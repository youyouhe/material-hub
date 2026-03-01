import { useState } from 'react';
import { Check, FileText, ArrowLeft, RotateCcw, RotateCw } from 'lucide-react';
import toast from 'react-hot-toast';
import { getPageThumbnailUrl, rotatePendingReview } from '../services/api';

interface PdfPageSelectorProps {
  pendingId: number;
  totalPages: number;
  filename: string;
  onSubmit: (selectedPages: number[], extractAllPages: boolean) => void;
  onCancel: () => void;
}

export default function PdfPageSelector({
  pendingId,
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
      await rotatePendingReview(pendingId, direction);
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

  const handleSubmit = () => {
    const sorted = Array.from(selectedPages).sort((a, b) => a - b);
    onSubmit(sorted, extractAllPages);
  };

  const sortedSelection = Array.from(selectedPages).sort((a, b) => a - b);

  return (
    <div className="bg-white rounded-lg border border-gray-200 flex flex-col h-[calc(100vh-14rem)]">
      {/* 顶部操作栏 */}
      <div className="flex-shrink-0 border-b border-gray-200 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={onCancel}
              className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
            >
              <ArrowLeft className="w-4 h-4" />
              返回
            </button>
            <div>
              <h3 className="text-lg font-medium text-gray-900 flex items-center gap-2">
                <FileText className="w-5 h-5 text-blue-600" />
                选择要分析的页面
              </h3>
              <p className="text-sm text-gray-500">
                {filename} - 共 {totalPages} 页
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => handleRotate('left')}
              disabled={rotating}
              className="px-3 py-1.5 text-xs text-gray-600 hover:text-gray-800 bg-gray-50 hover:bg-gray-100 rounded-md border border-gray-200 flex items-center gap-1 disabled:opacity-50"
              title="向左旋转90°"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${rotating ? 'animate-spin' : ''}`} />
              旋转
            </button>
            <button
              onClick={() => handleRotate('right')}
              disabled={rotating}
              className="px-3 py-1.5 text-xs text-gray-600 hover:text-gray-800 bg-gray-50 hover:bg-gray-100 rounded-md border border-gray-200 flex items-center gap-1 disabled:opacity-50"
              title="向右旋转90°"
            >
              <RotateCw className={`w-3.5 h-3.5 ${rotating ? 'animate-spin' : ''}`} />
              旋转
            </button>
            <div className="w-px h-5 bg-gray-300" />
            <button
              onClick={selectFirstAndLast}
              className="px-3 py-1.5 text-xs text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-md border border-blue-200"
            >
              选首尾页
            </button>
            <button
              onClick={() => setSelectedPages(new Set())}
              className="px-3 py-1.5 text-xs text-gray-600 hover:text-gray-800 bg-gray-50 hover:bg-gray-100 rounded-md border border-gray-200"
            >
              清除
            </button>
          </div>
        </div>

        {/* 已选页面提示 + 提交按钮 */}
        <div className="space-y-2">
          <div className="text-sm text-gray-600">
            {selectedPages.size > 0 ? (
              <span>
                已选 <span className="font-semibold text-blue-600">{selectedPages.size}</span> 页：
                <span className="text-gray-500 ml-1">
                  {sortedSelection.length <= 10
                    ? sortedSelection.join(', ')
                    : sortedSelection.slice(0, 10).join(', ') + '...'}
                </span>
              </span>
            ) : (
              <span className="text-gray-400">点击页面缩略图选择要OCR分析的页面</span>
            )}
          </div>

          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer hover:text-gray-900">
              <input
                type="checkbox"
                checked={extractAllPages}
                onChange={(e) => setExtractAllPages(e.target.checked)}
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
              />
              <span>提取所有{totalPages}页为PNG（完整归档）</span>
            </label>

            <button
              onClick={handleSubmit}
              disabled={selectedPages.size === 0}
              className={`
                px-5 py-2 text-sm font-medium rounded-md transition-colors
                ${selectedPages.size > 0
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                }
              `}
            >
              分析选中的 {selectedPages.size} 页
            </button>
          </div>
        </div>
      </div>

      {/* 缩略图网格 */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-8 gap-3">
          {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => {
            const isSelected = selectedPages.has(page);
            return (
              <div
                key={page}
                onClick={() => togglePage(page)}
                className={`
                  cursor-pointer rounded-lg border-2 transition-all relative group
                  ${isSelected
                    ? 'border-blue-500 ring-2 ring-blue-200 bg-blue-50'
                    : 'border-gray-200 hover:border-blue-300 hover:shadow-sm'
                  }
                `}
              >
                {/* 选中标记 */}
                {isSelected && (
                  <div className="absolute top-1.5 right-1.5 z-10 bg-blue-500 text-white rounded-full w-5 h-5 flex items-center justify-center shadow-sm">
                    <Check className="w-3 h-3" />
                  </div>
                )}

                {/* 缩略图 */}
                <div className="aspect-[3/4] overflow-hidden rounded-t-md bg-gray-100">
                  <img
                    src={getPageThumbnailUrl(pendingId, page) + `&t=${thumbnailKey}`}
                    alt={`第 ${page} 页`}
                    loading="lazy"
                    className="w-full h-full object-contain"
                  />
                </div>

                {/* 页码 */}
                <div className={`
                  text-xs text-center py-1 font-medium
                  ${isSelected ? 'text-blue-700' : 'text-gray-500'}
                `}>
                  {page}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
