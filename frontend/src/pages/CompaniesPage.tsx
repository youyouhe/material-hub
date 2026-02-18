import { useState, useEffect } from 'react';
import { Building2, Loader2, RefreshCw } from 'lucide-react';
import { listCompanies } from '../services/api';
import CompanyCard from '../components/CompanyCard';
import CompanyDetailModal from '../components/CompanyDetailModal';
import type { CompanyInfo } from '../types';

export default function CompaniesPage() {
  const [companies, setCompanies] = useState<CompanyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCompany, setSelectedCompany] = useState<CompanyInfo | null>(null);

  useEffect(() => {
    loadCompanies();
  }, []);

  const loadCompanies = async () => {
    try {
      setLoading(true);
      const data = await listCompanies();
      setCompanies(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load companies');
    } finally {
      setLoading(false);
    }
  };

  const handleCompanyClick = (company: CompanyInfo) => {
    setSelectedCompany(company);
  };

  const handleModalClose = () => {
    setSelectedCompany(null);
  };

  const handleRefresh = () => {
    loadCompanies();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Building2 className="w-7 h-7" />
          公司管理
        </h1>
        <button
          onClick={loadCompanies}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 text-sm bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
        </div>
      ) : error ? (
        <div className="text-center py-12 text-red-500 text-sm">{error}</div>
      ) : companies.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Building2 className="w-12 h-12 mx-auto mb-2" />
          <p className="text-sm">暂无公司信息</p>
          <p className="text-xs mt-1">上传包含营业执照或法人证明的文档后，系统会自动识别提取公司信息</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {companies.map((company) => (
              <CompanyCard
                key={company.id}
                company={company}
                onClick={() => handleCompanyClick(company)}
              />
            ))}
          </div>

          <p className="text-xs text-gray-400 text-right">
            共 {companies.length} 家公司
          </p>
        </>
      )}

      {/* Company Detail Modal */}
      {selectedCompany && (
        <CompanyDetailModal
          company={selectedCompany}
          onClose={handleModalClose}
          onRefresh={handleRefresh}
        />
      )}
    </div>
  );
}
