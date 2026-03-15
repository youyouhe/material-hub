import { useState, useEffect, useCallback, useRef } from 'react';
import { FileText, Filter, ChevronLeft, ChevronRight, Eye, Folder, Brain } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { listDocuments } from '../services/api-v2';
import type { DmsDocument, DmsFile } from '../types/dms';
import DocumentDetailPanel from '../components/DocumentDetailPanel';
import FilePreviewModal from '../components/FilePreviewModal';
import ReprocessModal from '../components/ReprocessModal';

interface DocumentsPageProps {
  folderId: number | null;
  selectedDocumentId: number | null;
  onSelectDocument: (id: number) => void;
  userRole: string;
}

export default function DocumentsPage({ folderId, selectedDocumentId, onSelectDocument, userRole }: DocumentsPageProps) {
  const [documents, setDocuments] = useState<DmsDocument[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [detailDoc, setDetailDoc] = useState<number | null>(selectedDocumentId);
  const [previewFile, setPreviewFile] = useState<DmsFile | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [showReprocess, setShowReprocess] = useState(false);
  const canEdit = userRole === 'editor' || userRole === 'admin';
  const pollRef = useRef<ReturnType<typeof setInterval>>();

  // Cleanup polling on unmount
  useEffect(() => () => { clearInterval(pollRef.current); }, []);

  useEffect(() => {
    if (selectedDocumentId !== null) setDetailDoc(selectedDocumentId);
  }, [selectedDocumentId]);
  const limit = 20;

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { limit, offset };
      if (folderId) params.folder_id = folderId;
      if (statusFilter) params.status = statusFilter;
      const data = await listDocuments(params as any);
      setDocuments(data.results);
      setTotal(data.total);
    } catch (err) {
      toast.error('加载文档失败');
    } finally {
      setLoading(false);
    }
  }, [folderId, statusFilter, offset]);

  useEffect(() => { fetchDocuments(); }, [fetchDocuments]);
  useEffect(() => { setOffset(0); }, [folderId, statusFilter]);

  const handleRowClick = (doc: DmsDocument) => {
    setDetailDoc(doc.id);
    onSelectDocument(doc.id);
  };

  const toggleSelect = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === documents.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(documents.map((d) => d.id)));
    }
  };

  const statusColors: Record<string, string> = {
    active: 'bg-green-900/30 text-green-400',
    draft: 'bg-yellow-900/30 text-yellow-400',
    archived: 'bg-gray-800/30 text-gray-400',
    expired: 'bg-red-900/30 text-red-400',
    superseded: 'bg-purple-900/30 text-purple-400',
  };

  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <div className="flex gap-4">
      <div className={clsx('flex-1 min-w-0', detailDoc && 'max-w-[60%]')}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-orbitron font-semibold text-cp-text flex items-center gap-2">
            <FileText className="w-5 h-5 text-cp-purple" />
            文档管理
            {folderId && <span className="text-sm font-exo font-normal text-cp-muted">(按文件夹筛选)</span>}
          </h2>
          <div className="flex items-center gap-2">
            {canEdit && selectedIds.size > 0 && (
              <button
                onClick={() => setShowReprocess(true)}
                className="cp-btn-primary px-3 py-1 text-sm rounded-md flex items-center gap-1"
              >
                <Brain className="w-3.5 h-3.5" />
                重新分析 ({selectedIds.size})
              </button>
            )}
            <Filter className="w-4 h-4 text-cp-dim" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="cp-select text-sm rounded-md px-2 py-1"
            >
              <option value="">全部状态</option>
              <option value="active">生效</option>
              <option value="draft">草稿</option>
              <option value="archived">已归档</option>
              <option value="expired">已过期</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-12 text-cp-dim">加载中...</div>
        ) : documents.length === 0 ? (
          <div className="text-center py-12 text-cp-dim">
            <FileText className="w-12 h-12 mx-auto mb-2 opacity-50" />
            <p>暂无文档</p>
          </div>
        ) : (
          <>
            <div className="cp-card rounded-lg overflow-hidden">
              <table className="cp-table min-w-full">
                <thead>
                  <tr>
                    {canEdit && (
                      <th className="px-2 py-3 w-10 text-center">
                        <input
                          type="checkbox"
                          checked={documents.length > 0 && selectedIds.size === documents.length}
                          onChange={toggleSelectAll}
                          className="rounded border-cp-border text-cp-purple focus:ring-cp-purple/50"
                        />
                      </th>
                    )}
                    <th className="px-4 py-3 text-left">标题</th>
                    <th className="px-4 py-3 text-left">目录</th>
                    <th className="px-4 py-3 text-left">类型</th>
                    <th className="px-4 py-3 text-left">状态</th>
                    <th className="px-4 py-3 text-center w-12" title="AI元数据提取状态">AI</th>
                    <th className="px-4 py-3 text-left">到期日</th>
                    <th className="px-4 py-3 text-left">更新时间</th>
                    <th className="px-4 py-3 text-center w-16">预览</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr
                      key={doc.id}
                      onClick={() => handleRowClick(doc)}
                      className={clsx(
                        'cursor-pointer transition-colors',
                        detailDoc === doc.id && 'bg-cp-purple/10'
                      )}
                    >
                      {canEdit && (
                        <td className="px-2 py-3 text-center" onClick={(e) => toggleSelect(doc.id, e)}>
                          <input
                            type="checkbox"
                            checked={selectedIds.has(doc.id)}
                            readOnly
                            className="rounded border-cp-border text-cp-purple focus:ring-cp-purple/50 pointer-events-none"
                          />
                        </td>
                      )}
                      <td className="px-4 py-3 text-sm text-cp-text max-w-xs truncate">{doc.title}</td>
                      <td className="px-4 py-3 text-sm text-cp-dim max-w-[120px] truncate" title={doc.folder?.path || ''}>
                        {doc.folder ? (
                          <span className="inline-flex items-center gap-1">
                            <Folder className="w-3 h-3 flex-shrink-0" />
                            <span className="truncate">{doc.folder.path && doc.folder.path.length > 15 ? '.../' + doc.folder.name : (doc.folder.path || doc.folder.name)}</span>
                          </span>
                        ) : (
                          <span>-</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {doc.doc_type ? (
                          <span className="inline-block px-2 py-0.5 text-xs rounded-full bg-cp-purple/15 text-cp-purple-light border border-cp-purple/20">
                            {doc.doc_type.name}
                          </span>
                        ) : (
                          <span className="text-cp-dim">未分类</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className={clsx('inline-block px-2 py-0.5 text-xs rounded-full', statusColors[doc.status] || 'bg-gray-800/30 text-gray-400')}>
                          {doc.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        {(() => {
                          const meta = doc.metadata as Record<string, unknown> | null;
                          const extracted = meta?.extracted_data as Record<string, unknown> | undefined;
                          const hasData = extracted && typeof extracted === 'object' && Object.keys(extracted).length > 0;
                          return hasData ? (
                            <span title="已提取元数据"><Brain className="w-4 h-4 text-cp-cyan inline-block" /></span>
                          ) : (
                            <span className="text-cp-dim text-xs" title="未提取元数据">-</span>
                          );
                        })()}
                      </td>
                      <td className="px-4 py-3 text-sm text-cp-muted">{doc.expiry_date || '-'}</td>
                      <td className="px-4 py-3 text-sm text-cp-dim">{doc.updated_at?.slice(0, 10) || '-'}</td>
                      <td className="px-4 py-3 text-center">
                        {(() => {
                          const origFile = doc.current_revision?.files?.find((f) => f.file_type === 'original');
                          if (!origFile) return '-';
                          return (
                            <button
                              onClick={(e) => { e.stopPropagation(); setPreviewFile(origFile); }}
                              className="p-1 text-cp-dim hover:text-cp-cyan transition-colors rounded hover:bg-white/5"
                              title="预览文件"
                            >
                              <Eye className="w-4 h-4" />
                            </button>
                          );
                        })()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 text-sm text-cp-muted">
                <span>共 {total} 条，第 {currentPage}/{totalPages} 页</span>
                <div className="flex gap-2">
                  <button
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - limit))}
                    className="px-3 py-1 border border-cp-border rounded text-cp-muted hover:border-cp-purple disabled:opacity-30"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    disabled={currentPage >= totalPages}
                    onClick={() => setOffset(offset + limit)}
                    className="px-3 py-1 border border-cp-border rounded text-cp-muted hover:border-cp-purple disabled:opacity-30"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Detail panel */}
      {detailDoc && (
        <DocumentDetailPanel
          documentId={detailDoc}
          userRole={userRole}
          onClose={() => setDetailDoc(null)}
          onUpdated={fetchDocuments}
        />
      )}

      {/* File preview modal */}
      {previewFile && (
        <FilePreviewModal
          url={previewFile.url}
          filename={previewFile.filename}
          mimeType={previewFile.mime_type}
          onClose={() => setPreviewFile(null)}
        />
      )}

      {/* Reprocess modal */}
      {showReprocess && (
        <ReprocessModal
          docIds={Array.from(selectedIds)}
          onClose={() => setShowReprocess(false)}
          onDone={(queuedIds: number[]) => {
            setShowReprocess(false);
            setSelectedIds(new Set());
            fetchDocuments();

            // Poll every 5s for up to 2 minutes to detect completion
            const pending = new Set(queuedIds);
            let rounds = 0;
            clearInterval(pollRef.current);
            pollRef.current = setInterval(async () => {
              rounds++;
              if (pending.size === 0 || rounds > 24) {
                clearInterval(pollRef.current);
                return;
              }
              try {
                const params: Record<string, unknown> = { limit: 200, offset: 0 };
                if (folderId) params.folder_id = folderId;
                const data = await listDocuments(params as any);
                let doneCount = 0;
                for (const doc of data.results) {
                  if (!pending.has(doc.id)) continue;
                  const meta = doc.metadata as Record<string, unknown> | null;
                  const ed = meta?.extracted_data as Record<string, unknown> | undefined;
                  if (ed && Object.keys(ed).length > 0) {
                    pending.delete(doc.id);
                    doneCount++;
                  }
                }
                if (doneCount > 0) {
                  toast.success(`${doneCount} 份文档分析完成`);
                  fetchDocuments();
                }
                if (pending.size === 0) {
                  clearInterval(pollRef.current);
                }
              } catch { /* ignore */ }
            }, 5000);
          }}
        />
      )}
    </div>
  );
}
