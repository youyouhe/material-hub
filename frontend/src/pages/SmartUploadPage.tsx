import { useState, useCallback } from 'react';
import { Upload, CheckCircle, XCircle, FileText, Image as ImageIcon, Loader, Play } from 'lucide-react';
import toast from 'react-hot-toast';
import { uploadFileV2, uploadBatchV2, getProcessingStatus } from '../services/api-v2';
import PdfPageSelector from '../components/PdfPageSelector';

interface UploadResult {
  status: 'processing' | 'failed';
  filename: string;
  document_id?: number;
  error?: string;
}

interface BatchResult {
  total: number;
  succeeded: number;
  failed: number;
  results: UploadResult[];
}

interface ProgressData {
  stage: string;
  message: string;
  current_page: number;
  total_pages: number;
  ocr_results?: Array<{ page: number; chars: number; preview: string; status: string }>;
}

interface FileProgress {
  filename: string;
  status: 'waiting' | 'processing' | 'completed' | 'failed';
  progress?: ProgressData;
  result?: UploadResult;
}

export default function SmartUploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<BatchResult | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [fileProgress, setFileProgress] = useState<FileProgress[]>([]);
  const [importMode, setImportMode] = useState<'auto' | 'manual'>('auto');
  const [manualState, setManualState] = useState<{
    docId: number;
    totalPages: number;
    filename: string;
  } | null>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") setDragActive(true);
    else if (e.type === "dragleave") setDragActive(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const droppedFiles = Array.from(e.dataTransfer.files);
    if (droppedFiles.length > 0) {
      setFiles(prev => [...prev, ...droppedFiles]);
      setResults(null);
    }
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(prev => [...prev, ...Array.from(e.target.files!)]);
      setResults(null);
    }
  };

  const removeFile = (idx: number) => {
    setFiles(prev => prev.filter((_, i) => i !== idx));
  };

  const pollProgress = async (docId: number) => {
    try {
      const status = await getProcessingStatus(docId);
      const proc = status.processing_status;
      if (proc === 'completed' || proc === 'failed' || status.status === 'active') {
        return { done: true, status };
      }
      return { done: false, status };
    } catch {
      return { done: true, status: null };
    }
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setResults(null);

    const progressList: FileProgress[] = files.map(f => ({
      filename: f.name,
      status: 'waiting' as const,
    }));
    setFileProgress([...progressList]);

    if (files.length === 1) {
      // Single file with progress polling
      progressList[0].status = 'processing';
      setFileProgress([...progressList]);

      try {
        const r = await uploadFileV2(files[0]);
        const docId = r.document_id;

        // Poll for analysis
        let attempts = 0;
        while (attempts < 60) {
          await new Promise(resolve => setTimeout(resolve, 1500));
          const { done, status } = await pollProgress(docId);
          if (status) {
            progressList[0].progress = {
              stage: status.processing_status || 'analyzing',
              message: status.summary || status.processing_status || '处理中...',
              current_page: status.pages?.length || 0,
              total_pages: status.total_pages || 0,
            };
            setFileProgress([...progressList]);
          }
          if (done) {
            progressList[0].status = 'completed';
            progressList[0].result = {
              status: 'processing',
              filename: files[0].name,
              document_id: docId,
            };
            setFileProgress([...progressList]);
            setResults({ total: 1, succeeded: 1, failed: 0, results: [{ status: 'processing', filename: files[0].name, document_id: docId }] });
            toast.success('文件上传成功，请前往审核队列处理');
            setFiles([]);
            setUploading(false);
            return;
          }
          attempts++;
        }
        // Timeout — still succeeded in upload
        progressList[0].status = 'completed';
        progressList[0].result = { status: 'processing', filename: files[0].name, document_id: docId };
        setFileProgress([...progressList]);
        setResults({ total: 1, succeeded: 1, failed: 0, results: [{ status: 'processing', filename: files[0].name, document_id: docId }] });
        toast.success('文件已上传，后台处理中');
      } catch (err) {
        progressList[0].status = 'failed';
        progressList[0].result = { status: 'failed', filename: files[0].name, error: String(err) };
        setFileProgress([...progressList]);
        setResults({ total: 1, succeeded: 0, failed: 1, results: [{ status: 'failed', filename: files[0].name, error: String(err) }] });
        toast.error(`上传失败: ${err}`);
      }
      setUploading(false);
      return;
    }

    // Batch upload
    try {
      const batchResult = await uploadBatchV2(files);
      const results: UploadResult[] = batchResult.results.map(r => ({
        status: r.success ? 'processing' : 'failed',
        filename: r.filename,
        document_id: r.document_id,
        error: r.error,
      }));
      setResults({ total: batchResult.total, succeeded: batchResult.succeeded, failed: batchResult.failed, results });
      setFileProgress(files.map((f, i) => ({
        filename: f.name,
        status: batchResult.results[i]?.success ? 'completed' : 'failed',
        result: results[i],
      })));
      if (batchResult.succeeded > 0) toast.success(`${batchResult.succeeded} 个文件上传成功`);
      if (batchResult.failed > 0) toast.error(`${batchResult.failed} 个文件上传失败`);
    } catch (err) {
      toast.error(`批量上传失败: ${err}`);
    }
    setUploading(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-orbitron font-bold text-cp-text">智能导入</h1>
          <p className="text-cp-muted text-sm mt-1">上传文件自动识别分类</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setImportMode('auto')}
            className={`px-4 py-2 rounded-lg text-sm ${importMode === 'auto' ? 'bg-cp-purple text-white' : 'bg-cp-card border border-cp-divider text-cp-muted'}`}
          >
            自动模式
          </button>
          <button
            onClick={() => setImportMode('manual')}
            className={`px-4 py-2 rounded-lg text-sm ${importMode === 'manual' ? 'bg-cp-purple text-white' : 'bg-cp-card border border-cp-divider text-cp-muted'}`}
          >
            手动选页
          </button>
        </div>
      </div>

      {/* Manual page selector mode */}
      {manualState && importMode === 'manual' && (
        <PdfPageSelector
          docId={manualState.docId}
          totalPages={manualState.totalPages}
          filename={manualState.filename}
          onSubmit={async (selectedPages: number[], extractAllPages: boolean) => {
            toast.success(`已选择 ${extractAllPages ? '全部' : selectedPages.length} 页，请在审核队列中处理`);
            setManualState(null);
            setFiles([]);
          }}
          onCancel={() => { setManualState(null); setFiles([]); }}
        />
      )}

      {/* Drop zone */}
      {!manualState && (
        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors ${
            dragActive ? 'border-cp-purple bg-cp-purple/5' : 'border-cp-divider bg-cp-card'
          }`}
        >
          <Upload className="w-12 h-12 mx-auto text-cp-muted mb-4" />
          <p className="text-cp-text font-medium mb-1">拖拽文件到此处</p>
          <p className="text-cp-muted text-sm mb-4">支持 PDF、图片（JPG/PNG/TIFF）、Word 文档</p>
          <label className="cp-btn-primary inline-block cursor-pointer px-6 py-2.5 rounded-lg">
            选择文件
            <input type="file" multiple className="hidden" onChange={handleFileSelect}
              accept=".pdf,.jpg,.jpeg,.png,.tiff,.docx,.doc" />
          </label>
        </div>
      )}

      {/* File list */}
      {files.length > 0 && !manualState && (
        <div className="cp-card rounded-lg p-4">
          <h3 className="text-cp-text font-medium mb-3">已选择 {files.length} 个文件</h3>
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {files.map((f, i) => (
              <div key={i} className="flex items-center justify-between bg-cp-bg rounded p-2 px-3">
                <div className="flex items-center gap-2">
                  {f.type.startsWith('image') ? <ImageIcon className="w-4 h-4 text-cp-green" /> :
                   f.type === 'application/pdf' ? <FileText className="w-4 h-4 text-cp-rose" /> :
                   <FileText className="w-4 h-4 text-cp-blue" />}
                  <span className="text-sm text-cp-text truncate max-w-xs">{f.name}</span>
                  <span className="text-xs text-cp-muted">({(f.size / 1024).toFixed(0)}KB)</span>
                </div>
                <button onClick={() => removeFile(i)} className="text-cp-muted hover:text-cp-rose">
                  <XCircle className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
          <div className="flex gap-3 mt-4">
            <button onClick={handleUpload} disabled={uploading}
              className="cp-btn-primary px-6 py-2.5 rounded-lg flex items-center gap-2">
              {uploading ? <Loader className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {uploading ? '处理中...' : importMode === 'manual' ? '上传并选页' : '开始导入'}
            </button>
            <button onClick={() => { setFiles([]); setResults(null); }}
              className="px-4 py-2 text-sm text-cp-muted hover:text-cp-text">
              清空
            </button>
          </div>
        </div>
      )}

      {/* Progress */}
      {fileProgress.length > 0 && uploading && (
        <div className="cp-card rounded-lg p-4">
          <h3 className="text-cp-text font-medium mb-3">处理进度</h3>
          {fileProgress.map((fp, i) => (
            <div key={i} className="flex items-center gap-3 py-2 border-b border-cp-divider last:border-0">
              {fp.status === 'completed' ? <CheckCircle className="w-5 h-5 text-cp-green" /> :
               fp.status === 'failed' ? <XCircle className="w-5 h-5 text-cp-rose" /> :
               fp.status === 'processing' ? <Loader className="w-5 h-5 text-cp-blue animate-spin" /> :
               <div className="w-5 h-5 rounded-full border-2 border-cp-divider" />}
              <div className="flex-1 min-w-0">
                <p className="text-sm text-cp-text truncate">{fp.filename}</p>
                {fp.progress && (
                  <p className="text-xs text-cp-muted">
                    {fp.progress.stage} · {fp.progress.total_pages > 0 ? `${fp.progress.total_pages} 页` : ''}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Results */}
      {results && !uploading && (
        <div className="cp-card rounded-lg p-4">
          <h3 className="text-cp-text font-medium mb-3">
            导入结果: {results.succeeded} 成功, {results.failed} 失败
          </h3>
          <div className="space-y-2">
            {results.results.map((r, i) => (
              <div key={i} className="flex items-center gap-3 py-2 border-b border-cp-divider last:border-0">
                {r.status === 'processing' ? <CheckCircle className="w-5 h-5 text-cp-green" /> :
                 <XCircle className="w-5 h-5 text-cp-rose" />}
                <div>
                  <p className="text-sm text-cp-text">{r.filename}</p>
                  {r.error && <p className="text-xs text-cp-rose">{r.error}</p>}
                  {r.document_id && <p className="text-xs text-cp-muted">文档ID: {r.document_id}</p>}
                </div>
              </div>
            ))}
          </div>
          <button onClick={() => { setResults(null); setFileProgress([]); }}
            className="mt-3 text-sm text-cp-purple hover:underline">
            继续上传
          </button>
        </div>
      )}
    </div>
  );
}
