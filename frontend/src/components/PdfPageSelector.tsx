import { useState } from 'react';
import { Check, ArrowLeft, RotateCcw, RotateCw } from 'lucide-react';
import toast from 'react-hot-toast';
import { getPageThumbnailUrlV2, rotatePdfV2 } from '../services/api-v2';

interface PdfPageSelectorProps {
  docId: number;
  totalPages: number;
  filename: string;
  onSubmit: (selectedPages: number[], extractAllPages: boolean) => void;
  onCancel: () => void;
}

export default function PdfPageSelector({
  docId,
  totalPages,
  filename,
  onSubmit,
  onCancel,
}: PdfPageSelectorProps) {
  const [selectedPages, setSelectedPages] = useState<Set<number>>(new Set());
  const [extractAllPages, setExtractAllPages] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [thumbnailKey, setThumbnailKey] = useState(0);

  const handleRotate = async (direction: 'left' | 'right') => {
    setRotating(true);
    try {
      await rotatePdfV2(docId, direction);
      setThumbnailKey(prev => prev + 1);
      toast.success(`已向${direction === 'left' ? '左' : '右'}旋转90°`);
    } catch (error) {
      toast.error('旋转失败: ' + (error instanceof Error ? error.message : '未知错误'));
    } finally {
      setRotating(false);
    }
  };

  const togglePage = (page: number) => {
    setSelectedPages(prev => {
      const next = new Set(prev);
      if (next.has(page)) next.delete(page);
      else next.add(page);
      return next;
    });
  };

  const selectFirstAndLast = () => {
    const pages = new Set<number>();
    pages.add(1);
    if (totalPages > 1) pages.add(totalPages);
    setSelectedPages(pages);
  };

  const toggleAll = () => {
    if (selectedPages.size === totalPages) {
      setSelectedPages(new Set());
      setExtractAllPages(false);
    } else {
      const all = new Set<number>();
      for (let i = 1; i <= totalPages; i++) all.add(i);
      setSelectedPages(all);
    }
  };

  const handleSubmit = () => {
    if (!extractAllPages && selectedPages.size === 0) {
      toast.error('请至少选择一页');
      return;
    }
    onSubmit(Array.from(selectedPages).sort((a, b) => a - b), extractAllPages);
  };

  return (
    <div className="cp-card rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <button onClick={onCancel} className="text-cp-muted hover:text-cp-text">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h3 className="text-cp-text font-medium">{filename}</h3>
            <p className="text-xs text-cp-muted">{totalPages} 页 · 请选择要提取的页面</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button onClick={() => handleRotate('left')} disabled={rotating}
            className="px-3 py-1.5 rounded bg-cp-bg border border-cp-divider text-cp-muted hover:text-cp-text text-sm flex items-center gap-1">
            <RotateCcw className="w-3.5 h-3.5" /> 左转
          </button>
          <button onClick={() => handleRotate('right')} disabled={rotating}
            className="px-3 py-1.5 rounded bg-cp-bg border border-cp-divider text-cp-muted hover:text-cp-text text-sm flex items-center gap-1">
            <RotateCw className="w-3.5 h-3.5" /> 右转
          </button>
        </div>
      </div>

      <div className="flex gap-2 mb-4">
        <button onClick={toggleAll}
          className="text-xs px-3 py-1 rounded bg-cp-bg border border-cp-divider text-cp-muted hover:text-cp-text">
          {selectedPages.size === totalPages ? '取消全选' : '全选'}
        </button>
        <button onClick={selectFirstAndLast}
          className="text-xs px-3 py-1 rounded bg-cp-bg border border-cp-divider text-cp-muted hover:text-cp-text">
          首页+末页
        </button>
      </div>

      <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-3 max-h-96 overflow-y-auto">
        {Array.from({ length: totalPages }, (_, i) => i + 1).map(pageNum => (
          <div key={`${pageNum}-${thumbnailKey}`} onClick={() => togglePage(pageNum)}
            className={`relative cursor-pointer rounded-lg overflow-hidden border-2 transition-all ${
              selectedPages.has(pageNum) ? 'border-cp-purple shadow-lg shadow-cp-purple/20' : 'border-transparent hover:border-cp-divider'
            }`}>
            <img
              src={getPageThumbnailUrlV2(docId, pageNum)}
              alt={`第${pageNum}页`}
              className="w-full h-32 object-cover"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
            <div className="absolute top-1 left-1 bg-black/60 text-white text-xs px-1.5 py-0.5 rounded">
              {pageNum}
            </div>
            {selectedPages.has(pageNum) && (
              <div className="absolute top-1 right-1 bg-cp-purple text-white rounded-full w-5 h-5 flex items-center justify-center">
                <Check className="w-3 h-3" />
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between mt-4 pt-3 border-t border-cp-divider">
        <label className="flex items-center gap-2 text-sm text-cp-muted cursor-pointer">
          <input type="checkbox" checked={extractAllPages} onChange={e => setExtractAllPages(e.target.checked)}
            className="rounded border-cp-divider" />
          提取全部页面
        </label>
        <div className="flex gap-2">
          <button onClick={onCancel} className="px-4 py-2 text-sm text-cp-muted hover:text-cp-text">
            取消
          </button>
          <button onClick={handleSubmit} disabled={!extractAllPages && selectedPages.size === 0}
            className="cp-btn-primary px-4 py-2 rounded-lg text-sm flex items-center gap-2">
            <Check className="w-4 h-4" />
            确认选择 ({extractAllPages ? '全部' : selectedPages.size}页)
          </button>
        </div>
      </div>
    </div>
  );
}
