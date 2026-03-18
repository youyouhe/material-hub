import { useState, useEffect, useCallback } from 'react';
import { Upload, Check, X, FileText, RefreshCw, Workflow, AlertTriangle } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { uploadFile, getUploadQueue, approveUpload, rejectUpload, listDocTypes, getFolderTree } from '../services/api-v2';
import type { DuplicateInfo } from '../services/api-v2';
import type { UploadQueueItem, DocType, FolderTreeNode } from '../types/dms';
import DocumentProcessPage from './DocumentProcessPage';

interface UploadPageV2Props {
  userRole: string;
}

const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  pending: { text: '等待中', color: 'text-cp-dim' },
  analyzing: { text: '分析中', color: 'text-cp-cyan' },
  analysis_done: { text: '待选页', color: 'text-cp-purple-light' },
  ocr_running: { text: 'OCR中', color: 'text-cp-cyan' },
  ocr_done: { text: 'OCR完成', color: 'text-cp-purple-light' },
  classifying: { text: '分类中', color: 'text-cp-cyan' },
  classified: { text: '待审核', color: 'text-amber-400' },
  finalizing: { text: '入库中', color: 'text-green-400' },
  completed: { text: '已完成', color: 'text-green-400' },
  failed: { text: '失败', color: 'text-cp-rose' },
};

function canProcess(status: string | undefined): boolean {
  return !!status && ['analysis_done', 'ocr_done', 'classified', 'failed'].includes(status);
}

