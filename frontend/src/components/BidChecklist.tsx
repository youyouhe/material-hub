import { useState, useEffect, useCallback } from 'react';
import { CheckCircle2, Circle, FileText, Plus, X, Sparkles, Link } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { getChecklist, getSuggestions, linkBidDocument, unlinkBidDocument, searchDocuments } from '../services/api-v2';
import type { ChecklistItem, ChecklistResponse, DocumentSuggestion, SearchResult } from '../types/dms';

interface BidChecklistProps {
  bidId: number;
  userRole: string;
}

export default function BidChecklist({ bidId, userRole }: BidChecklistProps) {
  const [checklist, setChecklist] = useState<ChecklistResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [linkingReqId, setLinkingReqId] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<DocumentSuggestion[]>([]);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [sugLoading, setSugLoading] = useState(false);

  const canEdit = userRole === 'editor' || userRole === 'admin';

  const fetchChecklist = useCallback(async () => {
    try {
      const data = await getChecklist(bidId);
      setChecklist(data);
    } catch { toast.error('加载需求清单失败'); }
    finally { setLoading(false); }
  }, [bidId]);

  useEffect(() => { fetchChecklist(); }, [fetchChecklist]);

  const handleOpenLink = async (reqId: number) => {
    setLinkingReqId(reqId);
    setSugLoading(true);
    setSearchResults([]);
    setSearchQuery('');
    try {
      const data = await getSuggestions(bidId, reqId);
      setSuggestions(data.suggestions);
    } catch { setSuggestions([]); }
    finally { setSugLoading(false); }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    try {
      const data = await searchDocuments({ q: searchQuery.trim(), limit: 10 });
      setSearchResults(data.results);
    } catch { toast.error('搜索失败'); }
  };

  const handleLink = async (docId: number) => {
    if (!linkingReqId) return;
    try {
      await linkBidDocument(bidId, linkingReqId, { document_id: docId });
      toast.success('文档已关联');
      setLinkingReqId(null);
      fetchChecklist();
    } catch (err) { toast.error(err instanceof Error ? err.message : '关联失败'); }
  };

  const handleUnlink = async (reqId: number, docId: number) => {
    if (!confirm('确定要取消关联？')) return;
    try {
      await unlinkBidDocument(bidId, reqId, docId);
      toast.success('已取消关联');
      fetchChecklist();
    } catch { toast.error('取消关联失败'); }
  };

  if (loading) return <div className="text-center py-8 text-cp-dim">加载中...</div>;
  if (!checklist) return null;

  return (
    <div className="cp-card rounded-lg p-4">
      {/* Progress header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-cp-purple-light">需求清单</h3>
        <span className="text-sm text-cp-muted">
          {checklist.fulfilled}/{checklist.total} 已满足 ({checklist.percentage}%)
        </span>
      </div>
      <div className="w-full bg-cp-purple/5 rounded-full h-2 mb-4">
        <div
          className={clsx('h-2 rounded-full transition-all', checklist.percentage === 100 ? 'bg-green-500' : checklist.percentage > 50 ? 'bg-cp-purple' : 'bg-amber-500')}
          style={{ width: `${checklist.percentage}%` }}
        />
      </div>

      {/* Items */}
      {checklist.items.length === 0 ? (
        <p className="text-sm text-cp-dim text-center py-4">暂无需求项</p>
      ) : (
        <div className="space-y-3">
          {checklist.items.map((item) => (
            <div key={item.id} className="border border-cp-border/50 rounded-lg p-3">
              <div className="flex items-start gap-2">
                {item.status === 'fulfilled' ? (
                  <CheckCircle2 className="w-5 h-5 text-green-400 shrink-0 mt-0.5" />
                ) : (
                  <Circle className="w-5 h-5 text-cp-dim shrink-0 mt-0.5" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-cp-text">{item.title}</span>
                    {item.is_required && <span className="text-xs text-cp-rose">必需</span>}
                    {item.doc_type && <span className="text-xs text-cp-dim">({item.doc_type.name})</span>}
                  </div>

                  {/* Linked documents */}
                  {item.linked_documents.length > 0 && (
                    <div className="mt-1 space-y-0.5">
                      {item.linked_documents.map((ld) => (
                        <div key={ld.document_id} className="flex items-center gap-2 text-xs">
                          <Link className="w-3 h-3 text-cp-cyan" />
                          <span className="text-cp-muted">{ld.document_title || `文档 #${ld.document_id}`}</span>
                          <span className={clsx('px-1.5 py-0.5 rounded', ld.link_status === 'verified' ? 'bg-green-900/20 text-green-400' : 'bg-cp-purple/5 text-cp-dim')}>
                            {ld.link_status === 'verified' ? '已验证' : '已关联'}
                          </span>
                          {canEdit && (
                            <button onClick={() => handleUnlink(item.id, ld.document_id)} className="text-cp-dim hover:text-cp-rose">
                              <X className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Add document button */}
                  {canEdit && item.status === 'missing' && (
                    <button
                      onClick={() => handleOpenLink(item.id)}
                      className="mt-1 flex items-center gap-1 text-xs text-cp-cyan hover:text-cyan-300"
                    >
                      <Plus className="w-3 h-3" /> 添加文档
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Link document modal */}
      {linkingReqId && (
        <div className="cp-overlay fixed inset-0 flex items-center justify-center z-50">
          <div className="cp-card rounded-lg p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-orbitron font-semibold text-cp-text">关联文档</h3>
              <button onClick={() => setLinkingReqId(null)} className="text-cp-dim hover:text-cp-text"><X className="w-5 h-5" /></button>
            </div>

            {/* Auto suggestions */}
            {sugLoading ? (
              <p className="text-sm text-cp-dim mb-4">加载推荐...</p>
            ) : suggestions.length > 0 && (
              <div className="mb-4">
                <h4 className="text-sm font-medium text-cp-purple-light flex items-center gap-1 mb-2">
                  <Sparkles className="w-3.5 h-3.5" /> 推荐匹配
                </h4>
                <div className="space-y-1">
                  {suggestions.map((s) => (
                    <button key={s.id} onClick={() => handleLink(s.id)} className="w-full text-left p-2 text-sm border border-cp-border rounded hover:bg-cp-purple/10 hover:border-cp-purple flex items-center justify-between transition-colors">
                      <div>
                        <span className="text-cp-text">{s.title}</span>
                        {s.doc_type && <span className="text-xs text-cp-dim ml-2">{s.doc_type.name}</span>}
                      </div>
                      <Plus className="w-4 h-4 text-cp-purple" />
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Manual search */}
            <div>
              <h4 className="text-sm font-medium text-cp-muted mb-2">手动搜索</h4>
              <div className="flex gap-2 mb-2">
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder="搜索文档..."
                  className="cp-input flex-1 rounded-md px-3 py-1.5 text-sm"
                />
                <button onClick={handleSearch} className="cp-btn-primary px-3 py-1.5 text-sm rounded-md">搜索</button>
              </div>
              {searchResults.length > 0 && (
                <div className="space-y-1">
                  {searchResults.map((r) => (
                    <button key={r.id} onClick={() => handleLink(r.id)} className="w-full text-left p-2 text-sm border border-cp-border rounded hover:bg-cp-purple/10 hover:border-cp-purple flex items-center justify-between transition-colors">
                      <div>
                        <span className="text-cp-text">{r.title}</span>
                        {r.doc_type && <span className="text-xs text-cp-dim ml-2">{r.doc_type.name}</span>}
                      </div>
                      <Plus className="w-4 h-4 text-cp-purple" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
