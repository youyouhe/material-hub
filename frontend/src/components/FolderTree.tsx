import { useState, useEffect, useRef } from 'react';
import {
  ChevronRight, ChevronDown, Folder as FolderIcon, FolderOpen,
  Plus, Pencil, Trash2, Check, X, RefreshCw, ArrowUp, ArrowDown,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { getFolderTree, createFolder, updateFolder, deleteFolder, reorderFolders } from '../services/api-v2';
import type { FolderTreeNode } from '../types/dms';

interface FolderTreeProps {
  activeFolderId: number | null;
  onSelectFolder: (folderId: number | null, folderName?: string) => void;
  collapsed?: boolean;
  userRole?: string;
}

function TreeNode({
  node,
  activeFolderId,
  onSelectFolder,
  depth,
  isAdmin,
  onRefresh,
  siblings,
  siblingIndex,
  onMove,
}: {
  node: FolderTreeNode;
  activeFolderId: number | null;
  onSelectFolder: (id: number | null, name?: string) => void;
  depth: number;
  isAdmin: boolean;
  onRefresh: () => void;
  siblings: FolderTreeNode[];
  siblingIndex: number;
  onMove: (parentId: number | null, siblingIds: number[], fromIndex: number, direction: -1 | 1) => void;
}) {
  const [expanded, setExpanded] = useState(depth < 1);
  const [hovered, setHovered] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameName, setRenameName] = useState(node.name);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState('');
  const renameRef = useRef<HTMLInputElement>(null);
  const addRef = useRef<HTMLInputElement>(null);

  const hasChildren = node.children && node.children.length > 0;
  const isActive = activeFolderId === node.id;

  useEffect(() => {
    if (renaming) renameRef.current?.focus();
  }, [renaming]);

  useEffect(() => {
    if (adding) addRef.current?.focus();
  }, [adding]);

  const handleRename = async () => {
    const trimmed = renameName.trim();
    if (!trimmed || trimmed === node.name) { setRenaming(false); return; }
    try {
      await updateFolder(node.id, { name: trimmed });
      toast.success('文件夹已重命名');
      onRefresh();
    } catch { toast.error('重命名失败'); }
    setRenaming(false);
  };

  const handleAddChild = async () => {
    const trimmed = newName.trim();
    if (!trimmed) { setAdding(false); return; }
    try {
      await createFolder({ name: trimmed, parent_id: node.id });
      toast.success('文件夹已创建');
      setExpanded(true);
      onRefresh();
    } catch { toast.error('创建失败'); }
    setAdding(false);
    setNewName('');
  };

  const handleDelete = async () => {
    if (!confirm(`确定删除文件夹「${node.name}」？文件夹必须为空才能删除。`)) return;
    try {
      await deleteFolder(node.id);
      toast.success('文件夹已删除');
      onRefresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败，文件夹可能不为空');
    }
  };

  return (
    <div>
      <div
        className="relative group"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        {renaming ? (
          <div className="flex items-center gap-1 px-2 py-0.5" style={{ paddingLeft: `${depth * 16 + 8}px` }}>
            <input
              ref={renameRef}
              value={renameName}
              onChange={(e) => setRenameName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleRename(); if (e.key === 'Escape') setRenaming(false); }}
              className="cp-input text-sm rounded px-1.5 py-0.5 flex-1 min-w-0"
            />
            <button onClick={handleRename} className="p-0.5 text-green-400 hover:bg-green-900/20 rounded"><Check className="w-3 h-3" /></button>
            <button onClick={() => setRenaming(false)} className="p-0.5 text-cp-dim hover:bg-white/5 rounded"><X className="w-3 h-3" /></button>
          </div>
        ) : (
          <button
            onClick={() => {
              onSelectFolder(node.id, node.name);
              if (hasChildren) setExpanded(!expanded);
            }}
            className={clsx(
              'flex items-center gap-1 w-full text-left px-2 py-1 text-sm rounded hover:bg-white/5 transition-colors text-cp-muted',
              isActive && 'bg-cp-purple/10 text-cp-purple-light font-medium'
            )}
            style={{ paddingLeft: `${depth * 16 + 8}px` }}
          >
            {hasChildren ? (
              expanded ? <ChevronDown className="w-3.5 h-3.5 shrink-0 text-cp-dim" /> : <ChevronRight className="w-3.5 h-3.5 shrink-0 text-cp-dim" />
            ) : (
              <span className="w-3.5 shrink-0" />
            )}
            {isActive ? (
              <FolderOpen className="w-4 h-4 shrink-0 text-cp-purple" />
            ) : (
              <FolderIcon className="w-4 h-4 shrink-0 text-cp-dim" />
            )}
            <span className="truncate">{node.name}</span>
            {(node.doc_count ?? 0) > 0 && (
              <span className="ml-auto shrink-0 text-xs text-cp-dim bg-white/5 rounded-full px-1.5 py-0.5 min-w-[1.25rem] text-center">
                {node.doc_count}
              </span>
            )}
          </button>
        )}

        {/* Admin action buttons */}
        {isAdmin && hovered && !renaming && (
          <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5 bg-cp-card/90 rounded px-0.5">
            {siblingIndex > 0 && (
              <button
                onClick={(e) => { e.stopPropagation(); onMove(node.parent_id ?? null, siblings.map(s => s.id), siblingIndex, -1); }}
                title="上移"
                className="p-0.5 text-cp-dim hover:text-cp-cyan rounded hover:bg-white/5"
              >
                <ArrowUp className="w-3 h-3" />
              </button>
            )}
            {siblingIndex < siblings.length - 1 && (
              <button
                onClick={(e) => { e.stopPropagation(); onMove(node.parent_id ?? null, siblings.map(s => s.id), siblingIndex, 1); }}
                title="下移"
                className="p-0.5 text-cp-dim hover:text-cp-cyan rounded hover:bg-white/5"
              >
                <ArrowDown className="w-3 h-3" />
              </button>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); setAdding(true); setExpanded(true); }}
              title="新建子文件夹"
              className="p-0.5 text-cp-dim hover:text-cp-cyan rounded hover:bg-white/5"
            >
              <Plus className="w-3 h-3" />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setRenameName(node.name); setRenaming(true); }}
              title="重命名"
              className="p-0.5 text-cp-dim hover:text-cp-purple-light rounded hover:bg-white/5"
            >
              <Pencil className="w-3 h-3" />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); handleDelete(); }}
              title="删除"
              className="p-0.5 text-cp-dim hover:text-red-400 rounded hover:bg-white/5"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        )}
      </div>

      {/* Add child folder inline input */}
      {adding && (
        <div className="flex items-center gap-1 px-2 py-0.5" style={{ paddingLeft: `${(depth + 1) * 16 + 8}px` }}>
          <FolderIcon className="w-3.5 h-3.5 shrink-0 text-cp-cyan" />
          <input
            ref={addRef}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAddChild(); if (e.key === 'Escape') { setAdding(false); setNewName(''); } }}
            placeholder="文件夹名称"
            className="cp-input text-sm rounded px-1.5 py-0.5 flex-1 min-w-0"
          />
          <button onClick={handleAddChild} className="p-0.5 text-green-400 hover:bg-green-900/20 rounded"><Check className="w-3 h-3" /></button>
          <button onClick={() => { setAdding(false); setNewName(''); }} className="p-0.5 text-cp-dim hover:bg-white/5 rounded"><X className="w-3 h-3" /></button>
        </div>
      )}

      {expanded && hasChildren && (
        <div>
          {node.children.map((child, idx) => (
            <TreeNode
              key={child.id}
              node={child}
              activeFolderId={activeFolderId}
              onSelectFolder={onSelectFolder}
              depth={depth + 1}
              isAdmin={isAdmin}
              onRefresh={onRefresh}
              siblings={node.children}
              siblingIndex={idx}
              onMove={onMove}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function FolderTree({ activeFolderId, onSelectFolder, collapsed, userRole }: FolderTreeProps) {
  const [folders, setFolders] = useState<FolderTreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [addingRoot, setAddingRoot] = useState(false);
  const [newRootName, setNewRootName] = useState('');
  const addRootRef = useRef<HTMLInputElement>(null);

  const isAdmin = userRole === 'admin';

  const loadFolders = (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    getFolderTree()
      .then(setFolders)
      .catch(() => setFolders([]))
      .finally(() => { setLoading(false); setRefreshing(false); });
  };

  useEffect(() => { loadFolders(); }, []);

  useEffect(() => {
    if (addingRoot) addRootRef.current?.focus();
  }, [addingRoot]);

  const handleAddRoot = async () => {
    const trimmed = newRootName.trim();
    if (!trimmed) { setAddingRoot(false); return; }
    try {
      await createFolder({ name: trimmed });
      toast.success('文件夹已创建');
      loadFolders();
    } catch { toast.error('创建失败'); }
    setAddingRoot(false);
    setNewRootName('');
  };

  const handleMove = async (parentId: number | null, siblingIds: number[], fromIndex: number, direction: -1 | 1) => {
    const toIndex = fromIndex + direction;
    if (toIndex < 0 || toIndex >= siblingIds.length) return;
    const newOrder = [...siblingIds];
    [newOrder[fromIndex], newOrder[toIndex]] = [newOrder[toIndex], newOrder[fromIndex]];
    try {
      await reorderFolders(parentId, newOrder);
      loadFolders();
    } catch { toast.error('排序失败'); }
  };

  if (collapsed) return null;

  return (
    <div className="py-2">
      <div className="px-3 mb-1 flex items-center justify-between">
        <span className="text-xs font-orbitron font-semibold text-cp-dim uppercase tracking-wider">文件夹</span>
        <div className="flex items-center gap-0.5">
          <button
            onClick={() => loadFolders(true)}
            title="刷新文件夹"
            className="p-0.5 text-cp-dim hover:text-cp-cyan rounded hover:bg-white/5"
          >
            <RefreshCw className={clsx('w-3.5 h-3.5', refreshing && 'animate-spin')} />
          </button>
          {isAdmin && (
            <button
              onClick={() => setAddingRoot(true)}
              title="新建根文件夹"
              className="p-0.5 text-cp-dim hover:text-cp-cyan rounded hover:bg-white/5"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
      <button
        onClick={() => onSelectFolder(null)}
        className={clsx(
          'flex items-center gap-1.5 w-full text-left px-3 py-1 text-sm rounded hover:bg-white/5 transition-colors text-cp-muted',
          activeFolderId === null && 'bg-cp-purple/10 text-cp-purple-light font-medium'
        )}
      >
        <FolderIcon className="w-4 h-4 shrink-0" />
        <span>全部文档</span>
      </button>

      {/* Add root folder inline input */}
      {addingRoot && (
        <div className="flex items-center gap-1 px-3 py-0.5">
          <FolderIcon className="w-3.5 h-3.5 shrink-0 text-cp-cyan" />
          <input
            ref={addRootRef}
            value={newRootName}
            onChange={(e) => setNewRootName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAddRoot(); if (e.key === 'Escape') { setAddingRoot(false); setNewRootName(''); } }}
            placeholder="文件夹名称"
            className="cp-input text-sm rounded px-1.5 py-0.5 flex-1 min-w-0"
          />
          <button onClick={handleAddRoot} className="p-0.5 text-green-400 hover:bg-green-900/20 rounded"><Check className="w-3 h-3" /></button>
          <button onClick={() => { setAddingRoot(false); setNewRootName(''); }} className="p-0.5 text-cp-dim hover:bg-white/5 rounded"><X className="w-3 h-3" /></button>
        </div>
      )}

      {loading ? (
        <div className="px-3 py-2 text-xs text-cp-dim">加载中...</div>
      ) : (
        folders.map((node, idx) => (
          <TreeNode
            key={node.id}
            node={node}
            activeFolderId={activeFolderId}
            onSelectFolder={onSelectFolder}
            depth={0}
            isAdmin={isAdmin}
            onRefresh={loadFolders}
            siblings={folders}
            siblingIndex={idx}
            onMove={handleMove}
          />
        ))
      )}
    </div>
  );
}
