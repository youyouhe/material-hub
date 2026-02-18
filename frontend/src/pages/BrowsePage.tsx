import { useState, useEffect, useCallback } from 'react';
import { Filter, Loader2, FolderOpen, LayoutGrid, SplitSquareVertical, Trash2, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import type { ExpiryStatus, MaterialInfo, CompanyInfo } from '../types';
import { useMaterials } from '../hooks/useMaterials';
import SearchBar from '../components/SearchBar';
import MaterialCard from '../components/MaterialCard';
import ImagePreview from '../components/ImagePreview';
import DocumentViewer from '../components/DocumentViewer';
import OCRResultViewer from '../components/OCRResultViewer';
import { deleteDocument, triggerOCR, listCompanies } from '../services/api';

const STATUS_OPTIONS: { value: ExpiryStatus; label: string }[] = [
  { value: 'valid', label: 'Valid' },
  { value: 'expired', label: 'Expired' },
  { value: 'all', label: 'All' },
];

const LINKED_STATUS_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'company', label: '已关联公司' },
  { value: 'person', label: '已关联人员' },
  { value: 'unlinked', label: '未关联' },
] as const;

const SOURCE_TYPE_OPTIONS = [
  { value: 'all', label: '全部来源' },
  { value: 'docx', label: 'DOCX提取' },
  { value: 'manual', label: '手动上传' },
] as const;

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
  const [linkedStatus, setLinkedStatus] = useState<'all' | 'company' | 'person' | 'unlinked'>('all');
  const [sourceType, setSourceType] = useState<'all' | 'docx' | 'manual'>('all');
  const [companyFilter, setCompanyFilter] = useState<number | undefined>();
  const [companies, setCompanies] = useState<CompanyInfo[]>([]);
  const [preview, setPreview] = useState<{ url: string; title: string } | null>(null);
  const [viewMode, setViewMode] = useState<'grid' | 'split'>('grid');
  const [ocrViewer, setOcrViewer] = useState<MaterialInfo | null>(null);

  useEffect(() => {
    loadDocuments();
    loadCompanies();
  }, [loadDocuments]);

  const loadCompanies = useCallback(async () => {
    try {
      const data = await listCompanies();
      setCompanies(data);
    } catch (err) {
      console.error('Failed to load companies:', err);
    }
  }, []);

  const doSearch = useCallback(() => {
    search({
      q: query || undefined,
      document_id: docFilter,
      status,
      linked_status: linkedStatus,
      source_type: sourceType,
      company_id: companyFilter,
    });
  }, [search, query, docFilter, status, linkedStatus, sourceType, companyFilter]);

  useEffect(() => {
    doSearch();
  }, [doSearch]);

  // Auto-refresh when there are materials with processing status
  useEffect(() => {
    const hasProcessing = materials.some(m => m.ocr_status === 'processing');

    if (!hasProcessing) {
      return;
    }

    // Poll every 3 seconds when there are processing materials
    const intervalId = setInterval(() => {
      doSearch();
    }, 3000);

    return () => clearInterval(intervalId);
  }, [materials, doSearch]);

  const handleQueryChange = useCallback((val: string) => {
    setQuery(val);
  }, []);

  const handleDeleteDocument = useCallback(async (docId: number) => {
    const doc = documents.find(d => d.id === docId);
    if (!doc) return;

    if (!confirm(`确定要删除文档"${doc.filename}"及其所有提取的素材吗？此操作不可恢复。`)) {
      return;
    }

    try {
      await deleteDocument(docId);
      // Clear filter if deleted document was selected
      if (docFilter === docId) {
        setDocFilter(undefined);
      }
      // Reload documents and materials
      loadDocuments();
      doSearch();
    } catch (err) {
      alert(`删除失败: ${err instanceof Error ? err.message : String(err)}`);
    }
  }, [documents, docFilter, loadDocuments, doSearch]);

  const handleRefresh = useCallback(() => {
    loadDocuments();
    doSearch();
  }, [loadDocuments, doSearch]);

  const handleTriggerOCR = useCallback(async (materialId: number) => {
    try {
      await triggerOCR(materialId);
      toast.success('OCR识别已启动，处理中...');

      // Refresh after a short delay to show processing status
      setTimeout(() => {
        doSearch();
      }, 1000);
    } catch (err) {
      toast.error(`OCR启动失败: ${err instanceof Error ? err.message : String(err)}`);
    }
  }, [doSearch]);

  const handleViewOCR = useCallback((material: MaterialInfo) => {
    setOcrViewer(material);
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
          {docFilter && (
            <button
              onClick={() => handleDeleteDocument(docFilter)}
              className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg border border-gray-300 transition-colors"
              title="Delete this document"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
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

        {/* Linked status filter */}
        <select
          value={linkedStatus}
          onChange={(e) => setLinkedStatus(e.target.value as typeof linkedStatus)}
          className="text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {LINKED_STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        {/* Source type filter */}
        <select
          value={sourceType}
          onChange={(e) => setSourceType(e.target.value as typeof sourceType)}
          className="text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {SOURCE_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        {/* Company filter */}
        <select
          value={companyFilter ?? ''}
          onChange={(e) => setCompanyFilter(e.target.value ? Number(e.target.value) : undefined)}
          className="text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">全部公司</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>

        {/* Refresh button */}
        <button
          onClick={handleRefresh}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 text-sm bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
          title="刷新数据（OCR处理完成后点击刷新查看更新）"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>

        {/* View mode toggle */}
        <div className="flex border border-gray-300 rounded-lg overflow-hidden">
          <button
            onClick={() => setViewMode('grid')}
            className={clsx(
              'p-2 transition-colors',
              viewMode === 'grid'
                ? 'bg-blue-500 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            )}
            title="Grid view"
          >
            <LayoutGrid className="w-4 h-4" />
          </button>
          <button
            onClick={() => setViewMode('split')}
            className={clsx(
              'p-2 transition-colors',
              viewMode === 'split'
                ? 'bg-blue-500 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            )}
            title="Split view"
          >
            <SplitSquareVertical className="w-4 h-4" />
          </button>
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
      ) : viewMode === 'split' ? (
        // Split view - show DocumentViewer
        docFilter ? (
          <DocumentViewer
            materials={materials}
            documentId={docFilter}
            onUpdateExpiry={updateExpiry}
            onDelete={remove}
          />
        ) : (
          <div className="text-center py-12 text-gray-400">
            <SplitSquareVertical className="w-12 h-12 mx-auto mb-2" />
            <p className="text-sm">Please select a document to view in split mode</p>
          </div>
        )
      ) : (
        // Grid view - show MaterialCards
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {materials.map((m) => (
              <MaterialCard
                key={m.id}
                material={m}
                onUpdateExpiry={updateExpiry}
                onDelete={remove}
                onImageClick={(url, title) => setPreview({ url, title })}
                onTriggerOCR={handleTriggerOCR}
                onViewOCR={handleViewOCR}
              />
            ))}
          </div>

          {/* Count */}
          <p className="text-xs text-gray-400 text-right">
            {materials.length} materials
          </p>
        </>
      )}

      {/* Image preview modal - only show in grid view */}
      {viewMode === 'grid' && preview && (
        <ImagePreview
          url={preview.url}
          title={preview.title}
          onClose={() => setPreview(null)}
        />
      )}

      {/* OCR Result Viewer */}
      {ocrViewer && (
        <OCRResultViewer
          material={ocrViewer}
          onClose={() => setOcrViewer(null)}
        />
      )}
    </div>
  );
}
