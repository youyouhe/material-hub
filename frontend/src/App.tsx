import { useState, useCallback, useEffect, useRef } from 'react';
import { Toaster } from 'react-hot-toast';
import toast from 'react-hot-toast';
import Sidebar from './components/Sidebar';
import type { Page } from './components/Sidebar';
import DocumentsPage from './pages/DocumentsPage';
import SearchPage from './pages/SearchPage';
import UploadPageV2 from './pages/UploadPageV2';
import BidsPage from './pages/BidsPage';
import BidDetailPage from './pages/BidDetailPage';
import ExpiryPage from './pages/ExpiryPage';
import ChatPage from './pages/ChatPage';
import { loadChatHistory, saveChatHistory, type ChatMessage } from './services/api-v2';
import AdminUsersPage from './pages/AdminUsersPage';
import AdminAuditPage from './pages/AdminAuditPage';
import AdminSettingsPage from './pages/AdminSettingsPage';
import AdminAgentsPage from './pages/AdminAgentsPage';
import AdminDocTypesPage from './pages/AdminDocTypesPage';
import AdminTransferPage from './pages/AdminTransferPage';
import AdminRolesPage from './pages/AdminRolesPage';
import { LoginPage } from './components/LoginPage';
import { isAuthenticated, setToken, clearToken, setUser, getUser } from './services/auth';
import { checkAuthV2, logoutV2 } from './services/api-v2';
import { X } from 'lucide-react';

const PAGE_TITLES: Record<Page, string> = {
  'documents': '文档', 'search': '搜索', 'upload': '上传', 'bids': '投标管理',
  'bid-detail': '投标详情', 'expiry': '到期提醒', 'chat': '智能助手',
  'admin-users': '用户管理', 'admin-agents': 'Agent管理', 'admin-doc-types': '文档类型',
  'admin-audit': '审计日志', 'admin-settings': '系统设置', 'admin-transfer': '数据迁移',
  'admin-roles': '角色权限',
};

interface Tab {
  id: number;
  page: Page;
  title: string;
  folderId?: number | null;
  folderName?: string;
  bidId?: number | null;
  docId?: number | null;
}

let _tabIdCounter = 0;
function nextTabId() { return ++_tabIdCounter; }

