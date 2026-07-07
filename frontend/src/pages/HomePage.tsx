import { useState, useEffect } from 'react';
import { Building2, Users, ChevronRight, ChevronDown, Loader2, FileText } from 'lucide-react';
import toast from 'react-hot-toast';
import { listEntities, searchDocuments } from '../services/api-v2';
import { entityToCompanyInfo, entityToPersonInfo, searchResultToMaterialInfo } from '../services/adapters';
const TYPE_LABELS: Record<string, string> = {
  'license': '营业执照', 'legal_person_cert': '法人证明', 'qualification': '资质证书',
  'iso_cert': 'ISO认证', 'certificate': '证书', 'tax_payment_cert': '完税证明',
  'id_card': '身份证', 'education': '学历证书', 'other': '其他',
};

const groupByType = (materials: any[]) => {
  const groups: Record<string, any[]> = {};
  materials.forEach(m => {
    const type = m.material_type || 'other';
    (groups[type] = groups[type] || []).push(m);
  });
  return groups;
};

const getExpiryStatus = (m: any) => {
  if (!m.expiry_date) return null;
  const diff = Math.ceil((new Date(m.expiry_date).getTime() - Date.now()) / 86400000);
  return diff < 0 ? 'expired' : diff <= 30 ? 'expiring-soon' : 'valid';
};

function TreeNode({ item, isCompany }: { item: any; isCompany: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [materials, setMaterials] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const Icon = isCompany ? Building2 : Users;
  const color = isCompany ? 'blue' : 'green';

  const load = async () => {
    if (loaded) return;
    setLoading(true);
    try {
      const data = await searchDocuments({ entity_id: item.id, limit: 200 });
      setMaterials(data.results.map(searchResultToMaterialInfo));
      setLoaded(true);
    } catch { toast.error('加载失败'); }
    finally { setLoading(false); }
  };

  const grouped = groupByType(materials);
  const keys = Object.keys(grouped).sort();

  return (
    <div className="border rounded-lg bg-white shadow-sm">
      <div onClick={() => { if (!expanded && !loaded) load(); setExpanded(!expanded); }}
        className="flex items-center gap-3 p-4 cursor-pointer hover:bg-gray-50">
        <button>{expanded ? <ChevronDown className="w-5 h-5 text-gray-600" /> : <ChevronRight className="w-5 h-5 text-gray-600" />}</button>
        <Icon className={`w-5 h-5 text-${color}-600 flex-shrink-0`} />
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-gray-900 truncate">{item.name}</h3>
          <div className="flex items-center gap-4 mt-1 text-xs text-gray-500">
            {isCompany && item.legal_person && <span>法人: {item.legal_person}</span>}
            {!isCompany && item.education && <span>{item.education}</span>}
            {!isCompany && item.position && <span>{item.position}</span>}
            <span>{item.document_count || item.material_count || 0} 材料</span>
          </div>
        </div>
      </div>
      {expanded && (
        <div className="border-t bg-gray-50">
          {loading ? <div className="flex items-center justify-center py-8"><Loader2 className={`w-5 h-5 text-${color}-500 animate-spin`} /></div>
           : materials.length === 0 ? <div className="py-8 text-center text-gray-400 text-sm">暂无</div>
           : <div className="p-4 space-y-2">
              {keys.map(type => (
                <div key={type} className="ml-8">
                  <div className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2"><FileText className="w-4 h-4" />{TYPE_LABELS[type] || type} ({grouped[type].length})</div>
                  <div className="ml-6 space-y-1">
                    {grouped[type].map((mat: any) => {
                      const status = getExpiryStatus(mat);
                      return (
                        <div key={mat.id} className={`flex items-center justify-between py-1.5 px-3 rounded bg-white hover:bg-${color}-50 transition-colors`}>
                          <span className="text-sm text-gray-700 truncate flex-1">{mat.title}</span>
                          {mat.expiry_date && <span className={`text-xs px-2 py-0.5 rounded-full ml-2 ${status === 'expired' ? 'bg-red-100 text-red-700' : status === 'expiring-soon' ? 'bg-yellow-100 text-yellow-700' : 'bg-green-100 text-green-700'}`}>{status === 'expired' ? '已过期' : mat.expiry_date}</span>}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>}
        </div>
      )}
    </div>
  );
}

export default function HomePage() {
  const [companies, setCompanies] = useState<any[]>([]);
  const [persons, setPersons] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterId, setFilterId] = useState<number | null>(null);

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [cData, pData] = await Promise.all([
        listEntities({ type: 'org' }),
        listEntities({ type: 'person' }),
      ]);
      setCompanies(cData.results.map(entityToCompanyInfo));
      setPersons(pData.results.map(entityToPersonInfo));
    } catch { toast.error('加载失败'); }
    finally { setLoading(false); }
  };

  if (loading) return <div className="flex items-center justify-center py-12"><Loader2 className="w-8 h-8 text-blue-500 animate-spin" /></div>;

  const fc = filterId ? companies.filter(c => c.id === filterId) : companies;
  const fp = filterId ? persons.filter(p => p.company_id === filterId) : persons;
  const total = fc.reduce((s: number, c: any) => s + (c.document_count || c.material_count || 0), 0) + fp.reduce((s: number, p: any) => s + (p.material_count || 0), 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h1 className="text-2xl font-bold text-gray-900">结构化信息概览</h1><p className="text-sm text-gray-500 mt-1">{fc.length} 公司 · {fp.length} 人员 · {total} 材料</p></div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">筛选:</label>
          <select value={filterId ?? ''} onChange={e => setFilterId(e.target.value ? Number(e.target.value) : null)} className="text-sm border rounded-lg px-3 py-2">
            <option value="">全部</option>
            {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
      </div>
      {companies.length === 0 && persons.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-lg border"><Building2 className="w-12 h-12 mx-auto mb-3 text-gray-400" /><p className="text-gray-500">暂无数据</p></div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-lg font-semibold"><Building2 className="w-5 h-5" />公司 ({fc.length})</div>
            {fc.length === 0 ? <div className="text-center py-8 bg-white rounded-lg border text-gray-400 text-sm">暂无</div>
             : <div className="space-y-3">{fc.map(c => <TreeNode key={c.id} item={c} isCompany />)}</div>}
          </div>
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-lg font-semibold"><Users className="w-5 h-5" />人员 ({fp.length})</div>
            {fp.length === 0 ? <div className="text-center py-8 bg-white rounded-lg border text-gray-400 text-sm">暂无</div>
             : <div className="space-y-3">{fp.map(p => <TreeNode key={p.id} item={p} isCompany={false} />)}</div>}
          </div>
        </div>
      )}
    </div>
  );
}
