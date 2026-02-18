import { useState, useEffect } from 'react';
import { Users, Loader2, RefreshCw } from 'lucide-react';
import { listPersons } from '../services/api';
import PersonCard from '../components/PersonCard';
import PersonDetailModal from '../components/PersonDetailModal';
import type { PersonInfo } from '../types';

export default function PersonsPage() {
  const [persons, setPersons] = useState<PersonInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPerson, setSelectedPerson] = useState<PersonInfo | null>(null);

  useEffect(() => {
    loadPersons();
  }, []);

  const loadPersons = async () => {
    try {
      setLoading(true);
      const data = await listPersons();
      setPersons(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load persons');
    } finally {
      setLoading(false);
    }
  };

  const handlePersonClick = (person: PersonInfo) => {
    setSelectedPerson(person);
  };

  const handleModalClose = () => {
    setSelectedPerson(null);
  };

  const handleRefresh = () => {
    loadPersons();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Users className="w-7 h-7" />
          人员管理
        </h1>
        <button
          onClick={loadPersons}
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
      ) : persons.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Users className="w-12 h-12 mx-auto mb-2" />
          <p className="text-sm">暂无人员信息</p>
          <p className="text-xs mt-1">上传包含身份证或学历证书的文档后，系统会自动识别提取人员信息</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {persons.map((person) => (
              <PersonCard
                key={person.id}
                person={person}
                onClick={() => handlePersonClick(person)}
              />
            ))}
          </div>

          <p className="text-xs text-gray-400 text-right">
            共 {persons.length} 人
          </p>
        </>
      )}

      {/* Person Detail Modal */}
      {selectedPerson && (
        <PersonDetailModal
          person={selectedPerson}
          onClose={handleModalClose}
          onRefresh={handleRefresh}
        />
      )}
    </div>
  );
}
