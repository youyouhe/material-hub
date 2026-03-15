import { useState, useEffect } from 'react';
import { Database, RefreshCw, ArrowRight, CheckCircle2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { getMigrationStatus, migrateCompanies, migratePersons, migrateMaterials } from '../services/api-v2';
import type { MigrationStatus } from '../types/dms';

export default function AdminMigratePage() {
  const [status, setStatus] = useState<MigrationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [migrating, setMigrating] = useState<string | null>(null);

  const fetchStatus = async () => {
    setLoading(true);
    try {
      const data = await getMigrationStatus();
      setStatus(data);
    } catch { toast.error('加载迁移状态失败'); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchStatus(); }, []);

  const handleMigrate = async (type: 'companies' | 'persons' | 'materials') => {
    setMigrating(type);
    try {
      const fns = { companies: migrateCompanies, persons: migratePersons, materials: migrateMaterials };
      const result = await fns[type]();
      toast.success(`迁移完成: 创建 ${result.created}, 跳过 ${result.skipped}, 总计 ${result.total}`);
      if ('warnings' in result && (result as any).warnings?.length > 0) {
        toast(`${(result as any).warnings.length} 条警告`, { icon: '⚠️' });
      }
      fetchStatus();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '迁移失败');
    } finally { setMigrating(null); }
  };

  const items = status ? [
    { key: 'companies' as const, label: '公司 → 实体(组织)', legacy: status.companies.legacy, migrated: status.companies.migrated },
    { key: 'persons' as const, label: '人员 → 实体(个人)', legacy: status.persons.legacy, migrated: status.persons.migrated },
    { key: 'materials' as const, label: '素材 → DMS文档', legacy: status.materials.legacy, migrated: status.materials.migrated },
  ] : [];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-orbitron font-semibold text-cp-text flex items-center gap-2">
          <Database className="w-5 h-5 text-cp-cyan" /> 数据迁移
        </h2>
        <button onClick={fetchStatus} className="text-sm text-cp-dim hover:text-cp-text flex items-center gap-1">
          <RefreshCw className="w-3.5 h-3.5" /> 刷新状态
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-cp-dim">加载中...</div>
      ) : (
        <div className="space-y-4">
          {items.map((item) => {
            const done = item.legacy > 0 && item.migrated >= item.legacy;
            return (
              <div key={item.key} className="cp-card rounded-lg p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-medium text-cp-text">{item.label}</h3>
                  {done && <CheckCircle2 className="w-5 h-5 text-green-400" />}
                </div>
                <div className="flex items-center gap-8 mb-3">
                  <div>
                    <span className="text-2xl font-bold text-cp-text">{item.legacy}</span>
                    <span className="text-sm text-cp-dim ml-1">旧版记录</span>
                  </div>
                  <ArrowRight className="w-5 h-5 text-cp-dim" />
                  <div>
                    <span className="text-2xl font-bold text-cp-cyan">{item.migrated}</span>
                    <span className="text-sm text-cp-dim ml-1">已迁移</span>
                  </div>
                </div>
                <button
                  onClick={() => handleMigrate(item.key)}
                  disabled={migrating !== null}
                  className="cp-btn-primary px-4 py-2 text-sm rounded-lg"
                >
                  {migrating === item.key ? '迁移中...' : done ? '重新迁移' : '开始迁移'}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
