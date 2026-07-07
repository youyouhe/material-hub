import { Building2, User, MapPin, FileText } from 'lucide-react';
import type { CompanyInfo } from '../types';

interface CompanyCardProps {
  company: CompanyInfo;
  onClick?: () => void;
}

export default function CompanyCard({ company, onClick }: CompanyCardProps) {
  return (
    <div
      onClick={onClick}
      className={`bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div className="flex items-start gap-3">
        <div className="p-2 bg-blue-50 rounded-lg">
          <Building2 className="w-6 h-6 text-blue-600" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-gray-900 truncate">
            {company.name}
          </h3>

          {company.legal_person && (
            <div className="flex items-center gap-1 mt-2 text-sm text-gray-600">
              <User className="w-4 h-4" />
              <span>法人：{company.legal_person}</span>
            </div>
          )}

          {company.address && (
            <div className="flex items-center gap-1 mt-1 text-sm text-gray-500">
              <MapPin className="w-4 h-4" />
              <span className="truncate">{company.address}</span>
            </div>
          )}

          {company.credit_code && (
            <div className="mt-2 text-xs text-gray-400 font-mono">
              {company.credit_code}
            </div>
          )}

          <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
            <div className="flex items-center gap-1">
              <FileText className="w-3 h-3" />
              <span>{company.document_count || 0} 文档</span>
            </div>
            <div>
              {company.material_count || 0} 素材
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
