import { useState, useMemo } from 'react';
import { Check, Eye, FileText, Scan, AlertTriangle } from 'lucide-react';
import clsx from 'clsx';
import type { PageInfo } from '../types/dms';

const DEFAULT_MAX_PAGES = 3;

interface PageSelectorProps {
  pages: PageInfo[];
  suggestedPages: number[];
  onSubmit: (selectedPages: number[]) => void;
  loading?: boolean;
}

export default function PageSelector({ pages, suggestedPages, onSubmit, loading }: PageSelectorProps) {
  // Default: select the first N pages that need OCR (max DEFAULT_MAX_PAGES)
  const defaultPages = useMemo(() => {
    const ocrPages = pages.filter((p) => p.needs_ocr).map((p) => p.page_num);
    return new Set(ocrPages.slice(0, DEFAULT_MAX_PAGES));
  }, [pages]);

  const [selected, setSelected] = useState<Set<number>>(defaultPages);
  const [previewPage, setPreviewPage] = useState<number | null>(null);
  const [showAllWarning, setShowAllWarning] = useState(false);

  const allOcrPages = useMemo(
    () => pages.filter((p) => p.needs_ocr).map((p) => p.page_num),
    [pages],
  );

  const toggle = (pageNum: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(pageNum)) next.delete(pageNum);
      else next.add(pageNum);
      return next;
    });
  };

  const selectAll = () => {
    if (allOcrPages.length > DEFAULT_MAX_PAGES) {
      setShowAllWarning(true);
    } else {
      setSelected(new Set(allOcrPages));
    }
  };

  const confirmSelectAll = () => {
    setSelected(new Set(allOcrPages));
    setShowAllWarning(false);
  };

  const selectNone = () => { setSelected(new Set()); setShowAllWarning(false); };

  const selectSuggested = () => { setSelected(new Set(suggestedPages)); setShowAllWarning(false); };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm text-cp-muted">
          选择需要OCR识别的页面（<span className="text-cp-cyan">{selected.size}</span> 页已选）
        </p>
        <div className="flex gap-2 text-xs">
          <button onClick={selectSuggested} className="text-cp-purple-light hover:text-cp-purple">
            推荐选择
          </button>
          <span className="text-cp-border">|</span>
          <button onClick={selectAll} className="text-cp-muted hover:text-cp-text">
            全选扫描页
          </button>
          <span className="text-cp-border">|</span>
          <button onClick={selectNone} className="text-cp-muted hover:text-cp-text">
            取消全选
          </button>
        </div>
      </div>

      <div className="grid grid-cols-4 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-8 gap-3">
        {pages.map((page) => {
          const isSelected = selected.has(page.page_num);
          const isSuggested = suggestedPages.includes(page.page_num);

          return (
            <div
              key={page.page_num}
              className={clsx(
                'relative group rounded-lg border-2 overflow-hidden cursor-pointer transition-all',
                isSelected
                  ? 'border-cp-purple ring-1 ring-cp-purple/30'
                  : page.has_text
                    ? 'border-cp-border/30 opacity-70'
                    : 'border-cp-border hover:border-cp-purple/50',
              )}
              onClick={() => toggle(page.page_num)}
            >
              {/* Thumbnail */}
              <div className="aspect-[3/4] bg-cp-bg relative">
                {page.thumbnail_url ? (
                  <img
                    src={page.thumbnail_url}
                    alt={`Page ${page.page_num + 1}`}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div className="flex items-center justify-center h-full">
                    <FileText className="w-8 h-8 text-cp-dim" />
                  </div>
                )}

                {/* Selection overlay */}
                {isSelected && (
                  <div className="absolute inset-0 bg-cp-purple/20 flex items-center justify-center">
                    <div className="w-6 h-6 rounded-full bg-cp-purple flex items-center justify-center">
                      <Check className="w-4 h-4 text-white" />
                    </div>
                  </div>
                )}

                {/* Preview button */}
                <button
                  className="absolute top-1 right-1 p-1 rounded bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={(e) => {
                    e.stopPropagation();
                    setPreviewPage(page.page_num);
                  }}
                >
                  <Eye className="w-3 h-3" />
                </button>
              </div>

              {/* Page info bar */}
              <div className="px-1.5 py-1 bg-cp-card flex items-center justify-between">
                <span className="text-xs text-cp-dim">P{page.page_num + 1}</span>
                <div className="flex items-center gap-1">
                  {page.has_text ? (
                    <span className="text-[10px] text-green-400 flex items-center gap-0.5">
                      <FileText className="w-2.5 h-2.5" /> 文本
                    </span>
                  ) : (
                    <span className="text-[10px] text-amber-400 flex items-center gap-0.5">
                      <Scan className="w-2.5 h-2.5" /> 扫描
                    </span>
                  )}
                  {isSuggested && !page.has_text && (
                    <span className="w-1.5 h-1.5 rounded-full bg-cp-purple" title="推荐OCR" />
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Select-all warning */}
      {showAllWarning && (
        <div className="mt-4 p-4 rounded-lg bg-amber-900/20 border border-amber-500/30">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-amber-300">
                确定要全选 {allOcrPages.length} 页进行OCR？
              </p>
              <p className="text-xs text-amber-400/80 mt-1">
                全部页面OCR将消耗较多时间和Token，通常前几页已包含关键信息（证书编号、有效期、公司名称等）。
                建议仅选择包含关键信息的页面。
              </p>
              <div className="flex gap-2 mt-3">
                <button
                  onClick={confirmSelectAll}
                  className="px-3 py-1.5 text-xs rounded-lg bg-amber-600/30 text-amber-300 border border-amber-500/30 hover:bg-amber-600/50 transition-colors"
                >
                  确认全选 {allOcrPages.length} 页
                </button>
                <button
                  onClick={() => setShowAllWarning(false)}
                  className="px-3 py-1.5 text-xs rounded-lg text-cp-muted hover:text-cp-text border border-cp-border/30 hover:border-cp-border transition-colors"
                >
                  取消
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Submit */}
      <div className="flex items-center justify-between mt-4 pt-4 border-t border-cp-border/50">
        <p className="text-xs text-cp-dim">
          {pages.filter((p) => p.has_text).length} 页可直接提取文本，
          {pages.filter((p) => p.needs_ocr).length} 页需要OCR
        </p>
        <button
          onClick={() => onSubmit(Array.from(selected).sort((a, b) => a - b))}
          disabled={loading}
          className="cp-btn-primary px-4 py-2 text-sm rounded-lg disabled:opacity-40 flex items-center gap-1"
        >
          <Scan className="w-4 h-4" />
          {loading ? 'OCR识别中...' : selected.size > 0 ? `识别 ${selected.size} 页` : '跳过OCR'}
        </button>
      </div>

      {/* Preview modal */}
      {previewPage !== null && (
        <div
          className="cp-overlay fixed inset-0 flex items-center justify-center z-50"
          onClick={() => setPreviewPage(null)}
        >
          <div
            className="cp-card rounded-lg p-4 max-w-2xl max-h-[90vh] overflow-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-medium text-cp-text">第 {previewPage + 1} 页</span>
              <button onClick={() => setPreviewPage(null)} className="text-cp-dim hover:text-cp-text text-sm">
                关闭
              </button>
            </div>
            {pages[previewPage]?.thumbnail_url && (
              <img
                src={pages[previewPage].thumbnail_url}
                alt={`Page ${previewPage + 1}`}
                className="max-w-full"
              />
            )}
            {pages[previewPage]?.has_text && pages[previewPage]?.text_length > 0 && (
              <p className="mt-2 text-xs text-cp-dim">
                此页有 {pages[previewPage].text_length} 个字符的可提取文本
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
