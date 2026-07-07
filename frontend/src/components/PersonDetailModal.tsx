import { useState, useEffect } from 'react';
import { X, FolderOpen, Plus, Building2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { searchDocuments, getEntity } from '../services/api-v2';
import { searchResultToMaterialInfo } from '../services/adapters';
import type { Entity, SearchResult } from '../types/dms';
import MaterialCard from './MaterialCard';
import MaterialPicker from './MaterialPicker';
import OCRResultViewer from './OCRResultViewer';

interface Props {
  entity: Entity;
  onClose: () => void;
  onRefresh: () => void;
}

export default function PersonDetailModal({ entity, onClose, onRefresh }: Props) {
  const [docs, setDocs] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageTitle, setImageTitle] = useState('');
  const [showPicker, setShowPicker] = useState(false);
  const [ocrDoc, setOcrDoc] = useState<SearchResult | null>(null);
  const [relations, setRelations] = useState<any[]>([]);
  const attrs = (entity.attributes || {}) as Record<string, string | null>;

  useEffect(() => { loadAll(); }, [entity]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') imageUrl ? setImageUrl(null) : onClose(); };
    document.addEventListener('keydown', h);
    return () => document.removeEventListener('keydown', h);
  }, [onClose, imageUrl]);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [docData, entData] = await Promise.all([
        searchDocuments({ entity_id: entity.id, limit: 100 }),
        getEntity(entity.id),
      ]);
      setDocs(docData.results);
      // Extract employed_by relations (getEntity returns extra fields not in base type)
      const rels = (entData as any).relations || {};
      setRelations([...(rels.outgoing || []), ...(rels.incoming || [])]);
    } catch (err) { toast.error('加载失败'); }
    finally { setLoading(false); }
  };

  const materials = docs.map(searchResultToMaterialInfo);
  const companyRel = relations.find(r => r.relation === 'employed_by');
  const companyName = companyRel?.to_name || companyRel?.from_name || null;

  if (!entity) return null;

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
        <div className="bg-white rounded-lg max-w-7xl w-full max-h-[90vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
          <div className="p-6 border-b">
            <div className="flex items-start justify-between mb-4">
              <div className="flex-1">
                <h2 className="text-2xl font-bold text-gray-900">{entity.name}</h2>
                <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                  {attrs.id_number && <div><span className="text-gray-500">身份证:</span> <span className="text-gray-900 font-mono">{String(attrs.id_number)}</span></div>}
                  {attrs.education && <div><span className="text-gray-500">学历:</span> <span className="text-gray-900">{String(attrs.education)}</span></div>}
                  {attrs.position && <div><span className="text-gray-500">职位:</span> <span className="text-gray-900">{String(attrs.position)}</span></div>}
                </div>
                <div className="mt-2 flex items-center gap-2 text-sm">
                  <Building2 className="w-4 h-4 text-gray-500" />
                  <span className="text-gray-500">所属公司:</span>
                  <span className="text-gray-900 font-medium">{companyName || '未关联'}</span>
                </div>
              </div>
              <button onClick={onClose} className="ml-4 p-2 text-gray-400 hover:text-gray-600 rounded-lg"><X className="w-6 h-6" /></button>
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowPicker(true)} className="inline-flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600">
                <Plus className="w-4 h-4" />关联文档
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-6">
            {loading ? <div className="text-center py-12"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto" /></div>
             : materials.length === 0 ? <div className="text-center py-12 text-gray-400"><FolderOpen className="w-12 h-12 mx-auto mb-2" /><p className="text-sm">暂无文档</p></div>
             : <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {materials.map((m: any) => (
                  <MaterialCard key={m.id} material={m}
                    onUpdateExpiry={async () => {}} onDelete={async () => { toast.success('请通过文档管理删除'); }}
                    onImageClick={(url: string, title: string) => { setImageUrl(url); setImageTitle(title); }}
                    onTriggerOCR={async () => { toast('OCR 已集成到上传管线'); }}
                    onViewOCR={(mat: any) => setOcrDoc(docs.find(d => d.id === mat.id) || null)}
                    onUnlink={async () => { toast('请通过实体管理取消关联'); }}
                  />
                ))}
              </div>}
          </div>
        </div>
      </div>
      {showPicker && <MaterialPicker onSelect={async () => { setShowPicker(false); loadAll(); onRefresh(); }} onClose={() => setShowPicker(false)} excludeIds={docs.map(d => d.id)} />}
      {imageUrl && <div className="fixed inset-0 z-[60] bg-black/90 flex items-center justify-center p-4" onClick={() => setImageUrl(null)}>
        <button onClick={() => setImageUrl(null)} className="absolute top-4 right-4 p-2 bg-cp-purple/10 rounded-lg text-white"><X className="w-6 h-6" /></button>
        <img src={imageUrl} alt={imageTitle} className="max-w-full max-h-[90vh] object-contain" onClick={e => e.stopPropagation()} />
      </div>}
      {ocrDoc && <OCRResultViewer material={searchResultToMaterialInfo(ocrDoc)} onClose={() => setOcrDoc(null)} />}
    </>
  );
}
