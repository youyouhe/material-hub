import { useState, useEffect } from 'react';
import { Users, Loader2, RefreshCw } from 'lucide-react';
import { listEntities } from '../services/api-v2';
import { entityToPersonInfo } from '../services/adapters';
import PersonCard from '../components/PersonCard';
import PersonDetailModal from '../components/PersonDetailModal';
import type { Entity } from '../types/dms';

export default function PersonsPage() {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Entity | null>(null);

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      setLoading(true);
      const data = await listEntities({ type: 'person' });
      setEntities(data.results);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed');
    } finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2"><Users className="w-7 h-7" />人员管理</h1>
        <button onClick={load} disabled={loading} className="flex items-center gap-2 px-3 py-2 text-sm bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />刷新
        </button>
      </div>
      {loading ? <div className="flex items-center justify-center py-12"><Loader2 className="w-6 h-6 text-blue-500 animate-spin" /></div>
       : error ? <div className="text-center py-12 text-red-500 text-sm">{error}</div>
       : entities.length === 0 ? <div className="text-center py-12 text-gray-400"><Users className="w-12 h-12 mx-auto mb-2" /><p className="text-sm">暂无人员</p></div>
       : <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {entities.map(e => <PersonCard key={e.id} person={entityToPersonInfo(e)} onClick={() => setSelected(e)} />)}
          </div>
          <p className="text-xs text-gray-400 text-right">共 {entities.length} 人</p>
        </>}
      {selected && <PersonDetailModal entity={selected} onClose={() => setSelected(null)} onRefresh={load} />}
    </div>
  );
}
