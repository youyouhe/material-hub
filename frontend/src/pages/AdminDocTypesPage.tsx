import { useState, useEffect, useCallback } from 'react';
import { FileType, Plus, Trash2, Edit3, Check, X, Tag } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { listDocTypes, createDocType, updateDocType, deleteDocType, getFolderTree } from '../services/api-v2';
import { getToken } from '../services/auth';
import type { DocType, FolderTreeNode } from '../types/dms';

const CATEGORY_LABELS: Record<string, string> = {
  company: '企业资质', personnel: '人员证件', project: '项目文档', bid: '投标文档', general: '通用文档',
};
const CATEGORY_COLORS: Record<string, string> = {
  company: 'bg-blue-900/30 text-blue-400',
  personnel: 'bg-green-900/30 text-green-400',
  project: 'bg-yellow-900/30 text-yellow-400',
  bid: 'bg-purple-900/30 text-purple-400',
  general: 'bg-gray-800/30 text-gray-400',
};

const BASE = '/api/v2';

interface KeywordRule {
  keywords: string[];
  doc_type_code: string;
  source: 'builtin' | 'custom';
}

function flattenFolders(nodes: FolderTreeNode[], depth = 0): { node: FolderTreeNode; depth: number }[] {
  const result: { node: FolderTreeNode; depth: number }[] = [];
  for (const n of nodes) {
    result.push({ node: n, depth });
    if (n.children?.length) result.push(...flattenFolders(n.children, depth + 1));
  }
  return result;
}

