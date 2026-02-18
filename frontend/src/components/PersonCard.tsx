import { User, GraduationCap, CreditCard, FileText } from 'lucide-react';
import type { PersonInfo } from '../types';

interface PersonCardProps {
  person: PersonInfo;
  onClick?: () => void;
}

export default function PersonCard({ person, onClick }: PersonCardProps) {
  return (
    <div
      onClick={onClick}
      className={`bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div className="flex items-start gap-3">
        <div className="p-2 bg-green-50 rounded-lg">
          <User className="w-6 h-6 text-green-600" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-gray-900">
            {person.name}
          </h3>

          {person.position && (
            <div className="mt-1 text-sm text-gray-600">
              {person.position}
            </div>
          )}

          {person.education && (
            <div className="flex items-center gap-1 mt-2 text-sm text-gray-600">
              <GraduationCap className="w-4 h-4" />
              <span>{person.education}</span>
            </div>
          )}

          {person.id_number && (
            <div className="flex items-center gap-1 mt-1 text-xs text-gray-400 font-mono">
              <CreditCard className="w-3 h-3" />
              <span>{person.id_number.replace(/^(.{6})(.{8})(.*)$/, '$1****$3')}</span>
            </div>
          )}

          <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
            <div className="flex items-center gap-1">
              <FileText className="w-3 h-3" />
              <span>{person.material_count || 0} 素材</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
