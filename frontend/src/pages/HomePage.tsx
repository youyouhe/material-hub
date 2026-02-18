import { useState, useEffect } from 'react';
import { Building2, Users, ChevronRight, ChevronDown, Loader2, FileText } from 'lucide-react';
import toast from 'react-hot-toast';
import { listCompanies, listPersons, getCompanyMaterials, getPersonMaterials } from '../services/api';
import type { CompanyInfo, PersonInfo, MaterialInfo } from '../types';

// 材料类型标签映射
const COMPANY_TYPE_LABELS: Record<string, string> = {
  'license': '营业执照',
  'legal_person_cert': '法定代表人证明',
  'qualification': '资质证书',
  'iso_cert': 'ISO认证',
  'certificate': '证书',
  'other': '其他材料'
};

const PERSON_TYPE_LABELS: Record<string, string> = {
  'id_card': '身份证',
  'education': '学历证书',
  'certificate': '职业证书',
  'qualification': '资格证书',
  'other': '其他材料'
};

// 按材料类型分组
const groupMaterialsByType = (materials: MaterialInfo[]) => {
  const groups: Record<string, MaterialInfo[]> = {};
  materials.forEach(mat => {
    const type = mat.material_type || 'other';
    if (!groups[type]) {
      groups[type] = [];
    }
    groups[type].push(mat);
  });
  return groups;
};

// 获取过期状态
const getExpiryStatus = (material: MaterialInfo) => {
  if (!material.expiry_date) return null;
  const today = new Date();
  const expiryDate = new Date(material.expiry_date);
  const diffTime = expiryDate.getTime() - today.getTime();
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

  if (diffDays < 0) return 'expired';
  if (diffDays <= 30) return 'expiring-soon';
  return 'valid';
};

interface CompanyTreeNodeProps {
  company: CompanyInfo;
}

