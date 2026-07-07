import { useState, useEffect } from 'react';
import { RenderValue } from '../utils/format';
import { CheckCircle, XCircle, Search, RefreshCw, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { getUploadQueue, approveUpload, rejectUpload, getProcessingStatus, updateProcessingMetadata, confirmMerge, getDocument, getApproveSuggestions } from '../services/api-v2';
import type { UploadQueueItem, ProcessingStatus } from '../types/dms';
import { listDocTypes, getFolderTree } from '../services/api-v2';
import InteractiveOcrWizard from '../components/InteractiveOcrWizard';

interface DetailState {
  docId: number;
  status: ProcessingStatus | null;
  loading: boolean;
  wizardMode: boolean;
  pendingMerge: any | null; // _pending_merge from meta_json
}

export default function ReviewQueuePage() {
  const [items, setItems] = useState<UploadQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<DetailState | null>(null);
  const [corrections, setCorrections] = useState<{
    title?: string;
    doc_type_id?: number;
    folder_id?: number;
    material_type?: string;
    extracted_data?: Record<string, unknown>;
    kb_index?: boolean;
  }>({});
  const [suggestions, setSuggestions] = useState<{ doc_type: { id: number; name: string } | null; folder: { id: number; name: string; path: string } | null } | null>(null);
  const [docTypes, setDocTypes] = useState<Array<{ id: number; name: string; code: string }>>([]);
  const [folders, setFolders] = useState<Array<{ id: number; name: string; path: string }>>([]);

  useEffect(() => {
    loadQueue();
    loadMeta();
  }, []);

  const loadMeta = async () => {
    try {
      const dt = await listDocTypes();
      const all: Array<{ id: number; name: string; code: string }> = [];
      Object.values(dt.doc_types || {}).forEach((arr: any) => {
        (arr as any[]).forEach((t: any) => all.push(t));
      });
      setDocTypes(all);
    } catch { /* ignore */ }
    try {
      const ft = await getFolderTree();
      const flat: Array<{ id: number; name: string; path: string }> = [];
      const walk = (nodes: any[]) => {
        for (const n of nodes) {
          flat.push({ id: n.id, name: n.name, path: n.path });
          if (n.children) walk(n.children);
        }
      };
      walk(ft);
      setFolders(flat);
    } catch { /* ignore */ }
  };

  const loadQueue = async () => {
    setLoading(true);
    try {
      const data = await getUploadQueue({ offset: 0, limit: 100 });
      setItems(data.results.filter((i: UploadQueueItem) => i.processing_status !== 'pending'));
    } catch (err) {
      toast.error('加载审核队列失败');
    } finally {
      setLoading(false);
    }
  };

  const viewDetail = async (docId: number) => {
    setDetail({ docId, status: null, loading: true, wizardMode: false, pendingMerge: null });
    setCorrections({});
    try {
      const [s, doc] = await Promise.all([
        getProcessingStatus(docId),
        getDocument(docId).catch(() => null),
      ]);
      const totalPages = s.total_pages || 0;
      const needsOcr = (s.suggested_ocr_pages?.length || s.ocr_pages?.length || 0) > 0;
      const wizardMode = totalPages > 1 && needsOcr && s.processing_status === 'analysis_done';
      const pendingMerge = (doc as any)?.metadata?._pending_merge || null;
      setDetail({ docId, status: s, loading: false, wizardMode, pendingMerge });
      setCorrections({
        title: s.title || undefined,
        doc_type_id: s.doc_type?.id,
        folder_id: s.folder?.id,
        material_type: s.material_type || undefined,
        kb_index: false,
      });
      getApproveSuggestions(docId).then(setSuggestions).catch(() => {});
    } catch (err) {
      toast.error('加载详情失败');
      setDetail(null);
    }
  };

  const handleMergeAction = async (action: 'confirm' | 'reject') => {
    if (!detail) return;
    try {
      const result = await confirmMerge(detail.docId, action);
      if (action === 'confirm') {
        toast.success(`已合并到文档 #${(result as any).into_doc_id}`);
      } else {
        toast.success('已保留为独立文档');
      }
      setDetail(null);
      loadQueue();
    } catch (err: any) {
      toast.error(`操作失败: ${err.message}`);
    }
  };

  const handleApprove = async (docId: number) => {
    try {
      await approveUpload(docId, {
        title: corrections.title,
        doc_type_id: corrections.doc_type_id,
        folder_id: corrections.folder_id,
        kb_index: corrections.kb_index,
      });
      toast.success(corrections.kb_index ? '已批准 (KB索引后台进行中)' : '已批准并归档');
      setItems(prev => prev.filter(i => i.id !== docId));
      setDetail(null);
      setCorrections({});
    } catch (err) {
      toast.error(`批准失败: ${err}`);
    }
  };

  const handleReject = async (docId: number) => {
    const del = confirm('确定要删除此文档吗？\n\n点击"确定"：永久删除\n点击"取消"：仅归档（可恢复）');
    try {
      await rejectUpload(docId, del);
      toast.success(del ? '已删除' : '已归档');
      setItems(prev => prev.filter(i => i.id !== docId));
      setDetail(null);
    } catch (err) {
      toast.error(`操作失败: ${err}`);
    }
  };

  const handleSaveMetadata = async (docId: number) => {
    try {
      await updateProcessingMetadata(docId, corrections);
      toast.success('元数据已更新');
    } catch (err) {
      toast.error(`保存失败: ${err}`);
    }
  };

  const getStatusBadge = (status: string | null) => {
    const map: Record<string, { color: string; label: string }> = {
      pending: { color: 'bg-gray-500/20 text-gray-400', label: '等待中' },
      analyzing: { color: 'bg-blue-500/20 text-blue-400', label: '分析中' },
      analysis_done: { color: 'bg-yellow-500/20 text-yellow-400', label: '待OCR' },
      ocr_done: { color: 'bg-purple-500/20 text-purple-400', label: '待分类' },
      classified: { color: 'bg-green-500/20 text-green-400', label: '已分类' },
      failed: { color: 'bg-red-500/20 text-red-400', label: '失败' },
    };
    const m = map[status || ''] || { color: 'bg-gray-500/20 text-gray-400', label: status || '未知' };
    return <span className={`px-2 py-0.5 rounded text-xs ${m.color}`}>{m.label}</span>;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-cp-purple animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-orbitron font-bold text-cp-text">审核队列</h1>
          <p className="text-cp-muted text-sm mt-1">{items.length} 个文档等待审核</p>
        </div>
        <button onClick={loadQueue} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cp-card border border-cp-divider text-cp-muted hover:text-cp-text">
          <RefreshCw className="w-4 h-4" /> 刷新
        </button>
      </div>

      <div className="flex gap-6">
        {/* Queue list */}
        <div className={`${detail ? 'w-1/2' : 'w-full'} space-y-2`}>
          {items.length === 0 ? (
            <div className="cp-card rounded-lg p-12 text-center">
              <CheckCircle className="w-12 h-12 text-cp-green mx-auto mb-3" />
              <p className="text-cp-text font-medium">暂无待审核文档</p>
              <p className="text-cp-muted text-sm mt-1">上传文件后将在此处审核</p>
            </div>
          ) : (
            items.map(item => (
              <div key={item.id}
                onClick={() => viewDetail(item.id)}
                className={`cp-card rounded-lg p-4 cursor-pointer transition-all hover:border-cp-purple/50 ${
                  detail?.docId === item.id ? 'border-cp-purple ring-1 ring-cp-purple/30' : ''
                }`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-10 h-10 rounded-lg bg-cp-purple/10 flex items-center justify-center shrink-0">
                      {item.thumbnail_url ? (
                        <img src={item.thumbnail_url} alt="" className="w-10 h-10 rounded object-cover" />
                      ) : (
                        <Search className="w-5 h-5 text-cp-purple" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-cp-text truncate">{item.title}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        {getStatusBadge(item.processing_status)}
                        {item.doc_type && (
                          <span className="text-xs text-cp-muted">{item.doc_type.name}</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button onClick={(e) => { e.stopPropagation(); handleApprove(item.id); }}
                      className="p-1.5 rounded hover:bg-cp-green/10 text-cp-muted hover:text-cp-green" title="批准">
                      <CheckCircle className="w-4 h-4" />
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); handleReject(item.id); }}
                      className="p-1.5 rounded hover:bg-cp-rose/10 text-cp-muted hover:text-cp-rose" title="拒绝">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Detail panel */}
        {detail && (
          <div className="w-1/2 cp-card rounded-lg p-4 space-y-4 sticky top-4 self-start max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <h3 className="text-cp-text font-medium">
                {detail.status?.title || `文档 #${detail.docId}`}
              </h3>
              <button onClick={() => setDetail(null)} className="text-cp-muted hover:text-cp-text">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            {detail.loading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="w-6 h-6 text-cp-purple animate-spin" />
              </div>
            ) : detail.wizardMode ? (
              <InteractiveOcrWizard
                docId={detail.docId}
                onComplete={() => { setDetail(null); loadQueue(); }}
                onCancel={() => setDetail(null)}
              />
            ) : detail.status ? (
              <>
                {/* Merge confirmation */}
                {detail.pendingMerge && (
                  <div className="bg-cp-rose/10 border border-cp-rose/30 rounded-lg p-4 space-y-3">
                    <div className="flex items-start gap-2">
                      <span className="text-cp-rose text-lg">⚠️</span>
                      <div>
                        <p className="text-cp-text font-medium">发现可能重复的文档</p>
                        <p className="text-cp-muted text-sm mt-1">
                          该文档与已有文档 <strong className="text-cp-text">{detail.pendingMerge.existing_title}</strong>
                          可能是同一证书的不同版本（到期日: {detail.pendingMerge.new_expiry || '无'} vs {detail.pendingMerge.existing_expiry || '无'}）
                        </p>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => handleMergeAction('confirm')}
                        className="flex-1 py-2 rounded-lg bg-cp-purple/20 border border-cp-purple/40 text-cp-purple-light hover:bg-cp-purple/30 text-sm">
                        合并（作为新版本）
                      </button>
                      <button onClick={() => handleMergeAction('reject')}
                        className="flex-1 py-2 rounded-lg border border-cp-border text-cp-muted hover:text-cp-text text-sm">
                        保留为独立文档
                      </button>
                    </div>
                  </div>
                )}

                {/* Processing status */}
                <div className="bg-cp-bg rounded p-3 text-sm space-y-1">
                  <div className="flex justify-between">
                    <span className="text-cp-muted">处理状态</span>
                    {getStatusBadge(detail.status.processing_status)}
                  </div>
                  {detail.status.processing_error && (
                    <p className="text-cp-rose text-xs">{detail.status.processing_error}</p>
                  )}
                  {detail.status.total_pages > 0 && (
                    <p className="text-cp-muted text-xs">{detail.status.total_pages} 页 · {detail.status.file_type}</p>
                  )}
                </div>

                {/* AI-extracted info */}
                {detail.status.material_type && (
                  <div className="bg-cp-bg rounded p-3 text-sm">
                    <p className="text-cp-muted text-xs mb-1">AI 识别类型</p>
                    <p className="text-cp-text">{detail.status.material_type}</p>
                    {detail.status.confidence && (
                      <p className="text-cp-green text-xs">置信度: {Math.round(detail.status.confidence * 100)}%</p>
                    )}
                  </div>
                )}

                {detail.status.extracted_data && Object.keys(detail.status.extracted_data).length > 0 && (
                  <div className="bg-cp-bg rounded p-3 text-sm">
                    <p className="text-cp-muted text-xs mb-1">提取数据</p>
                    <div className="space-y-1">
                      {Object.entries(detail.status.extracted_data).map(([k, v]) => (
                        <div key={k} className="text-xs">
                          <span className="text-cp-muted">{k}</span>
                          <div className="mt-0.5"><RenderValue value={v} /></div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Page thumbnails */}
                {detail.status.pages && detail.status.pages.length > 0 && (
                  <div>
                    <p className="text-cp-muted text-xs mb-2">页面预览</p>
                    <div className="flex gap-2 overflow-x-auto pb-2">
                      {detail.status.pages.filter(p => p.thumbnail_url).map(p => (
                        <img key={p.page_num} src={p.thumbnail_url!}
                          className="w-24 h-32 object-cover rounded border border-cp-divider shrink-0"
                          alt={`第${p.page_num}页`} />
                      ))}
                    </div>
                  </div>
                )}

                {/* Corrections form */}
                <div className="space-y-3 border-t border-cp-divider pt-3">
                  <p className="text-cp-text text-sm font-medium">修正信息</p>

                  {/* AI suggestions */}
                  {suggestions && ((suggestions as any).material_type || suggestions.doc_type || suggestions.folder) && (
                    <div className="bg-cp-purple/10 border border-cp-purple/30 rounded-lg p-2 text-xs space-y-1">
                      <span className="text-cp-purple-light font-medium">
                        💡 AI 建议{(suggestions as any).confidence ? ` (${Math.round((suggestions as any).confidence * 100)}%)` : ''}
                      </span>
                      {(suggestions as any).material_type && !suggestions.doc_type && !corrections.doc_type_id && (
                        <div className="text-cp-muted">
                          🏷️ AI 识别: <span className="text-cp-text">{(suggestions as any).material_type}</span>
                          <span className="text-cp-dim">（无匹配类型，请下拉选择或新建）</span>
                        </div>
                      )}
                      {suggestions.doc_type && !corrections.doc_type_id && (
                        <button onClick={() => setCorrections(p => ({ ...p, doc_type_id: suggestions.doc_type!.id }))}
                          className="block w-full text-left text-cp-text hover:text-cp-purple-light">
                          📄 {suggestions.doc_type.name}{(suggestions.doc_type as any).note ? `（{(suggestions.doc_type as any).note}）` : ''} → 点击采纳
                        </button>
                      )}
                      {suggestions.folder && !corrections.folder_id && (
                        <button onClick={() => setCorrections(p => ({ ...p, folder_id: suggestions.folder!.id }))}
                          className="block w-full text-left text-cp-text hover:text-cp-purple-light">
                          📁 {suggestions.folder.path || suggestions.folder.name} → 点击采纳
                        </button>
                      )}
                    </div>
                  )}

                  <div>
                    <label className="text-xs text-cp-muted">标题</label>
                    <input value={corrections.title || ''} onChange={e => setCorrections(p => ({ ...p, title: e.target.value }))}
                      className="cp-input block w-full mt-1 text-sm" />
                  </div>
                  <div>
                    <label className="text-xs text-cp-muted">文档类型</label>
                    <select value={corrections.doc_type_id || ''} onChange={e => setCorrections(p => ({ ...p, doc_type_id: Number(e.target.value) || undefined }))}
                      className="cp-input block w-full mt-1 text-sm">
                      <option value="">自动</option>
                      {docTypes.map(dt => (
                        <option key={dt.id} value={dt.id}>{dt.name} ({dt.code})</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-cp-muted">归档文件夹</label>
                    <select value={corrections.folder_id || ''} onChange={e => setCorrections(p => ({ ...p, folder_id: Number(e.target.value) || undefined }))}
                      className="cp-input block w-full mt-1 text-sm">
                      <option value="">自动</option>
                      {folders.map(f => (
                        <option key={f.id} value={f.id}>{f.path}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* KB checkbox */}
                <div className="flex items-center gap-2 pt-2 border-t border-cp-divider">
                  <input type="checkbox" id="kb_idx"
                    checked={corrections.kb_index || false}
                    onChange={(e) => setCorrections(p => ({ ...p, kb_index: e.target.checked }))}
                    className="w-4 h-4 rounded border-cp-border text-cp-purple" />
                  <label htmlFor="kb_idx" className="text-xs text-cp-muted cursor-pointer">
                    🧠 AI知识库索引
                  </label>
                </div>

                {/* Actions */}
                <div className="flex gap-2 pt-2">
                  <button onClick={() => handleSaveMetadata(detail!.docId)}
                    className="flex-1 px-3 py-2 rounded bg-cp-bg border border-cp-divider text-sm text-cp-muted hover:text-cp-text">
                    保存修改
                  </button>
                  <button onClick={() => handleApprove(detail!.docId)}
                    className="flex-1 px-3 py-2 rounded bg-cp-green/20 border border-cp-green/30 text-sm text-cp-green hover:bg-cp-green/30">
                    批准
                  </button>
                  <button onClick={() => handleReject(detail!.docId)}
                    className="flex-1 px-3 py-2 rounded bg-cp-rose/20 border border-cp-rose/30 text-sm text-cp-rose hover:bg-cp-rose/30">
                    拒绝
                  </button>
                </div>
              </>
            ) : (
              <p className="text-cp-muted text-sm text-center py-8">无法加载详情</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
