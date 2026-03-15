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
import { LoginPage } from './components/LoginPage';
import { isAuthenticated, setToken, clearToken, setUser, getUser } from './services/auth';
import { checkAuth, logout as apiLogout } from './services/api';

export default function App() {
  const [page, setPage] = useState<Page>('documents');
  const [isLoggedIn, setIsLoggedIn] = useState(isAuthenticated());
  const [isValidating, setIsValidating] = useState(true);
  const [userRole, setUserRole] = useState<string>(getUser()?.role || 'editor');
  const [activeFolderId, setActiveFolderId] = useState<number | null>(null);
  const [activeFolderName, setActiveFolderName] = useState<string>('');
  const [selectedBidId, setSelectedBidId] = useState<number | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatHistoryLoaded, setChatHistoryLoaded] = useState(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout>>();

  // Load chat history from backend on login
  useEffect(() => {
    if (!isLoggedIn) return;
    loadChatHistory()
      .then((msgs) => { setChatMessages(msgs); setChatHistoryLoaded(true); })
      .catch(() => setChatHistoryLoaded(true));
  }, [isLoggedIn]);

  // Debounced save to backend when messages change
  const handleChatMessagesChange = useCallback((msgs: ChatMessage[]) => {
    setChatMessages(msgs);
    if (!chatHistoryLoaded) return;
    clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      saveChatHistory(msgs).catch(() => {});
    }, 1000);
  }, [chatHistoryLoaded]);

  useEffect(() => {
    const validateToken = async () => {
      if (isAuthenticated()) {
        const valid = await checkAuth();
        if (!valid) {
          clearToken();
          setIsLoggedIn(false);
        }
      }
      setIsValidating(false);
    };
    validateToken();
  }, []);

  const handleNavigate = useCallback((newPage: Page) => {
    setPage(newPage);
  }, []);

  const handleSelectFolder = useCallback((folderId: number | null, folderName?: string) => {
    setActiveFolderId(folderId);
    setActiveFolderName(folderName || '');
  }, []);

  const handleOpenBid = useCallback((bidId: number) => {
    setSelectedBidId(bidId);
    setPage('bid-detail');
  }, []);

  const handleOpenDocument = useCallback((docId: number) => {
    setSelectedDocumentId(docId);
    setPage('documents');
  }, []);

  const handleLogin = useCallback((token: string, user?: { id: number; username: string; role: string }) => {
    setToken(token);
    if (user) {
      setUser(user);
      setUserRole(user.role);
    }
    setIsLoggedIn(true);
    toast.success('登录成功');
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      await apiLogout();
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      clearToken();
      setIsLoggedIn(false);
      toast.success('已退出登录');
    }
  }, []);

  if (isValidating) {
    return (
      <div className="min-h-screen bg-cp-bg flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-cp-purple mx-auto"></div>
          <p className="mt-4 text-cp-muted">加载中...</p>
        </div>
      </div>
    );
  }

  if (!isLoggedIn) {
    return (
      <>
        <Toaster position="top-right" />
        <LoginPage onLogin={handleLogin} />
      </>
    );
  }

  function renderPage() {
    switch (page) {
      case 'documents':
        return (
          <DocumentsPage
            folderId={activeFolderId}
            selectedDocumentId={selectedDocumentId}
            onSelectDocument={handleOpenDocument}
            userRole={userRole}
          />
        );
      case 'search':
        return <SearchPage onSelectDocument={handleOpenDocument} userRole={userRole} />;
      case 'upload':
        return <UploadPageV2 userRole={userRole} />;
      case 'bids':
        return <BidsPage onOpenBid={handleOpenBid} />;
      case 'bid-detail':
        return selectedBidId ? (
          <BidDetailPage
            bidId={selectedBidId}
            userRole={userRole}
            onBack={() => setPage('bids')}
          />
        ) : (
          <BidsPage onOpenBid={handleOpenBid} />
        );
      case 'expiry':
        return <ExpiryPage onSelectDocument={handleOpenDocument} />;
      case 'chat':
        return <ChatPage folderId={activeFolderId} folderName={activeFolderName} messages={chatMessages} onMessagesChange={handleChatMessagesChange} />;
      case 'admin-users':
        return <AdminUsersPage />;
      case 'admin-audit':
        return <AdminAuditPage />;
      case 'admin-settings':
        return <AdminSettingsPage />;
      case 'admin-agents':
        return <AdminAgentsPage />;
      case 'admin-doc-types':
        return <AdminDocTypesPage />;
      default:
        return <DocumentsPage folderId={null} selectedDocumentId={null} onSelectDocument={handleOpenDocument} userRole={userRole} />;
    }
  }

  return (
    <div className="flex h-screen bg-cp-bg">
      <Toaster
        position="top-right"
        toastOptions={{
          style: { background: '#12122A', color: '#E2E8F0', border: '1px solid rgba(124, 58, 237, 0.25)' },
        }}
      />
      <Sidebar
        currentPage={page}
        onNavigate={handleNavigate}
        userRole={userRole}
        activeFolderId={activeFolderId}
        onSelectFolder={handleSelectFolder}
        onLogout={handleLogout}
      />
      <main className="flex-1 overflow-y-auto bg-cp-bg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
          {renderPage()}
        </div>
      </main>
    </div>
  );
}