export default function UploadPageV2({ userRole }: UploadPageV2Props) {
  const [queue, setQueue] = useState<UploadQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [docTypes, setDocTypes] = useState<DocType[]>([]);
  const [folders, setFolders] = useState<FolderTreeNode[]>([]);
  const [approveModal, setApproveModal] = useState<number | null>(null);
  const [approveForm, setApproveForm] = useState({ title: '', folder_id: 0, doc_type_id: 0 });
  const [processDocId, setProcessDocId] = useState<number | null>(null);
  const [duplicateModal, setDuplicateModal] = useState<{
    file: File;
    info: DuplicateInfo;
  } | null>(null);

  const canEdit = userRole === 'editor' || userRole === 'admin';

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getUploadQueue({ limit: 50 });
      setQueue(data.results);
    } catch { toast.error('加载上传队列失败'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchQueue(); }, [fetchQueue]);

  useEffect(() => {
    listDocTypes().then((data) => {
      const all: DocType[] = [];
      Object.values(data.doc_types).forEach((arr) => all.push(...arr));
      setDocTypes(all);
    }).catch(() => {});
    getFolderTree().then(setFolders).catch(() => {});
  }, []);

  // Auto-refresh queue every 5s when items are in progress
  useEffect(() => {
    const hasInProgress = queue.some(
      (item) => item.processing_status && ['pending', 'analyzing', 'ocr_running', 'classifying', 'finalizing'].includes(item.processing_status)
    );
    if (!hasInProgress) return;
    const timer = setInterval(fetchQueue, 5000);
    return () => clearInterval(timer);
  }, [queue, fetchQueue]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploading(true);
    let uploaded = 0;
    try {
      for (const file of Array.from(files)) {
        try {
          await uploadFile(file);
          uploaded++;
        } catch (err: unknown) {
          const dupErr = err as Error & { duplicateInfo?: DuplicateInfo };
          if (dupErr.duplicateInfo) {
            setDuplicateModal({ file, info: dupErr.duplicateInfo });
            break;
          }
          throw err;
        }
      }
      if (uploaded > 0) {
        toast.success(`${uploaded} 个文件已上传`);
        fetchQueue();
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '上传失败');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleForceUpload = async () => {
    if (!duplicateModal) return;
    setUploading(true);
    try {
      await uploadFile(duplicateModal.file, { force: true });
      toast.success('文件已强制上传');
      fetchQueue();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '上传失败');
    } finally {
      setUploading(false);
      setDuplicateModal(null);
    }
  };

  const handleApprove = async () => {
    if (!approveModal) return;
    try {
      await approveUpload(approveModal, {
        title: approveForm.title || undefined,
        folder_id: approveForm.folder_id || undefined,
        doc_type_id: approveForm.doc_type_id || undefined,
      });
      toast.success('已批准');
      setApproveModal(null);
      fetchQueue();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '批准失败');
    }
  };

  const handleReject = async (docId: number) => {
    if (!confirm('确定要拒绝此上传？')) return;
    try {
      await rejectUpload(docId);
      toast.success('已拒绝');
      fetchQueue();
    } catch { toast.error('拒绝失败'); }
  };

  function flattenFolders(nodes: FolderTreeNode[], depth = 0): { id: number; name: string; indent: number }[] {
    const result: { id: number; name: string; indent: number }[] = [];
    for (const n of nodes) {
      result.push({ id: n.id, name: n.name, indent: depth });
      if (n.children) result.push(...flattenFolders(n.children, depth + 1));
    }
    return result;
  }

  const flatFolders = flattenFolders(folders);

  // Show process page if selected
  if (processDocId !== null) {
    return (
      <DocumentProcessPage
        documentId={processDocId}
        onBack={() => { setProcessDocId(null); fetchQueue(); }}
        onFinalized={() => { setProcessDocId(null); fetchQueue(); }}
      />
    );
  }

  return (
    <div>
      <h2 className="text-lg font-orbitron font-semibold text-cp-text flex items-center gap-2 mb-4">
        <Upload className="w-5 h-5 text-cp-purple" />
        文件上传
      </h2>

      {/* Upload area */}
      <div className="cp-card rounded-lg border-2 border-dashed border-cp-border p-8 text-center mb-6">
        <Upload className="w-10 h-10 mx-auto text-cp-dim mb-2" />
        <p className="text-cp-muted mb-4">选择文件上传到文档管理系统</p>
        <label className={clsx(
          'inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors',
          uploading ? 'bg-cp-dim text-cp-bg' : 'cp-btn-primary'
        )}>
          <Upload className="w-4 h-4" />
          {uploading ? '上传中...' : '选择文件'}
          <input
            type="file"
            multiple
            onChange={handleUpload}
            disabled={uploading}
            className="hidden"
          />
        </label>
      </div>

      {/* Queue */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-cp-muted">上传队列（待处理）</h3>
        <button onClick={fetchQueue} className="text-sm text-cp-dim hover:text-cp-text flex items-center gap-1">
          <RefreshCw className="w-3.5 h-3.5" /> 刷新
        </button>
      </div>

      {loading ? (
        <div className="text-center py-8 text-cp-dim">加载中...</div>
      ) : queue.length === 0 ? (
        <div className="text-center py-8 text-cp-dim">
          <FileText className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>队列为空</p>
        </div>
      ) : (
        <div className="cp-card rounded-lg overflow-hidden">
          <table className="cp-table min-w-full">
            <thead>
              <tr>
                <th className="px-4 py-3 text-left">标题</th>
                <th className="px-4 py-3 text-left">处理状态</th>
                <th className="px-4 py-3 text-left">时间</th>
                {canEdit && <th className="px-4 py-3 text-right">操作</th>}
              </tr>
            </thead>
            <tbody>
              {queue.map((item) => {
                const statusInfo = STATUS_LABELS[item.processing_status] || { text: item.processing_status || item.status, color: 'text-cp-dim' };
                const showProcess = canProcess(item.processing_status);
                const isProcessing = ['pending', 'analyzing', 'ocr_running', 'classifying', 'finalizing'].includes(item.processing_status);

                return (
                  <tr key={item.id}>
                    <td className="px-4 py-3 text-sm text-cp-text">
                      {item.thumbnail_url && (
                        <img
                          src={item.thumbnail_url}
                          alt=""
                          className="w-8 h-10 object-cover rounded inline-block mr-2 align-middle"
                        />
                      )}
                      {item.title}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span className={clsx('flex items-center gap-1', statusInfo.color)}>
                        {isProcessing && (
                          <span className="w-2 h-2 rounded-full bg-current animate-pulse" />
                        )}
                        {statusInfo.text}
                      </span>
                      {item.processing_status === 'failed' && item.processing_error && (
                        <p className="text-xs text-cp-rose/70 mt-1 max-w-xs truncate" title={item.processing_error}>
                          {item.processing_error}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-cp-dim">{item.created_at?.slice(0, 16).replace('T', ' ')}</td>
                    {canEdit && (
                      <td className="px-4 py-3 text-right space-x-2">
                        {showProcess && (
                          <button
                            onClick={() => setProcessDocId(item.id)}
                            className="text-cp-purple-light hover:text-cp-purple text-sm"
                          >
                            <Workflow className="w-4 h-4 inline" /> 处理
                          </button>
                        )}
                        <button
                          onClick={() => {
                            setApproveModal(item.id);
                            setApproveForm({ title: item.title, folder_id: 0, doc_type_id: 0 });
                          }}
                          className="text-green-400 hover:text-green-300 text-sm"
                        >
                          <Check className="w-4 h-4 inline" /> 快速批准
                        </button>
                        <button
                          onClick={() => handleReject(item.id)}
                          className="text-cp-rose hover:text-red-300 text-sm"
                        >
                          <X className="w-4 h-4 inline" /> 拒绝
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Duplicate file warning modal */}
      {duplicateModal && (
        <div className="cp-overlay fixed inset-0 flex items-center justify-center z-50">
          <div className="cp-card rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-orbitron font-semibold text-amber-400 mb-4 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5" /> 文件重复
            </h3>
            <p className="text-sm text-cp-muted mb-3">
              文件 <span className="text-cp-text font-medium">{duplicateModal.file.name}</span> 与系统中已有文档内容相同：
            </p>
            <div className="p-3 rounded-lg bg-cp-bg/50 border border-cp-border/30 mb-4 space-y-1">
              <div className="text-sm">
                <span className="text-cp-dim">文档标题: </span>
                <span className="text-cp-text">{duplicateModal.info.existing_document.title}</span>
              </div>
              <div className="text-sm">
                <span className="text-cp-dim">状态: </span>
                <span className="text-cp-text">{duplicateModal.info.existing_document.status}</span>
              </div>
              {duplicateModal.info.existing_document.folder && (
                <div className="text-sm">
                  <span className="text-cp-dim">文件夹: </span>
                  <span className="text-cp-text">{duplicateModal.info.existing_document.folder}</span>
                </div>
              )}
              {duplicateModal.info.existing_document.doc_type && (
                <div className="text-sm">
                  <span className="text-cp-dim">类型: </span>
                  <span className="text-cp-text">{duplicateModal.info.existing_document.doc_type}</span>
                </div>
              )}
              {duplicateModal.info.existing_document.created_at && (
                <div className="text-sm">
                  <span className="text-cp-dim">上传时间: </span>
                  <span className="text-cp-text">{duplicateModal.info.existing_document.created_at.slice(0, 16).replace('T', ' ')}</span>
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDuplicateModal(null)}
                className="cp-btn-ghost px-4 py-2 text-sm rounded-md border border-cp-border"
              >
                取消上传
              </button>
              <button
                onClick={() => {
                  setDuplicateModal(null);
                  setProcessDocId(duplicateModal.info.existing_document.id);
                }}
                className="cp-btn-ghost px-4 py-2 text-sm rounded-md border border-cp-purple/50 text-cp-purple-light"
              >
                查看已有文档
              </button>
              <button
                onClick={handleForceUpload}
                disabled={uploading}
                className="cp-btn-primary px-4 py-2 text-sm rounded-md"
              >
                {uploading ? '上传中...' : '仍然上传'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Approve modal (quick approve without processing flow) */}
      {approveModal && (
        <div className="cp-overlay fixed inset-0 flex items-center justify-center z-50">
          <div className="cp-card rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-orbitron font-semibold text-cp-text mb-4">快速批准</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">标题</label>
                <input
                  value={approveForm.title}
                  onChange={(e) => setApproveForm({ ...approveForm, title: e.target.value })}
                  className="cp-input w-full rounded-md px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">文件夹</label>
                <select
                  value={approveForm.folder_id}
                  onChange={(e) => setApproveForm({ ...approveForm, folder_id: Number(e.target.value) })}
                  className="cp-select w-full rounded-md px-3 py-2 text-sm"
                >
                  <option value={0}>-- 选择文件夹 --</option>
                  {flatFolders.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.indent === 0 ? `📁 ${f.name}` : `${'\u00A0\u00A0\u00A0\u00A0'.repeat(f.indent)}└ ${f.name}`}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">文档类型</label>
                <select
                  value={approveForm.doc_type_id}
                  onChange={(e) => setApproveForm({ ...approveForm, doc_type_id: Number(e.target.value) })}
                  className="cp-select w-full rounded-md px-3 py-2 text-sm"
                >
                  <option value={0}>-- 选择类型 --</option>
                  {docTypes.map((dt) => (
                    <option key={dt.id} value={dt.id}>{dt.name}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setApproveModal(null)} className="cp-btn-ghost px-4 py-2 text-sm rounded-md">取消</button>
              <button onClick={handleApprove} className="cp-btn-primary px-4 py-2 text-sm rounded-md">确认批准</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
