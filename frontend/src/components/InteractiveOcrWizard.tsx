import { useState, useEffect } from 'react';
import { Check, X, ChevronLeft, ChevronRight, SkipForward, CheckCheck, Loader, FileText } from 'lucide-react';
import toast from 'react-hot-toast';
import { getProcessingStatus, triggerOcr, triggerClassify, finalizeDocument, rotatePdfV2 } from '../services/api-v2';

interface Props {
  docId: number;
  onComplete: () => void;
  onCancel: () => void;
}

type PageDecision = 'yes' | 'no' | 'pending';

export default function InteractiveOcrWizard({ docId, onComplete, onCancel }: Props) {
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [currentPageIdx, setCurrentPageIdx] = useState(0);
  const [decisions, setDecisions] = useState<PageDecision[]>([]);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState('');
  const [thumbnailKey, setThumbnailKey] = useState(0);

  useEffect(() => { loadStatus(); }, [docId]);

  const loadStatus = async () => {
    try {
      const s = await getProcessingStatus(docId);
      setStatus(s);
      const total = s.pages?.length || s.total_pages || 0;
      setDecisions(new Array(total).fill('pending'));
    } catch (err) {
      toast.error('加载文档信息失败');
    } finally {
      setLoading(false);
    }
  };

  const totalPages = decisions.length;
  const currentPage = status?.pages?.[currentPageIdx];
  const pageNum = currentPage?.page_num ?? currentPageIdx;
  const yesCount = decisions.filter(d => d === 'yes').length;
  const pendingCount = decisions.filter(d => d === 'pending').length;

  const decide = (decision: 'yes' | 'no') => {
    setDecisions(prev => prev.map((d, i) => i === currentPageIdx ? decision : d));
    if (currentPageIdx < totalPages - 1) {
      setCurrentPageIdx(currentPageIdx + 1);
    }
  };

  const decideAllRemaining = (decision: 'yes' | 'no') => {
    setDecisions(prev => prev.map((d, i) => i >= currentPageIdx ? decision : d));
  };

  const handleRotate = async (direction: 'left' | 'right') => {
    try {
      await rotatePdfV2(docId, direction);
      setThumbnailKey(prev => prev + 1);
      toast.success('已旋转');
    } catch { toast.error('旋转失败'); }
  };

  const handleStartOcr = async () => {
    if (yesCount === 0) {
      toast.error('请至少选择一页进行 OCR');
      return;
    }
    setProcessing(true);
    setProgress(`正在 OCR ${yesCount} 页...`);
    try {
      const selectedPages = decisions
        .map((d, i) => (d === 'yes' ? i : -1))
        .filter(i => i >= 0)
        .map(i => i + 1); // convert to 1-indexed

      await triggerOcr(docId, selectedPages);
      setProgress('OCR 完成，正在 AI 分析...');
      await triggerClassify(docId);
      setProgress('正在归档...');
      await finalizeDocument(docId);
      toast.success(`完成！已 OCR ${yesCount} 页并归档`);
      onComplete();
    } catch (err: any) {
      toast.error(`处理失败: ${err.message}`);
      setProcessing(false);
    }
  };

  if (loading) {
    return (
      <div className="cp-card rounded-lg p-8 text-center">
        <Loader className="w-8 h-8 text-cp-purple animate-spin mx-auto" />
        <p className="text-cp-muted mt-3">加载页面信息...</p>
      </div>
    );
  }

  if (processing) {
    return (
      <div className="cp-card rounded-lg p-8 text-center">
        <Loader className="w-8 h-8 text-cp-purple animate-spin mx-auto" />
        <p className="text-cp-text font-medium mt-3">{progress}</p>
        <p className="text-cp-muted text-sm mt-1">请稍候，正在调用 BigModel + DeepSeek...</p>
      </div>
    );
  }

  return (
    <div className="cp-card rounded-lg p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-cp-text">选择 OCR 页面</h3>
          <p className="text-cp-muted text-sm">
            {status?.title} · {totalPages} 页 · 已选 {yesCount} 页 OCR
          </p>
        </div>
        <button onClick={onCancel} className="text-cp-dim hover:text-cp-text">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Progress bar */}
      <div className="flex items-center gap-1">
        {decisions.map((d, i) => (
          <div key={i}
            className={`flex-1 h-1.5 rounded-full transition-colors ${
              i === currentPageIdx ? 'ring-2 ring-cp-purple' : ''
            } ${
              d === 'yes' ? 'bg-cp-green' : d === 'no' ? 'bg-cp-rose/40' : 'bg-cp-border'
            }`}
            title={`第${i+1}页: ${d === 'yes' ? 'OCR' : d === 'no' ? '跳过' : '待定'}`}
          />
        ))}
      </div>

      {/* Page preview */}
      {currentPage && (
        <div className="flex gap-4">
          <div className="w-64 h-80 shrink-0 bg-cp-bg rounded-lg overflow-hidden border border-cp-border flex items-center justify-center">
            {currentPage.thumbnail_url ? (
              <img
                key={thumbnailKey}
                src={`${currentPage.thumbnail_url}&_t=${thumbnailKey}`}
                alt={`第${pageNum + 1}页`}
                className="w-full h-full object-contain"
              />
            ) : (
              <FileText className="w-12 h-12 text-cp-dim" />
            )}
          </div>
          <div className="flex-1 space-y-3">
            <div className="bg-cp-bg rounded p-3 text-sm">
              <p className="text-cp-text font-medium">第 {pageNum + 1} / {totalPages} 页</p>
              <div className="mt-2 space-y-1 text-xs text-cp-muted">
                {currentPage.has_text && <p>📝 已有文字: {currentPage.text_length} 字符</p>}
                {currentPage.needs_ocr && <p>🔍 需要 OCR 识别</p>}
                {currentPage.ocr_text && <p className="text-cp-green">✅ 已 OCR: {currentPage.ocr_text.length} 字符</p>}
              </div>
              {currentPage.ocr_text && (
                <p className="mt-2 text-xs text-cp-dim line-clamp-3">{currentPage.ocr_text}</p>
              )}
            </div>

            {/* Navigation */}
            <div className="flex items-center gap-1">
              <button onClick={() => setCurrentPageIdx(Math.max(0, currentPageIdx - 1))}
                disabled={currentPageIdx === 0}
                className="p-1.5 rounded hover:bg-cp-purple/10 disabled:opacity-30">
                <ChevronLeft className="w-4 h-4 text-cp-muted" />
              </button>
              <span className="text-xs text-cp-muted px-2">
                {currentPageIdx + 1} / {totalPages}
              </span>
              <button onClick={() => setCurrentPageIdx(Math.min(totalPages - 1, currentPageIdx + 1))}
                disabled={currentPageIdx === totalPages - 1}
                className="p-1.5 rounded hover:bg-cp-purple/10 disabled:opacity-30">
                <ChevronRight className="w-4 h-4 text-cp-muted" />
              </button>
              <div className="flex-1" />
              <button onClick={() => handleRotate('left')}
                className="px-2 py-1 text-xs rounded border border-cp-border text-cp-muted hover:text-cp-text">
                左转
              </button>
              <button onClick={() => handleRotate('right')}
                className="px-2 py-1 text-xs rounded border border-cp-border text-cp-muted hover:text-cp-text">
                右转
              </button>
            </div>

            {/* Vote buttons */}
            <div className="flex gap-2">
              <button onClick={() => decide('no')}
                className="flex-1 py-2.5 rounded-lg border border-cp-rose/30 text-cp-rose hover:bg-cp-rose/10 flex items-center justify-center gap-2 text-sm">
                <X className="w-4 h-4" /> 跳过此页
              </button>
              <button onClick={() => decide('yes')}
                className="flex-1 py-2.5 rounded-lg bg-cp-purple/20 border border-cp-purple/40 text-cp-purple-light hover:bg-cp-purple/30 flex items-center justify-center gap-2 text-sm font-medium">
                <Check className="w-4 h-4" /> OCR 此页
              </button>
            </div>

            {/* Shortcuts */}
            {pendingCount > 1 && (
              <div className="flex gap-2">
                <button onClick={() => decideAllRemaining('no')}
                  className="flex-1 py-1.5 rounded text-xs border border-cp-border text-cp-dim hover:text-cp-muted flex items-center justify-center gap-1">
                  <SkipForward className="w-3 h-3" /> 剩余全部跳过
                </button>
                <button onClick={() => decideAllRemaining('yes')}
                  className="flex-1 py-1.5 rounded text-xs bg-cp-purple/10 border border-cp-purple/20 text-cp-purple-light hover:bg-cp-purple/20 flex items-center justify-center gap-1">
                  <CheckCheck className="w-3 h-3" /> 剩余全部 OCR
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Start OCR button */}
      <div className="flex items-center justify-between border-t border-cp-border pt-3">
        <p className="text-xs text-cp-muted">
          {yesCount > 0
            ? `已选 ${yesCount} 页进行 OCR`
            : '请至少选择一页'}
        </p>
        <button onClick={handleStartOcr} disabled={yesCount === 0}
          className="px-6 py-2.5 cp-btn-primary rounded-lg flex items-center gap-2 disabled:opacity-40">
          <Check className="w-4 h-4" />
          {yesCount > 0 ? `开始 OCR (${yesCount} 页)` : '请选择页面'}
        </button>
      </div>
    </div>
  );
}
