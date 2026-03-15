import { useState, useEffect, useCallback } from 'react';
import { ArrowLeft, Loader2, AlertCircle, CheckCircle, Scan, Brain, FileText, Eye, RotateCcw } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import PageSelector from '../components/PageSelector';
import ClassificationReview from '../components/ClassificationReview';
import {
  getProcessingStatus, triggerOcr, triggerClassify,
  updateProcessingMetadata, finalizeDocument,
  listDocTypes, getFolderTree,
} from '../services/api-v2';
import type { ProcessingStatus, DocType, FolderTreeNode } from '../types/dms';

interface DocumentProcessPageProps {
  documentId: number;
  onBack: () => void;
  onFinalized?: () => void;
}

type Phase = 'analyzing' | 'select-pages' | 'ocr-running' | 'ocr-done' | 'classifying' | 'review' | 'finalizing' | 'done' | 'failed';

function mapStatusToPhase(procStatus: string | null): Phase {
  switch (procStatus) {
    case 'pending':
    case 'analyzing':
      return 'analyzing';
    case 'analysis_done':
      return 'select-pages';
    case 'ocr_running':
      return 'ocr-running';
    case 'ocr_done':
      return 'ocr-done';
    case 'classifying':
      return 'classifying';
    case 'classified':
      return 'review';
    case 'finalizing':
      return 'finalizing';
    case 'completed':
      return 'done';
    case 'failed':
      return 'failed';
    default:
      return 'analyzing';
  }
}

const STEPS = [
  { key: 'analyzing', label: '预分析', icon: FileText },
  { key: 'select-pages', label: '选页OCR', icon: Scan },
  { key: 'classifying', label: 'LLM分类', icon: Brain },
  { key: 'review', label: '人工审核', icon: CheckCircle },
];

