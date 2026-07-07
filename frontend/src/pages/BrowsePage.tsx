import { useState, useEffect, useCallback } from 'react';
import { Loader2, FolderOpen, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import { useMaterials } from '../hooks/useMaterials';
import SearchBar from '../components/SearchBar';
import MaterialCard from '../components/MaterialCard';
import ImagePreview from '../components/ImagePreview';
import OCRResultViewer from '../components/OCRResultViewer';
import { listEntities } from '../services/api-v2';

const STATUS_OPTIONS = ['all', 'active', 'draft', 'expired', 'archived'] as const;

export default function BrowsePage() {
  const { materials, loading, search, remove } = useMaterials();
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<string>('active');
  const [entityId, setEntityId] = useState<number | undefined>();
  const [entityFilter, setEntityFilter] = useState('');
  const [entities, setEntities] = useState<any[]>([]);
  const [preview, setPreview] = useState<{ url: string; title: string } | null>(null);
  const [ocrViewer, setOcrViewer] = useState<any | null>(null);

  useEffect(() => { loadEntities(); }, []);

  const loadEntities = async () => {
    try {
      const data = await listEntities({});
      setEntities(data.results);
    } catch { /* ignore */ }
  };

  const doSearch = useCallback(() => {
    search({ q: query || undefined, status: status !== 'all' ? status : undefined, entity_id: entityId });
  }, [search, query, status, entityId]);

  useEffect(() => { doSearch(); }, [doSearch]);

  useEffect(() => {
    const hasProcessing = materials.some(m => m.ocr_status === 'processing');
    if (!hasProcessing) return;
    const id = setInterval(() => doSearch(), 3000);
    return () => clearInterval(id);
  }, [materials, doSearch]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2"><FolderOpen className="w-7 h-7" />浏览文档</h1>
        <div className="flex gap-2 items-center">
          <select value={entityFilter} onChange={e => { setEntityFilter(e.target.value); setEntityId(e.target.value ? Number(e.target.value) : undefined); }}
            className="text-sm border rounded-lg px-3 py-2">
            <option value="">全部实体</option>
            {entities.map((e: any) => <option key={e.id} value={e.id}>{e.name} ({e.entity_type})</option>)}
          </select>
          <select value={status} onChange={e => setStatus(e.target.value)}
            className="text-sm border rounded-lg px-3 py-2">
            {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s === 'all' ? '全部状态' : s}</option>)}
          </select>
          <button onClick={doSearch} className="p-2 rounded hover:bg-gray-100"><RefreshCw className="w-4 h-4" /></button>
        </div>
      </div>

      <SearchBar value={query} onChange={setQuery} />

      {loading ? <div className="flex items-center justify-center py-12"><Loader2 className="w-6 h-6 text-blue-500 animate-spin" /></div>
       : materials.length === 0 ? <div className="text-center py-12 text-gray-400"><FolderOpen className="w-12 h-12 mx-auto mb-2" /><p className="text-sm">暂无文档</p></div>
       : <>
          <p className="text-xs text-gray-400">{materials.length} 个文档</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {materials.map((m: any) => (
              <MaterialCard key={m.id} material={m}
                onUpdateExpiry={async () => {}} onDelete={async () => { if (confirm('删除?')) { await remove(m.id); toast.success('已删除'); } }}
                onImageClick={(url: string, title: string) => setPreview({ url, title })}
                onTriggerOCR={async () => toast('OCR已集成到上传管线')}
                onViewOCR={(mat: any) => setOcrViewer(mat)}
                onUnlink={async () => toast('请通过实体管理取消关联')}
              />
            ))}
          </div>
        </>}

      {preview && <ImagePreview url={preview.url} title={preview.title} onClose={() => setPreview(null)} />}
      {ocrViewer && <OCRResultViewer material={ocrViewer} onClose={() => setOcrViewer(null)} />}
    </div>
  );
}
