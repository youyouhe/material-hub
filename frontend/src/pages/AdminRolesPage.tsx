import { useState, useEffect } from 'react';
import { Shield, Plus, Trash2, RefreshCw, Save, X, FolderOpen } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  listRoles, createRole, deleteRole,
  getRoleFolderPermissions, setRoleFolderPermissions,
  getFolderTree, syncRoleAgents,
} from '../services/api-v2';
import type { DmsRoleInfo, FolderPermission } from '../services/api-v2';

export default function AdminRolesPage() {
  const [roles, setRoles] = useState<DmsRoleInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRole, setSelectedRole] = useState<DmsRoleInfo | null>(null);
  const [folderPerms, setFolderPerms] = useState<FolderPermission[]>([]);
  const [folders, setFolders] = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [editPermMode, setEditPermMode] = useState(false);
  const [selectedFolderIds, setSelectedFolderIds] = useState<Set<number>>(new Set());
  const [permLevel, setPermLevel] = useState('write');

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [rData, fData] = await Promise.all([listRoles(), getFolderTree()]);
      setRoles(rData.roles);
      const flat: any[] = [];
      const walk = (nodes: any[]) => { for (const n of nodes) { flat.push(n); if (n.children) walk(n.children); } };
      walk(fData);
      setFolders(flat);
    } catch (err) { toast.error('加载失败'); }
    finally { setLoading(false); }
  };

  const selectRole = async (role: DmsRoleInfo) => {
    setSelectedRole(role);
    try {
      const p = await getRoleFolderPermissions(role.id);
      setFolderPerms(p.folder_permissions);
    } catch { setFolderPerms([]); }
    setEditPermMode(false);
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      const r = await createRole({ name: newName.trim(), description: newDesc.trim() || undefined });
      toast.success('角色已创建');
      setShowCreate(false); setNewName(''); setNewDesc('');
      await load();
      setSelectedRole(r);
    } catch (err: any) { toast.error(err.message); }
  };

  const handleDelete = async (role: DmsRoleInfo) => {
    if (role.is_system) { toast.error('系统角色不可删除'); return; }
    if (!confirm(`确定删除角色 "${role.name}"？`)) return;
    try {
      await deleteRole(role.id);
      toast.success('已删除');
      if (selectedRole?.id === role.id) setSelectedRole(null);
      await load();
    } catch (err: any) { toast.error(err.message); }
  };

  const startEditPerms = () => {
    const existingIds = new Set(folderPerms.map(p => p.folder_id));
    setSelectedFolderIds(existingIds);
    setPermLevel(folderPerms[0]?.permission || 'write');
    setEditPermMode(true);
  };

  const savePerms = async () => {
    if (!selectedRole || selectedRole.name === 'admin') return;
    try {
      await setRoleFolderPermissions(selectedRole.id, Array.from(selectedFolderIds), permLevel);
      toast.success('权限已保存');
      setEditPermMode(false);
      selectRole(selectedRole);
    } catch (err: any) { toast.error(err.message); }
  };

  const toggleFolder = (id: number) => {
    setSelectedFolderIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const getPermBadge = (p: string) => {
    const m: Record<string, string> = {
      read: 'bg-cp-cyan/20 text-cp-cyan',
      write: 'bg-cp-purple/20 text-cp-purple-light',
      admin: 'bg-cp-rose/20 text-cp-rose',
    };
    return <span className={`px-1.5 py-0.5 rounded text-xs ${m[p] || ''}`}>{p}</span>;
  };

  if (loading) return <div className="flex justify-center py-12"><RefreshCw className="w-6 h-6 text-cp-purple animate-spin" /></div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-orbitron font-bold text-cp-text">角色权限管理</h1>
          <p className="text-cp-muted text-sm mt-1">管理角色及文件夹访问权限</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={async () => {
            try { const r = await syncRoleAgents(); toast.success(`已同步 ${r.synced} 个 Agent`); await load(); }
            catch { toast.error('同步失败'); }
          }} className="px-3 py-2 text-sm border border-cp-border rounded text-cp-muted hover:text-cp-text flex items-center gap-1">
            <RefreshCw className="w-3.5 h-3.5" /> 同步 Agent
          </button>
          <button onClick={() => setShowCreate(true)} className="cp-btn-primary px-4 py-2 rounded-lg flex items-center gap-2">
            <Plus className="w-4 h-4" /> 新建角色
          </button>
        </div>
      </div>

      <div className="flex gap-6">
        {/* Role list */}
        <div className="w-64 shrink-0 space-y-1">
          {roles.map(r => (
            <div key={r.id} onClick={() => selectRole(r)}
              className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-all ${
                selectedRole?.id === r.id ? 'bg-cp-purple/15 border border-cp-purple/30' : 'cp-card hover:border-cp-purple/30'
              }`}>
              <div>
                <div className="flex items-center gap-2">
                  <Shield className="w-4 h-4 text-cp-purple-light" />
                  <span className="text-sm font-medium text-cp-text">{r.name}</span>
                </div>
                <div className="text-xs text-cp-muted mt-0.5">{r.description || '-'}</div>
                <div className="flex gap-2 mt-1 text-xs text-cp-dim">
                  <span>{r.user_count} 用户</span>
                  <span>{r.folder_count} 文件夹</span>
                  {r.is_system && <span className="text-cp-purple-light">系统</span>}
                </div>
              </div>
              {!r.is_system && (
                <button onClick={(e) => { e.stopPropagation(); handleDelete(r); }}
                  className="text-cp-dim hover:text-cp-rose p-1"><Trash2 className="w-3.5 h-3.5" /></button>
              )}
            </div>
          ))}
        </div>

        {/* Detail */}
        <div className="flex-1 cp-card rounded-lg p-4 min-h-[300px]">
          {!selectedRole ? (
            <div className="text-center py-12 text-cp-muted">选择一个角色查看详情</div>
          ) : selectedRole.name === 'admin' ? (
            <div className="text-center py-12">
              <Shield className="w-12 h-12 text-cp-purple mx-auto mb-3" />
              <p className="text-cp-text font-medium">系统管理员</p>
              <p className="text-cp-muted text-sm mt-1">管理员拥有全局访问权限，无需配置文件夹</p>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-cp-text font-semibold">{selectedRole.name} — 文件夹权限</h3>
                {editPermMode ? (
                  <div className="flex gap-2">
                    <button onClick={() => setEditPermMode(false)} className="px-3 py-1.5 text-sm border border-cp-border rounded text-cp-muted">取消</button>
                    <button onClick={savePerms} className="px-3 py-1.5 text-sm cp-btn-primary rounded flex items-center gap-1"><Save className="w-3.5 h-3.5" /> 保存</button>
                  </div>
                ) : (
                  <button onClick={startEditPerms} className="px-3 py-1.5 text-sm border border-cp-border rounded text-cp-muted hover:text-cp-text">
                    编辑权限
                  </button>
                )}
              </div>

              {editPermMode ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <label className="text-sm text-cp-muted">权限级别:</label>
                    <select value={permLevel} onChange={e => setPermLevel(e.target.value)}
                      className="cp-input text-sm rounded px-2 py-1">
                      <option value="read">只读 (read)</option>
                      <option value="write">读写 (write)</option>
                      <option value="admin">管理 (admin)</option>
                    </select>
                    <button onClick={() => setSelectedFolderIds(new Set(folders.map(f => f.id)))}
                      className="text-xs text-cp-purple-light hover:underline">全选</button>
                    <button onClick={() => setSelectedFolderIds(new Set())}
                      className="text-xs text-cp-dim hover:underline">取消全选</button>
                  </div>
                  <div className="max-h-96 overflow-y-auto space-y-1 border border-cp-border rounded p-2">
                    {folders.map(f => (
                      <label key={f.id} className="flex items-center gap-2 text-sm py-1 px-2 rounded cp-hover cursor-pointer">
                        <input type="checkbox" checked={selectedFolderIds.has(f.id)} onChange={() => toggleFolder(f.id)}
                          className="rounded border-cp-border" />
                        <FolderOpen className="w-3.5 h-3.5 text-cp-dim" />
                        <span className="text-cp-text">{f.name}</span>
                        <span className="text-cp-dim text-xs">{f.path}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="space-y-1">
                  {folderPerms.length === 0 ? (
                    <p className="text-cp-muted text-sm text-center py-8">尚未配置文件夹权限</p>
                  ) : (
                    folderPerms.map(p => (
                      <div key={p.id} className="flex items-center justify-between py-2 px-3 rounded cp-hover">
                        <div className="flex items-center gap-2">
                          <FolderOpen className="w-4 h-4 text-cp-dim" />
                          <span className="text-sm text-cp-text">{p.folder_name}</span>
                          <span className="text-xs text-cp-dim">{p.folder_path}</span>
                        </div>
                        {getPermBadge(p.permission)}
                      </div>
                    ))
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={() => setShowCreate(false)}>
          <div className="bg-white rounded-lg p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">新建角色</h3>
              <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-sm text-gray-600">角色名称</label>
                <input value={newName} onChange={e => setNewName(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 mt-1 text-sm" placeholder="如: 财务主管" />
              </div>
              <div>
                <label className="text-sm text-gray-600">描述</label>
                <input value={newDesc} onChange={e => setNewDesc(e.target.value)}
                  className="w-full border rounded-lg px-3 py-2 mt-1 text-sm" placeholder="可选" />
              </div>
              <button onClick={handleCreate} disabled={!newName.trim()}
                className="w-full cp-btn-primary py-2.5 rounded-lg disabled:opacity-40">
                创建
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
