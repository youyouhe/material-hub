import { useState, useEffect, useCallback } from 'react';
import { Briefcase, Plus, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { listBids, createBid } from '../services/api-v2';
import type { BidProject } from '../types/dms';

interface BidsPageProps {
  onOpenBid: (bidId: number) => void;
}

const STATUS_LABELS: Record<string, string> = {
  planning: '筹备中', active: '进行中', submitted: '已提交', won: '已中标', lost: '未中标', cancelled: '已取消',
};

const STATUS_COLORS: Record<string, string> = {
  planning: 'bg-gray-800/30 text-gray-400',
  active: 'bg-cp-purple/20 text-cp-purple-light',
  submitted: 'bg-yellow-900/30 text-yellow-400',
  won: 'bg-green-900/30 text-green-400',
  lost: 'bg-red-900/30 text-red-400',
  cancelled: 'bg-gray-800/30 text-gray-500',
};

export default function BidsPage({ onOpenBid }: BidsPageProps) {
  const [bids, setBids] = useState<BidProject[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ name: '', bid_number: '', buyer: '', budget: '', deadline: '', description: '' });
  const limit = 20;

  const fetchBids = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { limit, offset };
      if (statusFilter) params.status = statusFilter;
      if (searchQuery.trim()) params.q = searchQuery.trim();
      const data = await listBids(params as any);
      setBids(data.results);
      setTotal(data.total);
    } catch { toast.error('加载投标项目失败'); }
    finally { setLoading(false); }
  }, [statusFilter, searchQuery, offset]);

  useEffect(() => { fetchBids(); }, [fetchBids]);
  useEffect(() => { setOffset(0); }, [statusFilter, searchQuery]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createForm.name.trim()) return;
    try {
      const bid = await createBid({
        name: createForm.name,
        bid_number: createForm.bid_number || undefined,
        buyer: createForm.buyer || undefined,
        budget: createForm.budget || undefined,
        deadline: createForm.deadline || undefined,
        description: createForm.description || undefined,
      });
      toast.success('投标项目已创建');
      setShowCreate(false);
      setCreateForm({ name: '', bid_number: '', buyer: '', budget: '', deadline: '', description: '' });
      onOpenBid(bid.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '创建失败');
    }
  };

  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-orbitron font-semibold text-cp-text flex items-center gap-2">
          <Briefcase className="w-5 h-5 text-cp-cyan" />
          投标管理
        </h2>
        <button
          onClick={() => setShowCreate(true)}
          className="cp-btn-primary flex items-center gap-1 px-3 py-2 text-sm rounded-lg"
        >
          <Plus className="w-4 h-4" /> 新建项目
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-cp-dim" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索项目名称..."
            className="cp-input w-full pl-9 pr-3 py-2 rounded-lg text-sm"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="cp-select rounded-lg px-3 py-2 text-sm"
        >
          <option value="">全部状态</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </div>

      {/* Bid list */}
      {loading ? (
        <div className="text-center py-12 text-cp-dim">加载中...</div>
      ) : bids.length === 0 ? (
        <div className="text-center py-12 text-cp-dim">
          <Briefcase className="w-12 h-12 mx-auto mb-2 opacity-50" />
          <p>暂无投标项目</p>
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {bids.map((bid) => {
              const summary = bid.requirements_summary;
              const pct = summary && summary.total > 0 ? Math.round(summary.fulfilled / summary.total * 100) : 0;
              return (
                <div
                  key={bid.id}
                  onClick={() => onOpenBid(bid.id)}
                  className="cp-card rounded-lg p-4 cursor-pointer"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-cp-text">{bid.name}</span>
                      <span className={clsx('px-2 py-0.5 text-xs rounded-full', STATUS_COLORS[bid.status] || 'bg-gray-800/30 text-gray-400')}>
                        {STATUS_LABELS[bid.status] || bid.status}
                      </span>
                    </div>
                    {bid.deadline && <span className="text-sm text-cp-muted">截止: {bid.deadline}</span>}
                  </div>
                  <div className="flex items-center gap-4 text-sm text-cp-dim">
                    {bid.bid_number && <span>编号: {bid.bid_number}</span>}
                    {bid.buyer && <span>采购方: {bid.buyer}</span>}
                    {bid.budget && <span>预算: {bid.budget}</span>}
                  </div>
                  {summary && summary.total > 0 && (
                    <div className="mt-3">
                      <div className="flex items-center justify-between text-xs text-cp-dim mb-1">
                        <span>需求满足度</span>
                        <span>{summary.fulfilled}/{summary.total} ({pct}%)</span>
                      </div>
                      <div className="w-full bg-white/5 rounded-full h-2">
                        <div
                          className={clsx('h-2 rounded-full transition-all', pct === 100 ? 'bg-green-500' : pct > 50 ? 'bg-cp-purple' : 'bg-amber-500')}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
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

      {/* Create modal */}
      {showCreate && (
        <div className="cp-overlay fixed inset-0 flex items-center justify-center z-50">
          <div className="cp-card rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-orbitron font-semibold text-cp-text mb-4">新建投标项目</h3>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">项目名称 *</label>
                <input value={createForm.name} onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })} className="cp-input w-full rounded-md px-3 py-2 text-sm" required />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-cp-muted mb-1">投标编号</label>
                  <input value={createForm.bid_number} onChange={(e) => setCreateForm({ ...createForm, bid_number: e.target.value })} className="cp-input w-full rounded-md px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-cp-muted mb-1">采购方</label>
                  <input value={createForm.buyer} onChange={(e) => setCreateForm({ ...createForm, buyer: e.target.value })} className="cp-input w-full rounded-md px-3 py-2 text-sm" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-cp-muted mb-1">预算</label>
                  <input value={createForm.budget} onChange={(e) => setCreateForm({ ...createForm, budget: e.target.value })} className="cp-input w-full rounded-md px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-cp-muted mb-1">截止日期</label>
                  <input type="date" value={createForm.deadline} onChange={(e) => setCreateForm({ ...createForm, deadline: e.target.value })} className="cp-input w-full rounded-md px-3 py-2 text-sm" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">描述</label>
                <textarea value={createForm.description} onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })} rows={2} className="cp-input w-full rounded-md px-3 py-2 text-sm" />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setShowCreate(false)} className="cp-btn-ghost px-4 py-2 text-sm rounded-md">取消</button>
                <button type="submit" className="cp-btn-primary px-4 py-2 text-sm rounded-md">创建</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