export default function AdminDocTypesPage() {
  const [docTypes, setDocTypes] = useState<DocType[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ name: '', code: '', category: 'company', description: '' });
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ name: '', category: '', description: '' });
  const [keywordRules, setKeywordRules] = useState<KeywordRule[]>([]);
  const [folderMappings, setFolderMappings] = useState<Record<string, string>>({});
  const [editingKeywords, setEditingKeywords] = useState<number | null>(null);
  const [kwInput, setKwInput] = useState('');
  const [folderInput, setFolderInput] = useState('');
  const [folders, setFolders] = useState<FolderTreeNode[]>([]);

  const fetchAll = useCallback(async () => {
    try {
      const [dtData, rulesResp] = await Promise.all([
        listDocTypes(),
        fetch(`${BASE}/doc-types/config/keyword-rules`, { headers: { Authorization: `Bearer ${getToken()}` } }).then(r => r.json()),
      ]);
      const allTypes: DocType[] = [];
      for (const types of Object.values(dtData.doc_types)) {
        allTypes.push(...(types as DocType[]));
      }
      setDocTypes(allTypes);
      setKeywordRules(rulesResp.rules || []);
      setFolderMappings(rulesResp.folder_mappings || {});
    } catch { toast.error('加载失败'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);
  useEffect(() => { getFolderTree().then(setFolders).catch(() => {}); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createDocType(createForm);
      toast.success('文档类型已创建');
      setShowCreate(false);
      setCreateForm({ name: '', code: '', category: 'company', description: '' });
      fetchAll();
    } catch (err) { toast.error(err instanceof Error ? err.message : '创建失败'); }
  };

  const handleUpdate = async (id: number) => {
    try {
      await updateDocType(id, editForm);
      toast.success('已更新');
      setEditingId(null);
      fetchAll();
    } catch (err) { toast.error(err instanceof Error ? err.message : '更新失败'); }
  };

  const handleDelete = async (dt: DocType) => {
    if (!confirm(`确定删除「${dt.name}」？已关联文档的类型不可删除。`)) return;
    try {
      await deleteDocType(dt.id);
      toast.success('已删除');
      fetchAll();
    } catch (err) { toast.error(err instanceof Error ? err.message : '删除失败'); }
  };

  const handleSaveKeywords = async (dt: DocType) => {
    const keywords = kwInput.split(/[,，;；\s]+/).filter(Boolean);
    if (keywords.length === 0) { toast.error('请输入至少一个关键词'); return; }
    try {
      await fetch(`${BASE}/doc-types/${dt.id}/keywords`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ keywords, folder_path: folderInput || undefined }),
      }).then(r => { if (!r.ok) throw new Error('Failed'); return r.json(); });
      toast.success('关键词和文件夹映射已保存');
      setEditingKeywords(null);
      setKwInput('');
      setFolderInput('');
      fetchAll();
    } catch { toast.error('保存失败'); }
  };

  const getKeywordsForCode = (code: string) => {
    const rules = keywordRules.filter(r => r.doc_type_code === code);
    return rules;
  };

  const autoCode = (name: string) => {
    // Simple: pinyin-like slug from Chinese name
    return name.trim().toLowerCase()
      .replace(/[\s]+/g, '-')
      .replace(/[^a-z0-9\u4e00-\u9fff-]/g, '')
      || 'custom-type';
  };

  const flat = flattenFolders(folders);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-orbitron font-semibold text-cp-text flex items-center gap-2">
          <FileType className="w-5 h-5 text-cp-cyan" /> 文档类型管理
        </h2>
        <button onClick={() => setShowCreate(true)} className="cp-btn-primary flex items-center gap-1 px-3 py-2 text-sm rounded-lg">
          <Plus className="w-4 h-4" /> 新建类型
        </button>
      </div>

      <p className="text-sm text-cp-dim mb-4">
        管理系统中的文档类型。添加新类型后，可配置关键词让 AI 自动分类，并指定归档文件夹。
      </p>

      {loading ? (
        <div className="text-center py-12 text-cp-dim">加载中...</div>
      ) : (
        <div className="cp-card rounded-lg overflow-hidden">
          <table className="cp-table min-w-full">
            <thead>
              <tr>
                <th className="px-4 py-3 text-left">名称</th>
                <th className="px-4 py-3 text-left">Code</th>
                <th className="px-4 py-3 text-left">分类</th>
                <th className="px-4 py-3 text-left">关键词</th>
                <th className="px-4 py-3 text-left">归档文件夹</th>
                <th className="px-4 py-3 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {docTypes.map((dt) => {
                const rules = getKeywordsForCode(dt.code);
                const allKw = rules.flatMap(r => r.keywords);
                const folder = folderMappings[dt.code];
                const isEditing = editingId === dt.id;

                return (
                  <tr key={dt.id}>
                    <td className="px-4 py-3">
                      {isEditing ? (
                        <input value={editForm.name} onChange={e => setEditForm({ ...editForm, name: e.target.value })} className="cp-input text-sm rounded px-2 py-1 w-full" />
                      ) : (
                        <div>
                          <span className="text-sm text-cp-text font-medium">{dt.name}</span>
                          {dt.description && <div className="text-xs text-cp-dim mt-0.5">{dt.description}</div>}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <code className="text-xs text-cp-dim font-mono">{dt.code}</code>
                    </td>
                    <td className="px-4 py-3">
                      {isEditing ? (
                        <select value={editForm.category} onChange={e => setEditForm({ ...editForm, category: e.target.value })} className="cp-select text-xs rounded px-2 py-1">
                          {Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                        </select>
                      ) : (
                        <span className={clsx('text-xs px-2 py-0.5 rounded-full', CATEGORY_COLORS[dt.category] || CATEGORY_COLORS.general)}>
                          {CATEGORY_LABELS[dt.category] || dt.category}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {allKw.slice(0, 5).map((kw, i) => (
                          <span key={i} className="text-xs bg-cp-purple/5 text-cp-dim rounded px-1.5 py-0.5">{kw}</span>
                        ))}
                        {allKw.length > 5 && <span className="text-xs text-cp-dim">+{allKw.length - 5}</span>}
                        {allKw.length === 0 && <span className="text-xs text-cp-dim italic">未配置</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs text-cp-dim">{folder || '未配置'}</span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {isEditing ? (
                          <>
                            <button onClick={() => handleUpdate(dt.id)} className="text-green-400 hover:text-green-300" title="保存"><Check className="w-4 h-4" /></button>
                            <button onClick={() => setEditingId(null)} className="text-cp-dim hover:text-cp-text" title="取消"><X className="w-4 h-4" /></button>
                          </>
                        ) : (
                          <>
                            <button onClick={() => { setEditingKeywords(editingKeywords === dt.id ? null : dt.id); setKwInput(getKeywordsForCode(dt.code).filter(r => r.source === 'custom').flatMap(r => r.keywords).join(', ')); setFolderInput(folderMappings[dt.code] || ''); }} className="text-cp-cyan hover:text-cp-text" title="配置关键词">
                              <Tag className="w-4 h-4" />
                            </button>
                            <button onClick={() => { setEditingId(dt.id); setEditForm({ name: dt.name, category: dt.category, description: dt.description || '' }); }} className="text-cp-purple-light hover:text-cp-text" title="编辑">
                              <Edit3 className="w-4 h-4" />
                            </button>
                            {!dt.is_system && (
                              <button onClick={() => handleDelete(dt)} className="text-red-400 hover:text-red-300" title="删除">
                                <Trash2 className="w-4 h-4" />
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Keyword editor panel */}
      {editingKeywords && (() => {
        const dt = docTypes.find(d => d.id === editingKeywords);
        if (!dt) return null;
        const builtinRules = getKeywordsForCode(dt.code).filter(r => r.source === 'builtin');
        return (
          <div className="cp-card rounded-lg p-4 mt-2">
            <h4 className="text-sm font-medium text-cp-cyan flex items-center gap-1 mb-3">
              <Tag className="w-4 h-4" /> {dt.name} — 关键词 & 文件夹配置
            </h4>

            {builtinRules.length > 0 && (
              <div className="mb-3">
                <span className="text-xs text-cp-dim">内置关键词：</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {builtinRules.flatMap(r => r.keywords).map((kw, i) => (
                    <span key={i} className="text-xs bg-blue-900/20 text-blue-400 rounded px-1.5 py-0.5">{kw}</span>
                  ))}
                </div>
              </div>
            )}

            <div className="space-y-3">
              <div>
                <label className="block text-xs text-cp-muted mb-1">自定义关键词（逗号分隔，AI 识别到这些词会自动归类到此类型）</label>
                <input
                  value={kwInput}
                  onChange={e => setKwInput(e.target.value)}
                  placeholder="如：报价单, 报价函, 价格表"
                  className="cp-input w-full rounded-md px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-cp-muted mb-1">归档文件夹（文档分类后自动归入此文件夹）</label>
                <select
                  value={folderInput}
                  onChange={e => setFolderInput(e.target.value)}
                  className="cp-select w-full rounded-md px-3 py-2 text-sm"
                >
                  <option value="">不指定</option>
                  {flat.map(({ node, depth }) => (
                    <option key={node.id} value={node.path}>
                      {depth === 0 ? '📁 ' : '\u00A0'.repeat(depth * 4) + '└ '}{node.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex justify-end gap-2">
                <button onClick={() => setEditingKeywords(null)} className="cp-btn-ghost px-3 py-1.5 text-sm rounded">取消</button>
                <button onClick={() => handleSaveKeywords(dt)} className="cp-btn-primary px-3 py-1.5 text-sm rounded flex items-center gap-1">
                  <Check className="w-3.5 h-3.5" /> 保存
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Create dialog */}
      {showCreate && (
        <div className="cp-overlay fixed inset-0 flex items-center justify-center z-50">
          <div className="cp-card rounded-lg p-6 w-full max-w-sm">
            <h3 className="text-lg font-orbitron font-semibold text-cp-text mb-4 flex items-center gap-2">
              <FileType className="w-5 h-5 text-cp-cyan" /> 新建文档类型
            </h3>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">类型名称</label>
                <input
                  value={createForm.name}
                  onChange={e => {
                    const name = e.target.value;
                    setCreateForm({ ...createForm, name, code: createForm.code || autoCode(name) });
                  }}
                  placeholder="如：报价单、检测报告"
                  className="cp-input w-full rounded-md px-3 py-2 text-sm"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">Code（英文标识，创建后不可修改）</label>
                <input
                  value={createForm.code}
                  onChange={e => setCreateForm({ ...createForm, code: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-') })}
                  placeholder="如：quotation、test-report"
                  className="cp-input w-full rounded-md px-3 py-2 text-sm font-mono"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">分类</label>
                <select value={createForm.category} onChange={e => setCreateForm({ ...createForm, category: e.target.value })} className="cp-select w-full rounded-md px-3 py-2 text-sm">
                  {Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">描述（可选）</label>
                <input
                  value={createForm.description}
                  onChange={e => setCreateForm({ ...createForm, description: e.target.value })}
                  className="cp-input w-full rounded-md px-3 py-2 text-sm"
                />
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
