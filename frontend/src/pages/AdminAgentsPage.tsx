import { useState, useEffect, useCallback } from 'react';
import { Bot, Plus, Trash2, RefreshCw, Copy, FolderOpen, Check, Power } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { listAgents, createAgent, updateAgent, deleteAgent, regenerateAgentToken, setAgentFolders, getFolderTree } from '../services/api-v2';
import type { ApiAgent, FolderTreeNode } from '../types/dms';

function flattenFolders(nodes: FolderTreeNode[], depth = 0): { node: FolderTreeNode; depth: number }[] {
  const result: { node: FolderTreeNode; depth: number }[] = [];
  for (const n of nodes) {
    result.push({ node: n, depth });
    if (n.children?.length) {
      result.push(...flattenFolders(n.children, depth + 1));
    }
  }
  return result;
}

function AgentFolderEditor({ agent, folders, onSaved }: { agent: ApiAgent; folders: FolderTreeNode[]; onSaved: () => void }) {
  const [selected, setSelected] = useState<Set<number>>(new Set(agent.folder_ids || []));
  const [saving, setSaving] = useState(false);
  const flat = flattenFolders(folders);

  const toggle = (id: number) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await setAgentFolders(agent.id, Array.from(selected));
      toast.success(`已更新 ${agent.name} 的文件夹权限`);
      onSaved();
    } catch { toast.error('保存失败'); }
    finally { setSaving(false); }
  };

  const hasChanges = (() => {
    const orig = new Set(agent.folder_ids || []);
    if (orig.size !== selected.size) return true;
    for (const id of selected) if (!orig.has(id)) return true;
    return false;
  })();

  return (
    <div className="cp-card rounded-lg p-4 mt-2">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-medium text-cp-purple-light flex items-center gap-1">
          <FolderOpen className="w-4 h-4" /> {agent.name} 的文件夹权限
        </h4>
        <div className="flex items-center gap-2">
          <span className="text-xs text-cp-dim">已选 {selected.size} 个文件夹</span>
          {hasChanges && (
            <button onClick={handleSave} disabled={saving} className="cp-btn-primary flex items-center gap-1 px-2.5 py-1 text-xs rounded">
              <Check className="w-3 h-3" /> {saving ? '保存中...' : '保存'}
            </button>
          )}
        </div>
      </div>
      {agent.role === 'admin' ? (
        <p className="text-sm text-cp-dim">管理员角色拥有所有文件夹的访问权限，无需配置。</p>
      ) : flat.length === 0 ? (
        <p className="text-sm text-cp-dim">暂无文件夹，请先在文件夹管理中创建。</p>
      ) : (
        <div className="space-y-0.5 max-h-60 overflow-y-auto">
          {flat.map(({ node, depth }) => (
            <label key={node.id} className="flex items-center gap-2 px-2 py-1 rounded cp-hover cursor-pointer text-sm" style={{ paddingLeft: `${depth * 20 + 8}px` }}>
              <input type="checkbox" checked={selected.has(node.id)} onChange={() => toggle(node.id)} className="accent-cp-purple rounded" />
              <FolderOpen className="w-3.5 h-3.5 text-cp-dim shrink-0" />
              <span className="text-cp-text">{node.name}</span>
              <span className="text-xs text-cp-dim ml-auto">{node.path}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AdminAgentsPage() {
  const [agents, setAgents] = useState<ApiAgent[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ name: '', role: 'viewer', description: '' });
  const [newToken, setNewToken] = useState<string | null>(null);
  const [editingFolders, setEditingFolders] = useState<number | null>(null);
  const [folders, setFolders] = useState<FolderTreeNode[]>([]);

  const fetchAgents = useCallback(async () => {
    try {
      const data = await listAgents();
      setAgents(data.agents);
    } catch { toast.error('加载Agent列表失败'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAgents(); }, [fetchAgents]);
  useEffect(() => { getFolderTree().then(setFolders).catch(() => {}); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const agent = await createAgent(createForm);
      setNewToken(agent.token || null);
      toast.success('Agent已创建');
      setCreateForm({ name: '', role: 'viewer', description: '' });
      if (!agent.token) setShowCreate(false);
      fetchAgents();
    } catch (err) { toast.error(err instanceof Error ? err.message : '创建失败'); }
  };

  const handleDelete = async (agent: ApiAgent) => {
    if (!confirm(`确定要删除 Agent「${agent.name}」吗？使用该Token的集成将立即失效。`)) return;
    try {
      await deleteAgent(agent.id);
      toast.success('Agent已删除');
      fetchAgents();
    } catch { toast.error('删除失败'); }
  };

  const handleRegenerate = async (agent: ApiAgent) => {
    if (!confirm(`确定要重新生成「${agent.name}」的Token吗？旧Token将立即失效。`)) return;
    try {
      const result = await regenerateAgentToken(agent.id);
      setNewToken(result.token);
      toast.success('Token已重新生成');
      fetchAgents();
    } catch { toast.error('重新生成失败'); }
  };

  const handleToggleActive = async (agent: ApiAgent) => {
    try {
      await updateAgent(agent.id, { is_active: !agent.is_active });
      toast.success(agent.is_active ? '已禁用' : '已启用');
      fetchAgents();
    } catch { toast.error('操作失败'); }
  };

  const handleRoleChange = async (agentId: number, role: string) => {
    try {
      await updateAgent(agentId, { role });
      toast.success('角色已更新');
      fetchAgents();
    } catch { toast.error('更新失败'); }
  };

  const copyToken = (token: string) => {
    navigator.clipboard.writeText(token);
    toast.success('Token已复制到剪贴板');
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-orbitron font-semibold text-cp-text flex items-center gap-2">
          <Bot className="w-5 h-5 text-cp-cyan" /> Agent 管理
        </h2>
        <button onClick={() => { setShowCreate(true); setNewToken(null); }} className="cp-btn-primary flex items-center gap-1 px-3 py-2 text-sm rounded-lg">
          <Plus className="w-4 h-4" /> 新建 Agent
        </button>
      </div>

      <p className="text-sm text-cp-dim mb-4">
        创建 API Agent 用于 MCP 服务器和外部集成。每个 Agent 有独立的 Token 和文件夹访问权限。
      </p>

      {/* Token display banner */}
      {newToken && (
        <div className="cp-card rounded-lg p-4 mb-4 border border-cp-cyan/30 bg-cp-cyan/5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-cp-cyan">新生成的 Token（仅显示一次，请立即复制）</span>
            <button onClick={() => setNewToken(null)} className="text-xs text-cp-dim hover:text-cp-text">关闭</button>
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-black/30 rounded px-3 py-2 text-sm text-cp-text font-mono break-all select-all">{newToken}</code>
            <button onClick={() => copyToken(newToken)} className="cp-btn-primary flex items-center gap-1 px-3 py-2 text-sm rounded shrink-0">
              <Copy className="w-4 h-4" /> 复制
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-cp-dim">加载中...</div>
      ) : agents.length === 0 ? (
        <div className="text-center py-12 text-cp-dim">
          <Bot className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>暂无 Agent，点击上方按钮创建。</p>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="cp-card rounded-lg overflow-hidden">
            <table className="cp-table min-w-full">
              <thead>
                <tr>
                  <th className="px-4 py-3 text-left">名称</th>
                  <th className="px-4 py-3 text-left">Token</th>
                  <th className="px-4 py-3 text-left">角色</th>
                  <th className="px-4 py-3 text-left">文件夹权限</th>
                  <th className="px-4 py-3 text-left">状态</th>
                  <th className="px-4 py-3 text-left">最后使用</th>
                  <th className="px-4 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((a) => (
                  <tr key={a.id} className={clsx(!a.is_active && 'opacity-50')}>
                    <td className="px-4 py-3">
                      <div className="text-sm text-cp-text font-medium">{a.name}</div>
                      {a.description && <div className="text-xs text-cp-dim mt-0.5">{a.description}</div>}
                    </td>
                    <td className="px-4 py-3">
                      <code className="text-xs text-cp-dim font-mono">{a.token_preview}</code>
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={a.role}
                        onChange={(e) => handleRoleChange(a.id, e.target.value)}
                        className="cp-select text-xs rounded px-2 py-1"
                      >
                        <option value="admin">管理员</option>
                        <option value="editor">编辑</option>
                        <option value="viewer">查看者</option>
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      {a.role === 'admin' ? (
                        <span className="text-xs text-cp-dim">全部</span>
                      ) : (
                        <button
                          onClick={() => setEditingFolders(editingFolders === a.id ? null : a.id)}
                          className={clsx(
                            'flex items-center gap-1 text-xs px-2 py-0.5 rounded border transition-colors',
                            editingFolders === a.id
                              ? 'border-cp-purple text-cp-purple-light bg-cp-purple/10'
                              : 'border-cp-border text-cp-dim hover:text-cp-text hover:border-cp-purple/50',
                          )}
                        >
                          <FolderOpen className="w-3 h-3" />
                          {(a.folder_ids?.length || 0) > 0 ? `${a.folder_ids.length} 个文件夹` : '未配置'}
                        </button>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <button onClick={() => handleToggleActive(a)} className={clsx('flex items-center gap-1 text-xs px-2 py-0.5 rounded-full', a.is_active ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400')}>
                        <Power className="w-3 h-3" />
                        {a.is_active ? '已启用' : '已禁用'}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-xs text-cp-dim">
                      {a.last_used_at ? new Date(a.last_used_at).toLocaleString('zh-CN') : '从未'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button onClick={() => handleRegenerate(a)} className="text-cp-cyan hover:text-cp-text" title="重新生成Token">
                          <RefreshCw className="w-4 h-4" />
                        </button>
                        <button onClick={() => handleDelete(a)} className="text-red-400 hover:text-red-300" title="删除">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Folder access editor panel */}
          {editingFolders && (() => {
            const agent = agents.find(a => a.id === editingFolders);
            if (!agent || agent.role === 'admin') return null;
            return (
              <AgentFolderEditor
                key={agent.id}
                agent={agent}
                folders={folders}
                onSaved={() => { setEditingFolders(null); fetchAgents(); }}
              />
            );
          })()}
        </div>
      )}

      {/* Create dialog */}
      {showCreate && !newToken && (
        <div className="cp-overlay fixed inset-0 flex items-center justify-center z-50">
          <div className="cp-card rounded-lg p-6 w-full max-w-sm">
            <h3 className="text-lg font-orbitron font-semibold text-cp-text mb-4 flex items-center gap-2">
              <Bot className="w-5 h-5 text-cp-cyan" /> 新建 Agent
            </h3>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">名称</label>
                <input
                  value={createForm.name}
                  onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                  placeholder="如: MCP-Claude、投标助手"
                  className="cp-input w-full rounded-md px-3 py-2 text-sm"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">描述（可选）</label>
                <input
                  value={createForm.description}
                  onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                  placeholder="用途说明"
                  className="cp-input w-full rounded-md px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">角色</label>
                <select value={createForm.role} onChange={(e) => setCreateForm({ ...createForm, role: e.target.value })} className="cp-select w-full rounded-md px-3 py-2 text-sm">
                  <option value="viewer">查看者（只读）</option>
                  <option value="editor">编辑（读写）</option>
                  <option value="admin">管理员（全部权限）</option>
                </select>
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
