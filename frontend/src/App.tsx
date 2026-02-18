import { useState, useCallback } from 'react';
import { Toaster } from 'react-hot-toast';
import { Upload, Search, Building2, Users, Home } from 'lucide-react';
import clsx from 'clsx';
import HomePage from './pages/HomePage';
import UploadPage from './pages/UploadPage';
import BrowsePage from './pages/BrowsePage';
import CompaniesPage from './pages/CompaniesPage';
import PersonsPage from './pages/PersonsPage';

type Tab = 'home' | 'upload' | 'browse' | 'companies' | 'persons';

export default function App() {
  const [tab, setTab] = useState<Tab>('home');
  const [refreshKey, setRefreshKey] = useState(0);

  const handleTabChange = useCallback((newTab: Tab) => {
    setTab(newTab);
    // 切换到这些页面时刷新数据
    if (newTab === 'home' || newTab === 'browse') {
      setRefreshKey((k) => k + 1);
    }
  }, []);

  const handleExtracted = useCallback(() => {
    setRefreshKey((k) => k + 1);
    handleTabChange('home'); // 上传完成后跳转到首页查看结构化信息
  }, [handleTabChange]);

  return (
    <div className="min-h-screen bg-gray-50">
      <Toaster position="top-right" />

      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between h-14">
            <h1 className="text-lg font-semibold text-gray-900">MaterialHub</h1>

            <nav className="flex gap-1">
              <button
                onClick={() => handleTabChange('home')}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg transition-colors',
                  tab === 'home'
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-100'
                )}
              >
                <Home className="w-4 h-4" />
                首页
              </button>
              <button
                onClick={() => handleTabChange('browse')}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg transition-colors',
                  tab === 'browse'
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-100'
                )}
              >
                <Search className="w-4 h-4" />
                素材
              </button>
              <button
                onClick={() => handleTabChange('companies')}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg transition-colors',
                  tab === 'companies'
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-100'
                )}
              >
                <Building2 className="w-4 h-4" />
                公司
              </button>
              <button
                onClick={() => handleTabChange('persons')}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg transition-colors',
                  tab === 'persons'
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-100'
                )}
              >
                <Users className="w-4 h-4" />
                人员
              </button>
              <button
                onClick={() => handleTabChange('upload')}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg transition-colors',
                  tab === 'upload'
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-100'
                )}
              >
                <Upload className="w-4 h-4" />
                上传
              </button>
            </nav>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {tab === 'home' && <HomePage key={refreshKey} />}
        {tab === 'upload' && <UploadPage onExtracted={handleExtracted} />}
        {tab === 'browse' && <BrowsePage key={refreshKey} />}
        {tab === 'companies' && <CompaniesPage />}
        {tab === 'persons' && <PersonsPage />}
      </main>
    </div>
  );
}