export default function DocumentProcessPage({ documentId, onBack, onFinalized }: DocumentProcessPageProps) {
  const [data, setData] = useState<ProcessingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [ocrLoading, setOcrLoading] = useState(false);
  const [classifyLoading, setClassifyLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [finalizeLoading, setFinalizeLoading] = useState(false);
  const [docTypes, setDocTypes] = useState<DocType[]>([]);
  const [folders, setFolders] = useState<FolderTreeNode[]>([]);
  const [showOcrText, setShowOcrText] = useState(false);
  const [reOcrProvider, setReOcrProvider] = useState<string>('');

  const fetchStatus = useCallback(async () => {
    try {
      const status = await getProcessingStatus(documentId);
      setData(status);
      return status;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '加载处理状态失败');
      return null;
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  // Load doc types and folders
  const refreshDocTypes = useCallback(() => {
    listDocTypes().then((d) => {
      const all: DocType[] = [];
      Object.values(d.doc_types).forEach((arr) => all.push(...arr));
      setDocTypes(all);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    refreshDocTypes();
    getFolderTree().then(setFolders).catch(() => {});
  }, [refreshDocTypes]);

  // Poll for status updates during async phases
  useEffect(() => {
    if (!data) return;
    const phase = mapStatusToPhase(data.processing_status);
    if (['analyzing', 'ocr-running', 'classifying', 'finalizing'].includes(phase)) {
      const timer = setInterval(async () => {
        const updated = await fetchStatus();
        if (updated) {
          const newPhase = mapStatusToPhase(updated.processing_status);
          if (!['analyzing', 'ocr-running', 'classifying', 'finalizing'].includes(newPhase)) {
            clearInterval(timer);
            setOcrLoading(false);
            setClassifyLoading(false);
            setFinalizeLoading(false);
          }
        }
      }, 2000);
      return () => clearInterval(timer);
    }
  }, [data?.processing_status, fetchStatus]);

  const handleOcrSubmit = async (pages: number[], provider?: string) => {
    if (pages.length === 0) {
      // Skip OCR, go directly to classify
      handleClassify();
      return;
    }
    setOcrLoading(true);
    try {
      await triggerOcr(documentId, pages, provider || undefined);
      // Immediately fetch to get ocr_running status so polling kicks in
      await fetchStatus();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'OCR启动失败');
      setOcrLoading(false);
    }
  };

  const handleClassify = async () => {
    setClassifyLoading(true);
    try {
      await triggerClassify(documentId);
      // Immediately fetch to get classifying status so polling kicks in
      await fetchStatus();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '分类启动失败');
      setClassifyLoading(false);
    }
  };

  const handleSaveMetadata = async (updates: {
    title: string;
    doc_type_id: number | null;
    folder_id: number | null;
    material_type: string | null;
  }) => {
    setSaving(true);
    try {
      await updateProcessingMetadata(documentId, {
        title: updates.title,
        doc_type_id: updates.doc_type_id || undefined,
        folder_id: updates.folder_id || undefined,
        material_type: updates.material_type || undefined,
      });
      toast.success('已保存');
      fetchStatus();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleFinalize = async (updates: {
    title: string;
    doc_type_id: number | null;
    folder_id: number | null;
  }) => {
    setFinalizeLoading(true);
    try {
      await finalizeDocument(documentId, {
        title: updates.title,
        doc_type_id: updates.doc_type_id || undefined,
        folder_id: updates.folder_id || undefined,
      });
      toast.success('文档已入库');
      onFinalized?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '入库失败');
      setFinalizeLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 text-cp-purple animate-spin" />
        <span className="ml-2 text-cp-muted">加载中...</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-20 text-cp-dim">
        <AlertCircle className="w-8 h-8 mx-auto mb-2" />
        <p>无法加载文档处理状态</p>
        <button onClick={onBack} className="mt-4 text-sm text-cp-purple-light hover:text-cp-purple">
          返回
        </button>
      </div>
    );
  }

  const phase = mapStatusToPhase(data.processing_status);

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={onBack} className="p-1 rounded hover:bg-white/5 text-cp-dim">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h2 className="text-lg font-orbitron font-semibold text-cp-text">{data.title}</h2>
          <p className="text-xs text-cp-dim">
            {data.file_type === 'pdf' ? `PDF · ${data.total_pages} 页` : data.file_type?.toUpperCase()}
          </p>
        </div>
      </div>

      {/* Progress steps */}
      <div className="flex items-center gap-1 mb-6">
        {STEPS.map((step, idx) => {
          const stepPhases: Record<string, string[]> = {
            'analyzing': ['analyzing'],
            'select-pages': ['select-pages', 'ocr-running'],
            'classifying': ['ocr-done', 'classifying'],
            'review': ['review', 'finalizing', 'done'],
          };
          const isActive = stepPhases[step.key]?.includes(phase);
          const isPast = STEPS.findIndex(s => stepPhases[s.key]?.includes(phase)) > idx;
          const Icon = step.icon;

          return (
            <div key={step.key} className="flex items-center flex-1">
              <div className={clsx(
                'flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all w-full justify-center',
                isActive ? 'bg-cp-purple/15 text-cp-purple-light border border-cp-purple/30' :
                isPast ? 'bg-green-500/10 text-green-400 border border-green-500/20' :
                'bg-cp-bg text-cp-dim border border-cp-border/30',
              )}>
                {isPast ? <CheckCircle className="w-3.5 h-3.5" /> : <Icon className="w-3.5 h-3.5" />}
                {step.label}
              </div>
              {idx < STEPS.length - 1 && (
                <div className={clsx('w-4 h-px mx-0.5 shrink-0', isPast ? 'bg-green-500/40' : 'bg-cp-border/30')} />
              )}
            </div>
          );
        })}
      </div>

      {/* Phase content */}
      <div className="cp-card rounded-lg p-5">
        {/* Analyzing */}
        {phase === 'analyzing' && (
          <div className="text-center py-12">
            <Loader2 className="w-8 h-8 text-cp-purple animate-spin mx-auto mb-3" />
            <p className="text-cp-muted">正在预分析文档...</p>
            <p className="text-xs text-cp-dim mt-1">检测页面类型、提取文本、生成缩略图</p>
          </div>
        )}

        {/* Page selection for OCR */}
        {phase === 'select-pages' && (
          <div>
            <h3 className="text-sm font-orbitron font-semibold text-cp-text mb-4 flex items-center gap-2">
              <Scan className="w-4 h-4 text-cp-cyan" />
              选择OCR页面
            </h3>
            {data.pages.length > 0 ? (
              <PageSelector
                pages={data.pages}
                suggestedPages={data.suggested_ocr_pages}
                onSubmit={handleOcrSubmit}
                loading={ocrLoading}
              />
            ) : (
              <div className="text-center py-8">
                <p className="text-cp-muted mb-4">该文档无需选页OCR</p>
                <button
                  onClick={handleClassify}
                  disabled={classifyLoading}
                  className="cp-btn-primary px-4 py-2 text-sm rounded-lg"
                >
                  {classifyLoading ? '分类中...' : '直接分类'}
                </button>
              </div>
            )}
          </div>
        )}

        {/* OCR running */}
        {phase === 'ocr-running' && (
          <div className="text-center py-12">
            <Loader2 className="w-8 h-8 text-cp-cyan animate-spin mx-auto mb-3" />
            <p className="text-cp-muted">OCR识别中...</p>
            <p className="text-xs text-cp-dim mt-1">正在识别选定的页面</p>
          </div>
        )}

        {/* OCR done - ready to classify */}
        {phase === 'ocr-done' && (
          <div className="text-center py-12">
            <Brain className="w-8 h-8 text-cp-purple mx-auto mb-3" />
            <p className="text-cp-text font-medium">OCR识别完成</p>
            <p className="text-xs text-cp-dim mt-2 mb-4">点击下方按钮启动LLM智能分类</p>
            <button
              onClick={handleClassify}
              disabled={classifyLoading}
              className="cp-btn-primary px-6 py-2.5 text-sm rounded-lg inline-flex items-center gap-2"
            >
              <Brain className="w-4 h-4" />
              {classifyLoading ? 'LLM分类启动中...' : '开始LLM分类'}
            </button>
          </div>
        )}

        {/* Classifying */}
        {phase === 'classifying' && (
          <div className="text-center py-12">
            <Loader2 className="w-8 h-8 text-cp-purple animate-spin mx-auto mb-3" />
            <p className="text-cp-muted">LLM分类中...</p>
            <p className="text-xs text-cp-dim mt-1">利用AI分析文档类型和提取元数据</p>
          </div>
        )}

        {/* Review */}
        {phase === 'review' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-orbitron font-semibold text-cp-text flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-cp-cyan" />
                核实分类结果
              </h3>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowOcrText(!showOcrText)}
                  className="cp-btn-ghost flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border border-cp-border"
                >
                  <Eye className="w-3.5 h-3.5" />
                  {showOcrText ? '隐藏OCR' : '查看OCR'}
                </button>
                <div className="flex items-center gap-1">
                  <select
                    value={reOcrProvider}
                    onChange={(e) => setReOcrProvider(e.target.value)}
                    className="cp-select text-xs rounded-lg px-2 py-1.5 border border-cp-border bg-transparent"
                  >
                    <option value="">默认引擎</option>
                    <option value="paddleocr">PaddleOCR (本地)</option>
                    <option value="bigmodel">BigModel (智谱)</option>
                    <option value="deepseek">DeepSeek</option>
                  </select>
                  <button
                    onClick={() => {
                      setShowOcrText(false);
                      const pages = data.ocr_pages.length > 0 ? data.ocr_pages : data.suggested_ocr_pages;
                      handleOcrSubmit(pages, reOcrProvider || undefined);
                    }}
                    disabled={ocrLoading}
                    className="cp-btn-ghost flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border border-cp-border text-cp-cyan"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    重新OCR
                  </button>
                </div>
                <button
                  onClick={handleClassify}
                  disabled={classifyLoading}
                  className="cp-btn-ghost flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border border-cp-border text-cp-purple-light"
                >
                  <Brain className="w-3.5 h-3.5" />
                  {classifyLoading ? '分类中...' : '重新分类'}
                </button>
              </div>
            </div>

            {/* OCR Text viewer */}
            {showOcrText && (
              <div className="mb-4 p-4 rounded-lg bg-cp-bg/50 border border-cp-border/30 max-h-64 overflow-auto">
                <p className="text-xs text-cp-dim mb-2 font-medium">OCR 识别文本：</p>
                {data.ocr_text ? (
                  <pre className="text-xs text-cp-muted whitespace-pre-wrap font-mono leading-relaxed">{data.ocr_text}</pre>
                ) : (
                  <p className="text-xs text-cp-dim italic">暂无OCR文本</p>
                )}
              </div>
            )}

            <ClassificationReview
              data={data}
              docTypes={docTypes}
              folders={folders}
              onSave={handleSaveMetadata}
              onFinalize={handleFinalize}
              onDocTypesChanged={refreshDocTypes}
              saving={saving}
              finalizing={finalizeLoading}
            />
          </div>
        )}

        {/* Finalizing */}
        {phase === 'finalizing' && (
          <div className="text-center py-12">
            <Loader2 className="w-8 h-8 text-green-400 animate-spin mx-auto mb-3" />
            <p className="text-cp-muted">正在入库...</p>
            <p className="text-xs text-cp-dim mt-1">实体链接、版本匹配、全文索引</p>
          </div>
        )}

        {/* Done */}
        {phase === 'done' && (
          <div className="text-center py-12">
            <CheckCircle className="w-8 h-8 text-green-400 mx-auto mb-3" />
            <p className="text-cp-text font-medium">处理完成</p>
            <p className="text-xs text-cp-dim mt-1">文档已成功入库</p>
            <button
              onClick={onBack}
              className="mt-4 cp-btn-primary px-4 py-2 text-sm rounded-lg"
            >
              返回列表
            </button>
          </div>
        )}

        {/* Failed */}
        {phase === 'failed' && (
          <div className="text-center py-12">
            <AlertCircle className="w-8 h-8 text-cp-rose mx-auto mb-3" />
            <p className="text-cp-rose font-medium">处理失败</p>
            {data.processing_error && (
              <p className="text-xs text-cp-dim mt-1">{data.processing_error}</p>
            )}
            <div className="flex justify-center gap-3 mt-4">
              <button onClick={onBack} className="cp-btn-ghost px-4 py-2 text-sm rounded-lg border border-cp-border">
                返回
              </button>
              <button
                onClick={() => { setLoading(true); fetchStatus(); }}
                className="cp-btn-primary px-4 py-2 text-sm rounded-lg"
              >
                重新加载
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
