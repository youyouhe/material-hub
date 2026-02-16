import { useState, useEffect, useCallback } from 'react';
import { Filter, Loader2, FolderOpen } from 'lucide-react';
import clsx from 'clsx';
import type { ExpiryStatus } from '../types';
import { useMaterials } from '../hooks/useMaterials';
import SearchBar from '../components/SearchBar';
import MaterialCard from '../components/MaterialCard';
import ImagePreview from '../components/ImagePreview';

const STATUS_OPTIONS: { value: ExpiryStatus; label: string }[] = [
  { value: 'valid', label: 'Valid' },
  { value: 'expired', label: 'Expired' },
  { value: 'all', label: 'All' },
];

export default function BrowsePage() {
  const {
    materials,
    documents,
    loading,
    error,
    loadDocuments,
    search,
    updateExpiry,
    remove,
  } = useMaterials();

  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<ExpiryStatus>('valid');
  const [docFilter, setDocFilter] = useState<number | undefined>();
  const [preview, setPreview] = useState<{ url: string; title: string } | null>(null);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const doSearch = useCallback(() => {
    search({ q: query || undefined, document_id: docFilter, status });
  }, [search, query, docFilter, status]);

  useEffect(() => {
    doSearch();
  }, [doSearch]);

  const handleQueryChange = useCallback((val: string) => {
    setQuery(val);
  }, []);

  return (
    <div className="space-y-4">
      {/* Filters row */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[200px]">
          <SearchBar
            value={query}
            onChange={handleQueryChange}
            placeholder="Search by section name..."
          />
        </div>

        {/* Document filter */}
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-gray-400" />
          <select
            value={docFilter ?? ''}
            onChange={(e) =>
              setDocFilter(e.target.value ? Number(e.target.value) : undefined)
            }
            className="text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All documents</option>
            {documents.map((d) => (
              <option key={d.id} value={d.id}>
                {d.filename}
              </option>
            ))}
          </select>
        </div>

        {/* Status filter */}
        <div className="flex border border-gray-300 rounded-lg overflow-hidden">
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setStatus(opt.value)}
              className={clsx(
                'px-3 py-2 text-sm transition-colors',
                status === opt.value
                  ? 'bg-blue-500 text-white'
                  : 'bg-white text-gray-700 hover:bg-gray-50'
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Results */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
        </div>
      ) : error ? (
        <div className="text-center py-12 text-red-500 text-sm">{error}</div>
      ) : materials.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <FolderOpen className="w-12 h-12 mx-auto mb-2" />
          <p className="text-sm">No materials found</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {materials.map((m) => (
            <MaterialCard
              key={m.id}
              material={m}
              onUpdateExpiry={updateExpiry}
              onDelete={remove}
              onImageClick={(url, title) => setPreview({ url, title })}
            />
          ))}
        </div>
      )}

      {/* Count */}
      {!loading && materials.length > 0 && (
        <p className="text-xs text-gray-400 text-right">
          {materials.length} materials
        </p>
      )}

      {/* Image preview modal */}
      {preview && (
        <ImagePreview
          url={preview.url}
          title={preview.title}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  );
}
