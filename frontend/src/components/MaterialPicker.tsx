import { useState, useEffect } from 'react';
import { X, Search, CheckSquare } from 'lucide-react';
import { searchDocuments } from '../services/api-v2';
import { searchResultToMaterialInfo } from '../services/adapters';

interface Props {
  onSelect: (materialIds: number[], section?: string) => void;
  onClose: () => void;
  excludeIds?: number[];
  filterByType?: string[];
}

export default function MaterialPicker({ onSelect, onClose, excludeIds = [] }: Props) {
  const [materials, setMaterials] = useState<any[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadMaterials(); }, [query]);

  const loadMaterials = async () => {
    setLoading(true);
    try {
      const data = await searchDocuments({ q: query || undefined, limit: 50 });
      setMaterials(data.results
        .filter(r => !excludeIds.includes(r.id))
        .map(searchResultToMaterialInfo)
      );
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  const toggle = (id: number) => {
    setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  };

  const handleSubmit = () => {
    if (selected.size === 0) return;
    onSelect(Array.from(selected));
  };

  return (
    <div className="fixed inset-0 z-[70] bg-black/50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="p-4 border-b flex items-center justify-between">
          <h3 className="text-lg font-semibold">选择文档</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-4 border-b">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索文档..."
              className="w-full pl-10 pr-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? <div className="text-center py-8 text-gray-400">加载中...</div>
           : materials.length === 0 ? <div className="text-center py-8 text-gray-400">无匹配文档</div>
           : materials.map((m: any) => (
              <div key={m.id} onClick={() => toggle(m.id)}
                className={`flex items-center gap-3 p-3 rounded cursor-pointer ${selected.has(m.id) ? 'bg-blue-50 border border-blue-200' : 'hover:bg-gray-50 border border-transparent'}`}>
                <div className={`w-5 h-5 rounded border flex items-center justify-center ${selected.has(m.id) ? 'bg-blue-500 border-blue-500' : 'border-gray-300'}`}>
                  {selected.has(m.id) && <CheckSquare className="w-3.5 h-3.5 text-white" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{m.title}</p>
                  <p className="text-xs text-gray-500">{m.material_type || '未知'} · {m.section || ''}</p>
                </div>
              </div>
            ))}
        </div>
        <div className="p-4 border-t flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg">取消</button>
          <button onClick={handleSubmit} disabled={selected.size === 0}
            className="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg disabled:opacity-50">
            关联 ({selected.size})
          </button>
        </div>
      </div>
    </div>
  );
}
