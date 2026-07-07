import { useState, useEffect, useCallback } from 'react';
import { ArrowLeft, Briefcase, Edit3, Save, XCircle, UserPlus, Trash2, Plus } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import {
  getBid, updateBid, updateBidStatus, deleteBid,
  listTeamMembers, addTeamMember, removeTeamMember,
  createRequirementsFromCategory, listDocTypes,
} from '../services/api-v2';
import type { BidProject, BidTeamMember, DocType } from '../types/dms';
import BidChecklist from '../components/BidChecklist';

interface BidDetailPageProps {
  bidId: number;
  userRole: string;
  onBack: () => void;
}

const STATUS_LABELS: Record<string, string> = {
  planning: '筹备中', active: '进行中', submitted: '已提交', won: '已中标', lost: '未中标', cancelled: '已取消',
};
const STATUS_COLORS: Record<string, string> = {
  planning: 'bg-gray-800/30 text-gray-400', active: 'bg-cp-purple/20 text-cp-purple-light', submitted: 'bg-yellow-900/30 text-yellow-400',
  won: 'bg-green-900/30 text-green-400', lost: 'bg-red-900/30 text-red-400', cancelled: 'bg-gray-800/30 text-gray-500',
};
const TRANSITIONS: Record<string, string[]> = {
  planning: ['active'], active: ['submitted'], submitted: ['won', 'lost', 'cancelled'],
};

