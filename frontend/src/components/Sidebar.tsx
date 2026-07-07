import { useState, useRef, useCallback, useEffect } from 'react';
import {
  FileText, Search, Upload, Briefcase, Shield, LogOut, Clock,
  ScrollText, PanelLeftClose, PanelLeft, Settings, Bot, MessageSquare,
  Sun, Moon, Download,
} from 'lucide-react';
import clsx from 'clsx';
import FolderTree from './FolderTree';

export type Page =
  | 'documents' | 'search' | 'upload' | 'bids' | 'bid-detail' | 'expiry' | 'chat'
  | 'admin-users' | 'admin-agents' | 'admin-doc-types' | 'admin-audit' | 'admin-settings' | 'admin-transfer' | 'admin-roles';

interface SidebarProps {
  currentPage: Page;
  onNavigate: (page: Page) => void;
  userRole: string;
  activeFolderId: number | null;
  onSelectFolder: (folderId: number | null, folderName?: string) => void;
  onLogout: () => void;
}

interface NavItem {
  page: Page;
  label: string;
  icon: React.ReactNode;
}

export default function Sidebar({
  currentPage,
  onNavigate,
  userRole,
  activeFolderId,
  onSelectFolder,
  onLogout,
}: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [width, setWidth] = useState(224);
  const isResizing = useRef(false);
  const [theme, setTheme] = useState<'dark' | 'light'>(
    () => (localStorage.getItem('theme') as 'dark' | 'light') || 'dark'
  );

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark');

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (collapsed) return;
    e.preventDefault();
    isResizing.current = true;
    const startX = e.clientX;
    const startWidth = width;

    const onMouseMove = (ev: MouseEvent) => {
      if (!isResizing.current) return;
      const newWidth = Math.min(400, Math.max(180, startWidth + ev.clientX - startX));
      setWidth(newWidth);
    };

    const onMouseUp = () => {
      isResizing.current = false;
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }, [collapsed, width]);

  const mainNav: NavItem[] = [
    { page: 'documents', label: '文档', icon: <FileText className="w-4 h-4" /> },
    { page: 'search', label: '搜索', icon: <Search className="w-4 h-4" /> },
    { page: 'upload', label: '上传', icon: <Upload className="w-4 h-4" /> },
    { page: 'bids', label: '投标管理', icon: <Briefcase className="w-4 h-4" /> },
    { page: 'expiry', label: '到期提醒', icon: <Clock className="w-4 h-4" /> },
    { page: 'chat', label: '智能助手', icon: <MessageSquare className="w-4 h-4" /> },
  ];

  const adminNav: NavItem[] = [
    { page: 'admin-users', label: '用户管理', icon: <Shield className="w-4 h-4" /> },
    { page: 'admin-agents', label: 'Agent 管理', icon: <Bot className="w-4 h-4" /> },
    { page: 'admin-doc-types', label: '文档类型', icon: <FileText className="w-4 h-4" /> },
    { page: 'admin-audit', label: '审计日志', icon: <ScrollText className="w-4 h-4" /> },
    { page: 'admin-settings', label: '系统设置', icon: <Settings className="w-4 h-4" /> },
    { page: 'admin-roles', label: '角色权限', icon: <Shield className="w-4 h-4" /> },
    { page: 'admin-transfer', label: '数据迁移', icon: <Download className="w-4 h-4" /> },
  ];


  function renderNavItem(item: NavItem) {
    const isActive = currentPage === item.page || (item.page === 'bids' && currentPage === 'bid-detail');
    return (
      <button
        key={item.page}
        onClick={() => onNavigate(item.page)}
        title={collapsed ? item.label : undefined}
        className={clsx(
          'flex items-center gap-2 w-full text-left px-3 py-2 text-sm rounded-lg transition-colors',
          isActive
            ? 'bg-cp-purple/10 text-cp-purple-light font-medium border-l-2 border-cp-purple'
            : 'text-cp-muted cp-hover hover:text-cp-text'
        )}
      >
        {item.icon}
        {!collapsed && <span>{item.label}</span>}
      </button>
    );
  }

  return (
    <aside
      className="flex flex-col bg-cp-card border-r border-cp-border h-full relative"
      style={{ width: collapsed ? 56 : width, minWidth: collapsed ? 56 : 180, transition: collapsed ? 'width 0.2s' : undefined }}
    >
      {/* Header */}
      <div className="flex items-center justify-between h-14 px-3 border-b border-cp-border shrink-0">
        {!collapsed && <span className="text-lg font-orbitron font-semibold text-cp-purple glow-purple-sm">MaterialHub</span>}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1 rounded cp-hover text-cp-dim"
          title={collapsed ? '展开侧边栏' : '收起侧边栏'}
        >
          {collapsed ? <PanelLeft className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">
        {/* Main nav */}
        <div className="p-2 space-y-0.5">
          {mainNav.map(renderNavItem)}
        </div>

        {/* Folder tree */}
        {!collapsed && (
          <div className="border-t border-cp-border/50 mx-2">
            <FolderTree
              activeFolderId={activeFolderId}
              onSelectFolder={(id, name) => {
                onSelectFolder(id, name);
                onNavigate('documents');
              }}
              userRole={userRole}
            />
          </div>
        )}

        {/* Admin nav */}
        {userRole === 'admin' && (
          <div className="border-t border-cp-border/50 mx-2 pt-2">
            {!collapsed && (
              <div className="px-3 mb-1">
                <span className="text-xs font-orbitron font-semibold text-cp-rose uppercase tracking-wider">管理</span>
              </div>
            )}
            <div className="space-y-0.5">
              {adminNav.map(renderNavItem)}
            </div>
          </div>
        )}

      </div>

      {/* Footer */}
      <div className="border-t border-cp-border p-2 shrink-0 space-y-0.5">
        <button
          onClick={toggleTheme}
          title={collapsed ? (theme === 'dark' ? '亮色模式' : '暗色模式') : undefined}
          className="flex items-center gap-2 w-full text-left px-3 py-2 text-sm rounded-lg text-cp-dim hover:bg-cp-purple/10 hover:text-cp-purple-light transition-colors"
        >
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          {!collapsed && <span>{theme === 'dark' ? '亮色模式' : '暗色模式'}</span>}
        </button>
        <button
          onClick={onLogout}
          title={collapsed ? '退出登录' : undefined}
          className="flex items-center gap-2 w-full text-left px-3 py-2 text-sm rounded-lg text-cp-dim hover:bg-cp-rose/10 hover:text-cp-rose transition-colors"
        >
          <LogOut className="w-4 h-4" />
          {!collapsed && <span>退出登录</span>}
        </button>
      </div>

      {/* Resize handle */}
      {!collapsed && (
        <div
          onMouseDown={handleMouseDown}
          className="absolute top-0 right-0 w-1 h-full cursor-col-resize hover:bg-cp-purple/40 active:bg-cp-purple/60 transition-colors z-10"
        />
      )}
    </aside>
  );
}