export default function App() {
  const [tabs, setTabs] = useState<Tab[]>([{ id: nextTabId(), page: 'documents', title: '文档' }]);
  const [activeTab, setActiveTab] = useState(0);
  const [isLoggedIn, setIsLoggedIn] = useState(isAuthenticated());
  const [isValidating, setIsValidating] = useState(true);
  const [userRole, setUserRole] = useState<string>(getUser()?.role || 'editor');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatSessionId, setChatSessionId] = useState<number | null>(null);
  const [chatHistoryLoaded, setChatHistoryLoaded] = useState(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout>>();

  const curTab = tabs[activeTab] || tabs[0];

  useEffect(() => {
    if (!isLoggedIn) return;
    loadChatHistory()
      .then(({ messages, session_id }) => {
        setChatMessages(messages || []);
        if (session_id) setChatSessionId(session_id);
        setChatHistoryLoaded(true);
      })
      .catch(() => setChatHistoryLoaded(true));
  }, [isLoggedIn]);

  const handleChatMessagesChange = useCallback((msgs: ChatMessage[]) => {
    setChatMessages(msgs);
    if (!chatHistoryLoaded) return;
    clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      saveChatHistory(msgs, chatSessionId || undefined).catch(() => {});
    }, 1000);
  }, [chatHistoryLoaded, chatSessionId]);

  useEffect(() => {
    const validateToken = async () => {
      if (isAuthenticated()) {
        const valid = await checkAuthV2();
        if (!valid) { clearToken(); setIsLoggedIn(false); }
      }
      setIsValidating(false);
    };
    validateToken();
  }, []);

  const switchOrOpenTab = useCallback((page: Page) => {
    const existing = tabs.findIndex(t => t.page === page && page !== 'bid-detail');
    if (existing >= 0) {
      setActiveTab(existing);
    } else {
      const newTab: Tab = { id: nextTabId(), page, title: PAGE_TITLES[page] || page };
      setTabs(prev => [...prev, newTab]);
      setActiveTab(tabs.length);
    }
  }, [tabs]);

  const openTab = useCallback((page: Page, extra?: Partial<Tab>) => {
    const newTab: Tab = { id: nextTabId(), page, title: PAGE_TITLES[page] || page, ...extra };
    setTabs(prev => [...prev, newTab]);
    setActiveTab(tabs.length);
  }, [tabs]);

  const closeTab = useCallback((idx: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (tabs.length <= 1) return;
    setTabs(prev => {
      const next = prev.filter((_, i) => i !== idx);
      if (idx <= activeTab) setActiveTab(Math.max(0, activeTab - 1));
      return next;
    });
  }, [tabs, activeTab]);

  const handleSelectFolder = useCallback((folderId: number | null, folderName?: string) => {
    setTabs(prev => prev.map((t, i) => i === activeTab ? { ...t, folderId, folderName: folderName || '', title: folderName || t.title } : t));
    switchOrOpenTab('documents');
  }, [activeTab, switchOrOpenTab]);

  const handleLogin = useCallback((token: string, user?: { id: number; username: string; role: string }) => {
    setToken(token);
    if (user) { setUser(user); setUserRole(user.role); }
    setIsLoggedIn(true);
    toast.success('登录成功');
  }, []);

  const handleLogout = useCallback(async () => {
    try { await logoutV2(); } catch {}
    clearToken();
    setIsLoggedIn(false);
    toast.success('已退出登录');
  }, []);

  if (isValidating) {
    return <div className="min-h-screen bg-cp-bg flex items-center justify-center">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-cp-purple mx-auto" />
    </div>;
  }

  if (!isLoggedIn) {
    return <><Toaster position="top-right" /><LoginPage onLogin={handleLogin} /></>;
  }

  function renderTab(tab: Tab) {
    switch (tab.page) {
      case 'documents':
        return <DocumentsPage folderId={tab.folderId ?? null} selectedDocumentId={tab.docId ?? null}
          onSelectDocument={(id) => setTabs(prev => prev.map((t, i) => i === activeTab ? { ...t, docId: id } : t))}
          userRole={userRole} />;
      case 'search':
        return <SearchPage onSelectDocument={(id) => openTab('documents', { docId: id })} userRole={userRole} />;
      case 'upload':
        return <UploadPageV2 userRole={userRole} />;
      case 'bids':
        return <BidsPage onOpenBid={(id) => openTab('bid-detail', { bidId: id, title: `投标 #${id}` })} />;
      case 'bid-detail':
        return tab.bidId ? <BidDetailPage bidId={tab.bidId} userRole={userRole}
          onBack={() => closeTab(activeTab, {} as any)} /> : <BidsPage onOpenBid={(id) => openTab('bid-detail', { bidId: id })} />;
      case 'expiry':
        return <ExpiryPage onSelectDocument={(id) => openTab('documents', { docId: id })} />;
      case 'chat':
        return <ChatPage folderId={tab.folderId ?? null} folderName={tab.folderName} messages={chatMessages}
          onMessagesChange={handleChatMessagesChange} sessionId={chatSessionId} onSessionChange={setChatSessionId} />;
      case 'admin-users': return <AdminUsersPage />;
      case 'admin-audit': return <AdminAuditPage />;
      case 'admin-settings': return <AdminSettingsPage />;
      case 'admin-agents': return <AdminAgentsPage />;
      case 'admin-doc-types': return <AdminDocTypesPage />;
      case 'admin-transfer': return <AdminTransferPage />;
      case 'admin-roles': return <AdminRolesPage />;
      default: return <DocumentsPage folderId={null} selectedDocumentId={null}
        onSelectDocument={(id) => setTabs(prev => prev.map((t, i) => i === activeTab ? { ...t, docId: id } : t))}
        userRole={userRole} />;
    }
  }

  return (
    <div className="flex flex-col h-screen bg-cp-bg">
      <Toaster position="top-right" toastOptions={{
        style: { background: 'var(--cp-card)', color: 'var(--cp-text)', border: '1px solid var(--cp-border)' },
      }} />

      {/* Tab Bar */}
      <div className="flex items-center h-9 bg-cp-footer border-b border-cp-border shrink-0 overflow-x-auto">
        {tabs.map((t, i) => (
          <div key={t.id}
            onClick={() => setActiveTab(i)}
            className={`flex items-center gap-1.5 h-full px-3 text-xs cursor-pointer border-r border-cp-border shrink-0 transition-colors ${
              i === activeTab ? 'bg-cp-card text-cp-text border-t-2 border-t-cp-purple' : 'text-cp-muted hover:bg-cp-card/50'
            }`}>
            <span className="truncate max-w-32">{t.title}</span>
            {tabs.length > 1 && (
              <button onClick={(e) => closeTab(i, e)}
                className="p-0.5 rounded hover:bg-cp-rose/10 hover:text-cp-rose">
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          currentPage={curTab.page}
          onNavigate={switchOrOpenTab}
          userRole={userRole}
          activeFolderId={curTab.folderId ?? null}
          onSelectFolder={handleSelectFolder}
          onLogout={handleLogout}
        />
        <main className="flex-1 overflow-y-auto bg-cp-bg">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4">
            {renderTab(curTab)}
          </div>
        </main>
      </div>
    </div>
  );
}
