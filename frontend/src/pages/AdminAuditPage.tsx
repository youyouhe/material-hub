import { useState, useEffect, useCallback } from 'react';
import { ScrollText, ChevronLeft, ChevronRight, Filter } from 'lucide-react';
import toast from 'react-hot-toast';
import { listAuditLogs } from '../services/api-v2';
import type { AuditLog } from '../types/dms';

const ACTION_LABELS: Record<string, string> = {
  create: '创建', update: '更新', delete: '删除', status_change: '状态变更',
  download: '下载', approve: '批准', reject: '拒绝', lock: '锁定', unlock: '解锁',
};

export default function AdminAuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [actionFilter, setActionFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const limit = 30;

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { limit, offset };
      if (actionFilter) params.action = actionFilter;
      if (typeFilter) params.target_type = typeFilter;
      const data = await listAuditLogs(params as any);
      setLogs(data.results);
      setTotal(data.total);
    } catch { toast.error('加载审计日志失败'); }
    finally { setLoading(false); }
  }, [actionFilter, typeFilter, offset]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);
  useEffect(() => { setOffset(0); }, [actionFilter, typeFilter]);

  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <div>
      <h2 className="text-lg font-orbitron font-semibold text-cp-text flex items-center gap-2 mb-4">
        <ScrollText className="w-5 h-5 text-cp-purple" /> 审计日志
      </h2>

      <div className="flex gap-3 mb-4">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-cp-dim" />
          <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} className="cp-select text-sm rounded-md px-2 py-1">
            <option value="">全部操作</option>
            {Object.entries(ACTION_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="cp-select text-sm rounded-md px-2 py-1">
          <option value="">全部类型</option>
          <option value="document">文档</option>
          <option value="folder">文件夹</option>
          <option value="entity">实体</option>
          <option value="tag">标签</option>
          <option value="bid_project">投标项目</option>
        </select>
      </div>

      {loading ? (
        <div className="text-center py-12 text-cp-dim">加载中...</div>
      ) : logs.length === 0 ? (
        <div className="text-center py-12 text-cp-dim">暂无日志记录</div>
      ) : (
        <>
          <div className="cp-card rounded-lg overflow-hidden">
            <table className="cp-table min-w-full">
              <thead>
                <tr>
                  <th className="px-4 py-3 text-left">时间</th>
                  <th className="px-4 py-3 text-left">用户</th>
                  <th className="px-4 py-3 text-left">操作</th>
                  <th className="px-4 py-3 text-left">对象类型</th>
                  <th className="px-4 py-3 text-left">对象名称</th>
                  <th className="px-4 py-3 text-left">详情</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id}>
                    <td className="px-4 py-3 text-sm text-cp-dim whitespace-nowrap">{log.created_at?.slice(0, 16).replace('T', ' ')}</td>
                    <td className="px-4 py-3 text-sm text-cp-muted">{log.user_id ?? '-'}</td>
                    <td className="px-4 py-3 text-sm text-cp-text">{ACTION_LABELS[log.action] || log.action}</td>
                    <td className="px-4 py-3 text-sm text-cp-muted">{log.target_type || '-'}</td>
                    <td className="px-4 py-3 text-sm text-cp-text max-w-xs truncate">{log.target_title || '-'}</td>
                    <td className="px-4 py-3 text-sm text-cp-dim max-w-xs truncate">{log.details ? JSON.stringify(log.details) : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4 text-sm text-cp-muted">
              <span>共 {total} 条，第 {currentPage}/{totalPages} 页</span>
              <div className="flex gap-2">
                <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))} className="px-3 py-1 border border-cp-border rounded text-cp-muted hover:border-cp-purple disabled:opacity-30"><ChevronLeft className="w-4 h-4" /></button>
                <button disabled={currentPage >= totalPages} onClick={() => setOffset(offset + limit)} className="px-3 py-1 border border-cp-border rounded text-cp-muted hover:border-cp-purple disabled:opacity-30"><ChevronRight className="w-4 h-4" /></button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
