import { useState, useCallback } from 'react';
import { Toaster } from 'react-hot-toast';
import { Upload, Search } from 'lucide-react';
import clsx from 'clsx';
import UploadPage from './pages/UploadPage';
import BrowsePage from './pages/BrowsePage';

type Tab = 'upload' | 'browse';

export default function App() {
  const [tab, setTab] = useState<Tab>('browse');
  const [refreshKey, setRefreshKey] = useState(0);

  const handleExtracted = useCallback(() => {
    setRefreshKey((k) => k + 1);
  }, []);

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
                onClick={() => setTab('browse')}
                className={clsx(
                  'flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg transition-colors',
                  tab === 'browse'
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-100'
                )}
              >
                <Search className="w-4 h-4" />
                Browse
              </button>
              <button
                onClick={() => setTab('upload')}
                className={clsx(
                  'flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg transition-colors',
                  tab === 'upload'
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-100'
                )}
              >
                <Upload className="w-4 h-4" />
                Upload
              </button>
            </nav>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {tab === 'upload' ? (
          <UploadPage onExtracted={handleExtracted} />
        ) : (
          <BrowsePage key={refreshKey} />
        )}
      </main>
    </div>
  );
}