export default function BidDetailPage({ bidId, userRole, onBack }: BidDetailPageProps) {
  const [bid, setBid] = useState<BidProject | null>(null);
  const [team, setTeam] = useState<BidTeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: '', bid_number: '', buyer: '', budget: '', deadline: '', description: '' });
  const [showAddTeam, setShowAddTeam] = useState(false);
  const [teamForm, setTeamForm] = useState({ entity_id: '', role: '' });
  const [categories, setCategories] = useState<string[]>([]);
  const [showBulkReq, setShowBulkReq] = useState(false);

  const canEdit = userRole === 'editor' || userRole === 'admin';

  const fetchBid = useCallback(async () => {
    try {
      const [bidData, teamData] = await Promise.all([getBid(bidId), listTeamMembers(bidId)]);
      setBid(bidData);
      setTeam(teamData.team_members);
      setEditForm({
        name: bidData.name, bid_number: bidData.bid_number || '', buyer: bidData.buyer || '',
        budget: bidData.budget || '', deadline: bidData.deadline || '', description: bidData.description || '',
      });
    } catch { toast.error('加载投标项目失败'); }
    finally { setLoading(false); }
  }, [bidId]);

  useEffect(() => { fetchBid(); }, [fetchBid]);

  useEffect(() => {
    listDocTypes().then((data) => {
      setCategories(Object.keys(data.doc_types));
    }).catch(() => {});
  }, []);

  const handleSave = async () => {
    try {
      const updated = await updateBid(bidId, {
        name: editForm.name, bid_number: editForm.bid_number || null, buyer: editForm.buyer || null,
        budget: editForm.budget || null, deadline: editForm.deadline || null, description: editForm.description || null,
      });
      setBid(updated);
      setEditing(false);
      toast.success('已更新');
    } catch { toast.error('更新失败'); }
  };

  const handleStatusChange = async (status: string) => {
    if (!confirm(`确定要将状态改为 "${STATUS_LABELS[status] || status}"？`)) return;
    try {
      const updated = await updateBidStatus(bidId, { status });
      setBid(updated);
      toast.success('状态已更新');
    } catch (err) { toast.error(err instanceof Error ? err.message : '状态更新失败'); }
  };

  const handleDelete = async () => {
    if (!confirm('确定要删除此投标项目？此操作不可撤销。')) return;
    try {
      await deleteBid(bidId);
      toast.success('已删除');
      onBack();
    } catch { toast.error('删除失败'); }
  };

  const handleAddTeam = async () => {
    if (!teamForm.entity_id || !teamForm.role) return;
    try {
      await addTeamMember(bidId, { entity_id: Number(teamForm.entity_id), role: teamForm.role });
      toast.success('团队成员已添加');
      setShowAddTeam(false);
      setTeamForm({ entity_id: '', role: '' });
      const data = await listTeamMembers(bidId);
      setTeam(data.team_members);
    } catch (err) { toast.error(err instanceof Error ? err.message : '添加失败'); }
  };

  const handleRemoveTeam = async (memberId: number) => {
    if (!confirm('确定要移除此团队成员？')) return;
    try {
      await removeTeamMember(bidId, memberId);
      setTeam(team.filter((m) => m.id !== memberId));
      toast.success('已移除');
    } catch { toast.error('移除失败'); }
  };

  const handleBulkCreate = async (category: string) => {
    try {
      const result = await createRequirementsFromCategory(bidId, category);
      toast.success(`已创建 ${result.total} 条需求${result.skipped > 0 ? `，跳过 ${result.skipped} 条` : ''}`);
      setShowBulkReq(false);
    } catch (err) { toast.error(err instanceof Error ? err.message : '批量创建失败'); }
  };

  if (loading) return <div className="text-center py-12 text-cp-dim">加载中...</div>;
  if (!bid) return <div className="text-center py-12 text-cp-dim">项目未找到</div>;

  const allowedTransitions = TRANSITIONS[bid.status] || [];

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={onBack} className="p-1 rounded cp-hover"><ArrowLeft className="w-5 h-5 text-cp-dim" /></button>
        <Briefcase className="w-5 h-5 text-cp-cyan" />
        <h2 className="text-lg font-orbitron font-semibold text-cp-text flex-1">{bid.name}</h2>
        <span className={clsx('px-2 py-1 text-xs rounded-full', STATUS_COLORS[bid.status])}>{STATUS_LABELS[bid.status] || bid.status}</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Info + Team */}
        <div className="lg:col-span-1 space-y-4">
          {/* Project info */}
          <div className="cp-card rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-cp-purple-light">项目信息</h3>
              {canEdit && !editing && (
                <button onClick={() => setEditing(true)} className="text-cp-dim hover:text-cp-text">
                  <Edit3 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            {editing ? (
              <div className="space-y-2">
                <input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} placeholder="项目名称" className="cp-input w-full rounded px-2 py-1 text-sm" />
                <input value={editForm.bid_number} onChange={(e) => setEditForm({ ...editForm, bid_number: e.target.value })} placeholder="投标编号" className="cp-input w-full rounded px-2 py-1 text-sm" />
                <input value={editForm.buyer} onChange={(e) => setEditForm({ ...editForm, buyer: e.target.value })} placeholder="采购方" className="cp-input w-full rounded px-2 py-1 text-sm" />
                <input value={editForm.budget} onChange={(e) => setEditForm({ ...editForm, budget: e.target.value })} placeholder="预算" className="cp-input w-full rounded px-2 py-1 text-sm" />
                <input type="date" value={editForm.deadline} onChange={(e) => setEditForm({ ...editForm, deadline: e.target.value })} className="cp-input w-full rounded px-2 py-1 text-sm" />
                <textarea value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} placeholder="描述" rows={2} className="cp-input w-full rounded px-2 py-1 text-sm" />
                <div className="flex gap-2">
                  <button onClick={handleSave} className="cp-btn-primary px-3 py-1 text-sm rounded"><Save className="w-3.5 h-3.5 inline mr-1" />保存</button>
                  <button onClick={() => setEditing(false)} className="cp-btn-ghost px-3 py-1 text-sm rounded"><XCircle className="w-3.5 h-3.5 inline mr-1" />取消</button>
                </div>
              </div>
            ) : (
              <div className="space-y-2 text-sm">
                {bid.bid_number && <div className="flex justify-between"><span className="text-cp-dim">编号</span><span className="text-cp-text">{bid.bid_number}</span></div>}
                {bid.buyer && <div className="flex justify-between"><span className="text-cp-dim">采购方</span><span className="text-cp-text">{bid.buyer}</span></div>}
                {bid.budget && <div className="flex justify-between"><span className="text-cp-dim">预算</span><span className="text-cp-text">{bid.budget}</span></div>}
                {bid.deadline && <div className="flex justify-between"><span className="text-cp-dim">截止日期</span><span className="text-cp-text">{bid.deadline}</span></div>}
                {bid.description && <div><span className="text-cp-dim">描述</span><p className="text-cp-muted mt-1">{bid.description}</p></div>}
              </div>
            )}
          </div>

          {/* Status transitions */}
          {canEdit && allowedTransitions.length > 0 && (
            <div className="cp-card rounded-lg p-4">
              <h3 className="text-sm font-semibold text-cp-purple-light mb-2">状态变更</h3>
              <div className="flex flex-wrap gap-2">
                {allowedTransitions.map((s) => (
                  <button key={s} onClick={() => handleStatusChange(s)} className={clsx('px-3 py-1 text-xs rounded-full border border-cp-border', STATUS_COLORS[s])}>
                    {STATUS_LABELS[s] || s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Team */}
          <div className="cp-card rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-cp-purple-light">团队成员</h3>
              {canEdit && (
                <button onClick={() => setShowAddTeam(true)} className="text-cp-cyan hover:text-cyan-300">
                  <UserPlus className="w-4 h-4" />
                </button>
              )}
            </div>
            {team.length === 0 ? (
              <p className="text-sm text-cp-dim">暂无成员</p>
            ) : (
              <div className="space-y-2">
                {team.map((m) => (
                  <div key={m.id} className="flex items-center justify-between text-sm">
                    <div>
                      <span className="text-cp-text">{m.entity_name || `实体 #${m.entity_id}`}</span>
                      <span className="text-xs text-cp-dim ml-2">({m.role})</span>
                    </div>
                    {canEdit && (
                      <button onClick={() => handleRemoveTeam(m.id)} className="text-cp-dim hover:text-cp-rose">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Add team modal */}
          {showAddTeam && (
            <div className="cp-overlay fixed inset-0 flex items-center justify-center z-50">
              <div className="cp-card rounded-lg p-6 w-full max-w-sm">
                <h3 className="text-lg font-orbitron font-semibold text-cp-text mb-4">添加团队成员</h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-cp-muted mb-1">实体 ID</label>
                    <input value={teamForm.entity_id} onChange={(e) => setTeamForm({ ...teamForm, entity_id: e.target.value })} className="cp-input w-full rounded-md px-3 py-2 text-sm" placeholder="输入实体ID" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-cp-muted mb-1">角色</label>
                    <input value={teamForm.role} onChange={(e) => setTeamForm({ ...teamForm, role: e.target.value })} className="cp-input w-full rounded-md px-3 py-2 text-sm" placeholder="如：项目经理、技术负责人" />
                  </div>
                </div>
                <div className="flex justify-end gap-2 mt-4">
                  <button onClick={() => setShowAddTeam(false)} className="cp-btn-ghost px-4 py-2 text-sm rounded-md">取消</button>
                  <button onClick={handleAddTeam} className="cp-btn-primary px-4 py-2 text-sm rounded-md">添加</button>
                </div>
              </div>
            </div>
          )}

          {/* Actions */}
          {canEdit && (
            <div className="space-y-2">
              <button onClick={() => setShowBulkReq(true)} className="cp-btn-ghost w-full flex items-center justify-center gap-1 px-3 py-2 text-sm rounded-lg">
                <Plus className="w-4 h-4" /> 按类别批量添加需求
              </button>
              <button onClick={handleDelete} className="w-full flex items-center justify-center gap-1 px-3 py-2 text-sm border border-cp-rose/30 text-cp-rose rounded-lg hover:bg-cp-rose/10 transition-colors">
                <Trash2 className="w-4 h-4" /> 删除项目
              </button>
            </div>
          )}

          {/* Bulk create modal */}
          {showBulkReq && (
            <div className="cp-overlay fixed inset-0 flex items-center justify-center z-50">
              <div className="cp-card rounded-lg p-6 w-full max-w-sm">
                <h3 className="text-lg font-orbitron font-semibold text-cp-text mb-4">按类别添加需求</h3>
                <div className="space-y-2">
                  {categories.map((cat) => (
                    <button key={cat} onClick={() => handleBulkCreate(cat)} className="w-full text-left px-3 py-2 text-sm text-cp-text border border-cp-border rounded-lg hover:bg-cp-purple/10 hover:border-cp-purple transition-colors">
                      {cat}
                    </button>
                  ))}
                </div>
                <div className="flex justify-end mt-4">
                  <button onClick={() => setShowBulkReq(false)} className="cp-btn-ghost px-4 py-2 text-sm rounded-md">关闭</button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right: Checklist */}
        <div className="lg:col-span-2">
          <BidChecklist bidId={bidId} userRole={userRole} />
        </div>
      </div>
    </div>
  );
}
