import { useState, useEffect } from 'react';
import { Clock, AlertTriangle, AlertCircle, FileText } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { getExpirySummary, getExpiringDocuments, getExpiredDocuments } from '../services/api-v2';
import type { ExpirySummary, ExpiringDocument } from '../types/dms';

interface ExpiryPageProps {
  onSelectDocument: (id: number) => void;
}

export default function ExpiryPage({ onSelectDocument }: ExpiryPageProps) {
  const [summary, setSummary] = useState<ExpirySummary | null>(null);
  const [expired, setExpired] = useState<ExpiringDocument[]>([]);
  const [expiring30, setExpiring30] = useState<ExpiringDocument[]>([]);
  const [expiring90, setExpiring90] = useState<ExpiringDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'expired' | '30d' | '90d'>('expired');

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getExpirySummary(),
      getExpiredDocuments(50),
      getExpiringDocuments(30, 50),
      getExpiringDocuments(90, 50),
    ]).then(([sum, exp, e30, e90]) => {
      setSummary(sum);
      setExpired(exp.results);
      setExpiring30(e30.results);
      setExpiring90(e90.results);
    }).catch(() => toast.error('加载到期信息失败'))
    .finally(() => setLoading(false));
  }, []);

  const tabs = [
    { key: 'expired' as const, label: '已过期', count: summary?.expired ?? 0, color: 'text-cp-rose', icon: <AlertCircle className="w-4 h-4" /> },
    { key: '30d' as const, label: '30天内到期', count: summary?.expiring_30d ?? 0, color: 'text-amber-400', icon: <AlertTriangle className="w-4 h-4" /> },
    { key: '90d' as const, label: '90天内到期', count: summary?.expiring_90d ?? 0, color: 'text-yellow-400', icon: <Clock className="w-4 h-4" /> },
  ];

  const activeList = activeTab === 'expired' ? expired : activeTab === '30d' ? expiring30 : expiring90;

  return (
    <div>
      <h2 className="text-lg font-orbitron font-semibold text-cp-text flex items-center gap-2 mb-4">
        <Clock className="w-5 h-5 text-cp-rose" />
        到期提醒
      </h2>

      {loading ? (
        <div className="text-center py-12 text-cp-dim">加载中...</div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-3 gap-4 mb-6">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                className={clsx(
                  'cp-card rounded-lg p-4 text-left transition-all',
                  activeTab === t.key && 'border-cp-purple box-glow-purple'
                )}
              >
                <div className={clsx('flex items-center gap-2 mb-1', t.color)}>
                  {t.icon}
                  <span className="text-sm font-medium">{t.label}</span>
                </div>
                <p className="text-2xl font-bold text-cp-text">{t.count}</p>
              </button>
            ))}
          </div>

          {/* Document list */}
          {activeList.length === 0 ? (
            <div className="text-center py-8 text-cp-dim">
              <FileText className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>无记录</p>
            </div>
          ) : (
            <div className="cp-card rounded-lg overflow-hidden">
              <table className="cp-table min-w-full">
                <thead>
                  <tr>
                    <th className="px-4 py-3 text-left">标题</th>
                    <th className="px-4 py-3 text-left">类型</th>
                    <th className="px-4 py-3 text-left">到期日</th>
                    <th className="px-4 py-3 text-left">剩余天数</th>
                    <th className="px-4 py-3 text-left">关联实体</th>
                  </tr>
                </thead>
                <tbody>
                  {activeList.map((doc) => (
                    <tr
                      key={doc.id}
                      onClick={() => onSelectDocument(doc.id)}
                      className="cursor-pointer"
                    >
                      <td className="px-4 py-3 text-sm text-cp-text">{doc.title}</td>
                      <td className="px-4 py-3 text-sm text-cp-muted">{doc.doc_type?.name || '-'}</td>
                      <td className="px-4 py-3 text-sm text-cp-muted">{doc.expiry_date || '-'}</td>
                      <td className="px-4 py-3 text-sm">
                        <span className={clsx(
                          doc.days_until_expiry !== null && doc.days_until_expiry < 0 ? 'text-cp-rose font-medium' :
                          doc.days_until_expiry !== null && doc.days_until_expiry <= 30 ? 'text-amber-400' : 'text-cp-muted'
                        )}>
                          {doc.days_until_expiry !== null ? (doc.days_until_expiry < 0 ? `已过期 ${Math.abs(doc.days_until_expiry)} 天` : `${doc.days_until_expiry} 天`) : '-'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-cp-dim">{doc.entity_names.join(', ') || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
