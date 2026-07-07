import { useState, useEffect, useCallback } from 'react';
import { Shield, Plus, Edit3, FolderOpen, Check } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { listUsers, createUser, updateUserRole, resetUserPassword, getFolderTree, setUserFolders } from '../services/api-v2';
import type { AdminUser, FolderTreeNode } from '../types/dms';

const ROLE_LABELS: Record<string, string> = { admin: '管理员', editor: '编辑', viewer: '查看者' };
const ROLE_COLORS: Record<string, string> = { admin: 'bg-cp-rose/20 text-cp-rose', editor: 'bg-cp-purple/20 text-cp-purple-light', viewer: 'bg-gray-800/30 text-gray-400' };

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

function FolderAccessEditor({ user, folders, onSaved }: { user: AdminUser; folders: FolderTreeNode[]; onSaved: () => void }) {
  const [selected, setSelected] = useState<Set<number>>(new Set(user.folder_ids || []));
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
      await setUserFolders(user.id, Array.from(selected));
      toast.success(`已更新 ${user.username} 的文件夹权限`);
      onSaved();
    } catch { toast.error('保存失败'); }
    finally { setSaving(false); }
  };

  const hasChanges = (() => {
    const orig = new Set(user.folder_ids || []);
    if (orig.size !== selected.size) return true;
    for (const id of selected) if (!orig.has(id)) return true;
    return false;
  })();

  return (
    <div className="cp-card rounded-lg p-4 mt-2">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-medium text-cp-purple-light flex items-center gap-1">
          <FolderOpen className="w-4 h-4" /> {user.username} 的文件夹权限
        </h4>
        <div className="flex items-center gap-2">
          <span className="text-xs text-cp-dim">已选 {selected.size} 个文件夹</span>
          {hasChanges && (
            <button
              onClick={handleSave}
              disabled={saving}
              className="cp-btn-primary flex items-center gap-1 px-2.5 py-1 text-xs rounded"
            >
              <Check className="w-3 h-3" /> {saving ? '保存中...' : '保存'}
            </button>
          )}
        </div>
      </div>
      {user.role === 'admin' ? (
        <p className="text-sm text-cp-dim">管理员拥有所有文件夹的访问权限，无需配置。</p>
      ) : flat.length === 0 ? (
        <p className="text-sm text-cp-dim">暂无文件夹，请先在文件夹管理中创建。</p>
      ) : (
        <div className="space-y-0.5 max-h-60 overflow-y-auto">
          {flat.map(({ node, depth }) => (
            <label
              key={node.id}
              className="flex items-center gap-2 px-2 py-1 rounded cp-hover cursor-pointer text-sm"
              style={{ paddingLeft: `${depth * 20 + 8}px` }}
            >
              <input
                type="checkbox"
                checked={selected.has(node.id)}
                onChange={() => toggle(node.id)}
                className="accent-cp-purple rounded"
              />
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

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ username: '', password: '', role: 'editor' });
  const [editingRole, setEditingRole] = useState<number | null>(null);
  const [editingFolders, setEditingFolders] = useState<number | null>(null);
  const [folders, setFolders] = useState<FolderTreeNode[]>([]);

  const fetchUsers = useCallback(async () => {
    try {
      const data = await listUsers();
      setUsers(data.users);
    } catch { toast.error('加载用户列表失败'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  useEffect(() => {
    getFolderTree().then(setFolders).catch(() => {});
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createUser(createForm);
      toast.success('用户已创建');
      setShowCreate(false);
      setCreateForm({ username: '', password: '', role: 'editor' });
      fetchUsers();
    } catch (err) { toast.error(err instanceof Error ? err.message : '创建失败'); }
  };

  const handleRoleChange = async (userId: number, role: string) => {
    try {
      await updateUserRole(userId, role);
      toast.success('角色已更新');
      setEditingRole(null);
      fetchUsers();
    } catch (err) { toast.error(err instanceof Error ? err.message : '更新失败'); }
  };

  const handleResetPassword = async (userId: number) => {
    const pw = prompt('输入新密码:');
    if (!pw) return;
    try {
      await resetUserPassword(userId, pw);
      toast.success('密码已重置');
    } catch { toast.error('重置失败'); }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-orbitron font-semibold text-cp-text flex items-center gap-2">
          <Shield className="w-5 h-5 text-cp-rose" /> 用户管理
        </h2>
        <button onClick={() => setShowCreate(true)} className="cp-btn-primary flex items-center gap-1 px-3 py-2 text-sm rounded-lg">
          <Plus className="w-4 h-4" /> 新建用户
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-cp-dim">加载中...</div>
      ) : (
        <div className="space-y-2">
          <div className="cp-card rounded-lg overflow-hidden">
            <table className="cp-table min-w-full">
              <thead>
                <tr>
                  <th className="px-4 py-3 text-left">ID</th>
                  <th className="px-4 py-3 text-left">用户名</th>
                  <th className="px-4 py-3 text-left">角色</th>
                  <th className="px-4 py-3 text-left">文件夹权限</th>
                  <th className="px-4 py-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td className="px-4 py-3 text-sm text-cp-dim">{u.id}</td>
                    <td className="px-4 py-3 text-sm text-cp-text font-medium">{u.username}</td>
                    <td className="px-4 py-3">
                      {editingRole === u.id ? (
                        <select
                          defaultValue={u.role}
                          onChange={(e) => handleRoleChange(u.id, e.target.value)}
                          onBlur={() => setEditingRole(null)}
                          autoFocus
                          className="cp-select text-sm rounded px-2 py-1"
                        >
                          <option value="admin">管理员</option>
                          <option value="editor">编辑</option>
                          <option value="viewer">查看者</option>
                        </select>
                      ) : (
                        <span className={clsx('px-2 py-0.5 text-xs rounded-full cursor-pointer', ROLE_COLORS[u.role])} onClick={() => setEditingRole(u.id)}>
                          {ROLE_LABELS[u.role] || u.role}
                          <Edit3 className="w-3 h-3 inline ml-1 opacity-50" />
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {u.role === 'admin' ? (
                        <span className="text-xs text-cp-dim">全部</span>
                      ) : (
                        <button
                          onClick={() => setEditingFolders(editingFolders === u.id ? null : u.id)}
                          className={clsx(
                            'flex items-center gap-1 text-xs px-2 py-0.5 rounded border transition-colors',
                            editingFolders === u.id
                              ? 'border-cp-purple text-cp-purple-light bg-cp-purple/10'
                              : 'border-cp-border text-cp-dim hover:text-cp-text hover:border-cp-purple/50',
                          )}
                        >
                          <FolderOpen className="w-3 h-3" />
                          {(u.folder_ids?.length || 0) > 0 ? `${u.folder_ids!.length} 个文件夹` : '未配置'}
                        </button>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => handleResetPassword(u.id)} className="text-sm text-cp-cyan hover:underline">
                        重置密码
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Folder access editor panel */}
          {editingFolders && (() => {
            const user = users.find(u => u.id === editingFolders);
            if (!user || user.role === 'admin') return null;
            return (
              <FolderAccessEditor
                key={user.id}
                user={user}
                folders={folders}
                onSaved={() => { setEditingFolders(null); fetchUsers(); }}
              />
            );
          })()}
        </div>
      )}

      {showCreate && (
        <div className="cp-overlay fixed inset-0 flex items-center justify-center z-50">
          <div className="cp-card rounded-lg p-6 w-full max-w-sm">
            <h3 className="text-lg font-orbitron font-semibold text-cp-text mb-4">新建用户</h3>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">用户名</label>
                <input value={createForm.username} onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })} className="cp-input w-full rounded-md px-3 py-2 text-sm" required />
              </div>
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">密码</label>
                <input type="password" value={createForm.password} onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })} className="cp-input w-full rounded-md px-3 py-2 text-sm" required />
              </div>
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">角色</label>
                <select value={createForm.role} onChange={(e) => setCreateForm({ ...createForm, role: e.target.value })} className="cp-select w-full rounded-md px-3 py-2 text-sm">
                  <option value="admin">管理员</option>
                  <option value="editor">编辑</option>
                  <option value="viewer">查看者</option>
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
