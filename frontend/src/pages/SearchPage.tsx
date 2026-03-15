import { useState, useCallback, useEffect, useRef } from 'react';
import { Search, FileText } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { searchDocuments } from '../services/api-v2';
import type { SearchResult } from '../types/dms';
import DocumentDetailPanel from '../components/DocumentDetailPanel';

interface SearchPageProps {
  onSelectDocument?: (id: number) => void;
  userRole?: string;
}

export default function SearchPage({ userRole = 'viewer' }: SearchPageProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [detailDocId, setDetailDocId] = useState<number | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      setTotal(0);
      setSearched(false);
      return;
    }
    setLoading(true);
    setSearched(true);
    try {
      const data = await searchDocuments({ q: q.trim(), limit: 50 });
      setResults(data.results);
      setTotal(data.total);
    } catch {
      toast.error('搜索失败');
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounced auto-search on input change
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(query), 400);
    return () => clearTimeout(debounceRef.current);
  }, [query, doSearch]);

  const handleSearch = useCallback((e?: React.FormEvent) => {
    e?.preventDefault();
    clearTimeout(debounceRef.current);
    doSearch(query);
  }, [query, doSearch]);

  const statusColors: Record<string, string> = {
    active: 'bg-green-900/30 text-green-400',
    draft: 'bg-yellow-900/30 text-yellow-400',
    archived: 'bg-gray-800/30 text-gray-400',
    expired: 'bg-red-900/30 text-red-400',
  };

  return (
    <div>
      <h2 className="text-lg font-orbitron font-semibold text-cp-text flex items-center gap-2 mb-4">
        <Search className="w-5 h-5 text-cp-cyan" />
        文档搜索
      </h2>

      <form onSubmit={handleSearch} className="flex gap-2 mb-6">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索文档标题、内容..."
          className="cp-input flex-1 rounded-lg px-4 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="cp-btn-primary px-4 py-2 rounded-lg"
        >
          {loading ? '搜索中...' : '搜索'}
        </button>
      </form>

      {!searched ? (
        <div className="text-center py-16 text-cp-dim">
          <Search className="w-12 h-12 mx-auto mb-2 opacity-50" />
          <p>输入关键词搜索文档</p>
        </div>
      ) : loading ? (
        <div className="text-center py-12 text-cp-dim">搜索中...</div>
      ) : results.length === 0 ? (
        <div className="text-center py-12 text-cp-dim">
          <p>未找到匹配的文档</p>
        </div>
      ) : (
        <div>
          <p className="text-sm text-cp-muted mb-3">找到 {total} 条结果</p>
          <div className="space-y-2">
            {results.map((r) => (
              <div
                key={r.id}
                onClick={() => setDetailDocId(r.id)}
                className="cp-card rounded-lg p-4 cursor-pointer"
              >
                <div className="flex items-center gap-2 mb-1">
                  <FileText className="w-4 h-4 text-cp-dim shrink-0" />
                  <span className="font-medium text-cp-text">{r.title}</span>
                  <span className={clsx('px-2 py-0.5 text-xs rounded-full', statusColors[r.status] || 'bg-gray-800/30 text-gray-400')}>
                    {r.status}
                  </span>
                </div>
                {r.snippet && (
                  <p
                    className="text-sm text-cp-muted mt-1 line-clamp-2"
                    dangerouslySetInnerHTML={{ __html: r.snippet }}
                  />
                )}
                <div className="flex items-center gap-3 mt-2 text-xs text-cp-dim">
                  {r.doc_type && <span>{r.doc_type.name}</span>}
                  {r.folder && <span>{r.folder.path}</span>}
                  {r.entity_names.length > 0 && <span>{r.entity_names.join(', ')}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Document detail modal */}
      {detailDocId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setDetailDocId(null)}
        >
          <div
            className="mx-4 rounded-xl shadow-2xl overflow-hidden [&>div]:w-full [&>div]:max-w-none [&>div]:max-h-[85vh] [&>div]:border-l-0 [&>div]:rounded-xl"
            style={{ width: '600px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <DocumentDetailPanel
              documentId={detailDocId}
              userRole={userRole}
              onClose={() => setDetailDocId(null)}
              onUpdated={() => doSearch(query)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