function CompanyTreeNode({ company }: CompanyTreeNodeProps) {
  const [expanded, setExpanded] = useState(false);
  const [materials, setMaterials] = useState<MaterialInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const loadMaterials = async () => {
    if (loaded) return;
    setLoading(true);
    try {
      const data = await getCompanyMaterials(company.id);
      setMaterials(data.materials || []);
      setLoaded(true);
    } catch (error) {
      console.error('Failed to load materials:', error);
      toast.error('加载材料失败');
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = () => {
    if (!expanded && !loaded) {
      loadMaterials();
    }
    setExpanded(!expanded);
  };

  const groupedMaterials = groupMaterialsByType(materials);
  const groupKeys = Object.keys(groupedMaterials).sort();

  return (
    <div className="border rounded-lg bg-white shadow-sm">
      {/* Company header */}
      <div
        onClick={handleToggle}
        className="flex items-center gap-3 p-4 cursor-pointer hover:bg-gray-50 transition-colors"
      >
        <button className="flex-shrink-0">
          {expanded ? (
            <ChevronDown className="w-5 h-5 text-gray-600" />
          ) : (
            <ChevronRight className="w-5 h-5 text-gray-600" />
          )}
        </button>
        <Building2 className="w-5 h-5 text-blue-600 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-gray-900 truncate">{company.name}</h3>
          <div className="flex items-center gap-4 mt-1 text-xs text-gray-500">
            {company.legal_person && <span>法人: {company.legal_person}</span>}
            <span>{company.material_count || 0} 个材料</span>
          </div>
        </div>
      </div>

      {/* Materials tree */}
      {expanded && (
        <div className="border-t bg-gray-50">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
            </div>
          ) : materials.length === 0 ? (
            <div className="py-8 text-center text-gray-400 text-sm">暂无关联材料</div>
          ) : (
            <div className="p-4 space-y-2">
              {groupKeys.map(type => {
                const groupMaterials = groupedMaterials[type];
                return (
                  <div key={type} className="ml-8">
                    <div className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
                      <FileText className="w-4 h-4" />
                      {COMPANY_TYPE_LABELS[type] || type} ({groupMaterials.length})
                    </div>
                    <div className="ml-6 space-y-1">
                      {groupMaterials.map(mat => {
                        const expiryStatus = getExpiryStatus(mat);
                        return (
                          <div
                            key={mat.id}
                            className="flex items-center justify-between py-1.5 px-3 rounded bg-white hover:bg-blue-50 transition-colors group"
                          >
                            <span className="text-sm text-gray-700 truncate flex-1">
                              {mat.title}
                            </span>
                            {mat.expiry_date && (
                              <span
                                className={`text-xs px-2 py-0.5 rounded-full ml-2 flex-shrink-0 ${
                                  expiryStatus === 'expired'
                                    ? 'bg-red-100 text-red-700'
                                    : expiryStatus === 'expiring-soon'
                                    ? 'bg-yellow-100 text-yellow-700'
                                    : 'bg-green-100 text-green-700'
                                }`}
                              >
                                {expiryStatus === 'expired' ? '已过期' : mat.expiry_date}
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface PersonTreeNodeProps {
  person: PersonInfo;
}

function PersonTreeNode({ person }: PersonTreeNodeProps) {
  const [expanded, setExpanded] = useState(false);
  const [materials, setMaterials] = useState<MaterialInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const loadMaterials = async () => {
    if (loaded) return;
    setLoading(true);
    try {
      const data = await getPersonMaterials(person.id);
      setMaterials(data.materials || []);
      setLoaded(true);
    } catch (error) {
      console.error('Failed to load materials:', error);
      toast.error('加载材料失败');
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = () => {
    if (!expanded && !loaded) {
      loadMaterials();
    }
    setExpanded(!expanded);
  };

  const groupedMaterials = groupMaterialsByType(materials);
  const groupKeys = Object.keys(groupedMaterials).sort();

  return (
    <div className="border rounded-lg bg-white shadow-sm">
      {/* Person header */}
      <div
        onClick={handleToggle}
        className="flex items-center gap-3 p-4 cursor-pointer hover:bg-gray-50 transition-colors"
      >
        <button className="flex-shrink-0">
          {expanded ? (
            <ChevronDown className="w-5 h-5 text-gray-600" />
          ) : (
            <ChevronRight className="w-5 h-5 text-gray-600" />
          )}
        </button>
        <Users className="w-5 h-5 text-green-600 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-gray-900 truncate">{person.name}</h3>
          <div className="flex items-center gap-4 mt-1 text-xs text-gray-500">
            {person.education && <span>{person.education}</span>}
            {person.position && <span>{person.position}</span>}
            <span>{person.material_count || 0} 个材料</span>
          </div>
        </div>
      </div>

      {/* Materials tree */}
      {expanded && (
        <div className="border-t bg-gray-50">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 text-green-500 animate-spin" />
            </div>
          ) : materials.length === 0 ? (
            <div className="py-8 text-center text-gray-400 text-sm">暂无关联材料</div>
          ) : (
            <div className="p-4 space-y-2">
              {groupKeys.map(type => {
                const groupMaterials = groupedMaterials[type];
                return (
                  <div key={type} className="ml-8">
                    <div className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
                      <FileText className="w-4 h-4" />
                      {PERSON_TYPE_LABELS[type] || type} ({groupMaterials.length})
                    </div>
                    <div className="ml-6 space-y-1">
                      {groupMaterials.map(mat => {
                        const expiryStatus = getExpiryStatus(mat);
                        return (
                          <div
                            key={mat.id}
                            className="flex items-center justify-between py-1.5 px-3 rounded bg-white hover:bg-green-50 transition-colors group"
                          >
                            <span className="text-sm text-gray-700 truncate flex-1">
                              {mat.title}
                            </span>
                            {mat.expiry_date && (
                              <span
                                className={`text-xs px-2 py-0.5 rounded-full ml-2 flex-shrink-0 ${
                                  expiryStatus === 'expired'
                                    ? 'bg-red-100 text-red-700'
                                    : expiryStatus === 'expiring-soon'
                                    ? 'bg-yellow-100 text-yellow-700'
                                    : 'bg-green-100 text-green-700'
                                }`}
                              >
                                {expiryStatus === 'expired' ? '已过期' : mat.expiry_date}
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function HomePage() {
  const [companies, setCompanies] = useState<CompanyInfo[]>([]);
  const [persons, setPersons] = useState<PersonInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCompanyId, setSelectedCompanyId] = useState<number | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [companiesData, personsData] = await Promise.all([
        listCompanies(),
        listPersons()
      ]);
      setCompanies(companiesData);
      setPersons(personsData);
    } catch (error) {
      console.error('Failed to load data:', error);
      toast.error('加载数据失败');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    );
  }

  // 根据选择的公司过滤数据
  const filteredCompanies = selectedCompanyId
    ? companies.filter(c => c.id === selectedCompanyId)
    : companies;

  const filteredPersons = selectedCompanyId
    ? persons.filter(p => p.company_id === selectedCompanyId)
    : persons;

  const totalMaterials = filteredCompanies.reduce((sum, c) => sum + (c.material_count || 0), 0) +
                        filteredPersons.reduce((sum, p) => sum + (p.material_count || 0), 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">结构化信息概览</h1>
          <p className="text-sm text-gray-500 mt-1">
            {filteredCompanies.length} 家公司 · {filteredPersons.length} 位人员 · {totalMaterials} 个材料
          </p>
        </div>

        {/* Company Filter */}
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">筛选公司:</label>
          <select
            value={selectedCompanyId ?? ''}
            onChange={(e) => setSelectedCompanyId(e.target.value ? Number(e.target.value) : null)}
            className="text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">全部公司</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {companies.length === 0 && persons.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-lg border">
          <Building2 className="w-12 h-12 mx-auto mb-3 text-gray-400" />
          <p className="text-gray-500">暂无数据</p>
          <p className="text-xs text-gray-400 mt-2">
            上传包含营业执照、身份证等文档后，系统会自动识别并构建结构化信息
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Companies section */}
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-lg font-semibold text-gray-900">
              <Building2 className="w-5 h-5" />
              公司 ({filteredCompanies.length})
            </div>
            {filteredCompanies.length === 0 ? (
              <div className="text-center py-8 bg-white rounded-lg border text-gray-400 text-sm">
                暂无公司信息
              </div>
            ) : (
              <div className="space-y-3">
                {filteredCompanies.map(company => (
                  <CompanyTreeNode key={company.id} company={company} />
                ))}
              </div>
            )}
          </div>

          {/* Persons section */}
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-lg font-semibold text-gray-900">
              <Users className="w-5 h-5" />
              人员 ({filteredPersons.length})
            </div>
            {filteredPersons.length === 0 ? (
              <div className="text-center py-8 bg-white rounded-lg border text-gray-400 text-sm">
                暂无人员信息
              </div>
            ) : (
              <div className="space-y-3">
                {filteredPersons.map(person => (
                  <PersonTreeNode key={person.id} person={person} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
