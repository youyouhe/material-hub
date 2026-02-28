import { useState, useCallback, useRef } from 'react';
import { Upload, CheckCircle, AlertCircle, XCircle, FileText, Image as ImageIcon, Loader } from 'lucide-react';
import toast from 'react-hot-toast';
import { smartImportSingle, getPendingReviewProgress, getPendingReview } from '../services/api';

interface UploadResult {
  status: 'auto_archived' | 'pending_review' | 'failed' | 'processing';
  filename: string;
  confidence?: number;
  material_id?: number;
  pending_id?: number;
  message?: string;
  error?: string;
}

interface BatchResult {
  total: number;
  auto_archived: number;
  pending_review: number;
  failed: number;
  items: UploadResult[];
}

interface ProgressData {
  stage: string;
  message: string;
  current_page: number;
  total_pages: number;
  ocr_results?: Array<{
    page: number;
    chars: number;
    preview: string;
    status: string;
  }>;
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
  const progressIntervalRef = useRef<number | null>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const droppedFiles = Array.from(e.dataTransfer.files);
    setFiles(prev => [...prev, ...droppedFiles]);
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selectedFiles = Array.from(e.target.files);
      setFiles(prev => [...prev, ...selectedFiles]);
    }
  };

  const removeFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleBatchUpload = async () => {
    if (files.length === 0) {
      toast.error('请先选择文件');
      return;
    }

    setUploading(true);
    setResults(null);

    // 初始化进度状态
    const initialProgress: FileProgress[] = files.map(file => ({
      filename: file.name,
      status: 'waiting',
    }));
    setFileProgress(initialProgress);

    const uploadResults: UploadResult[] = [];
    let autoArchived = 0;
    let pendingReview = 0;
    let failed = 0;

    try {
      // 顺序处理每个文件
      for (let i = 0; i < files.length; i++) {
        const file = files[i];

        // 更新当前文件状态为处理中
        setFileProgress(prev => {
          const updated = [...prev];
          updated[i] = { ...updated[i], status: 'processing' };
          return updated;
        });

        try {
          // 上传文件
          const result = await smartImportSingle(file);

          // 如果返回 processing 状态且有 pending_id，开始轮询进度
          if (result.status === 'processing' && result.pending_id) {
            const pendingId = result.pending_id;

            // 清除之前的定时器
            if (progressIntervalRef.current) {
              clearInterval(progressIntervalRef.current);
            }

            // 轮询进度直到处理完成
            let finalResult: UploadResult = result as UploadResult;
            await new Promise<void>((resolve) => {
              progressIntervalRef.current = setInterval(async () => {
                try {
                  const progressData = await getPendingReviewProgress(pendingId);

                  if (progressData.status === 'processing' && progressData.progress) {
                    // 更新当前文件的进度
                    setFileProgress(prev => {
                      const updated = [...prev];
                      updated[i] = {
                        ...updated[i],
                        status: 'processing',
                        progress: progressData.progress,
                      };
                      return updated;
                    });
                  } else {
                    // 处理完成，停止轮询
                    if (progressIntervalRef.current) {
                      clearInterval(progressIntervalRef.current);
                      progressIntervalRef.current = null;
                    }

                    // 获取最终结果
                    try {
                      const pendingItem = await getPendingReview(pendingId);

                      // 映射后台状态到前端状态
                      let mappedStatus: 'auto_archived' | 'pending_review' | 'failed' = 'pending_review';
                      if (pendingItem.status === 'approved') {
                        mappedStatus = 'auto_archived';
                      } else if (pendingItem.status === 'pending') {
                        mappedStatus = 'pending_review';
                      } else if (pendingItem.status === 'rejected' || pendingItem.status === 'processing') {
                        mappedStatus = 'failed';
                      }

                      finalResult = {
                        status: mappedStatus,
                        pending_id: pendingId,
                        material_id: pendingItem.material_id,
                        filename: pendingItem.filename,
                        confidence: pendingItem.confidence || 0,
                        message: mappedStatus === 'auto_archived' ? '已自动归档' : (mappedStatus === 'pending_review' ? '需要人工审核' : '处理失败'),
                        ...(mappedStatus === 'failed' && { error: pendingItem.review_notes || '处理失败' }),
                      } as UploadResult;
                    } catch (err) {
                      console.error('获取最终结果失败:', err);
                    }

                    resolve();
                  }
                } catch (error) {
                  console.error('获取进度失败:', error);
                  // 继续轮询
                }
              }, 1000);
            });

            // 使用最终结果
            result.status = finalResult.status;
            result.material_id = finalResult.material_id;
            result.confidence = finalResult.confidence || 0;
            result.message = finalResult.message;
            if (finalResult.error) {
              (result as any).error = finalResult.error;
            }
          }

          // 类型转换 - 确保 status 符合 UploadResult 类型
          const uploadResult: UploadResult = {
            status: result.status as 'auto_archived' | 'pending_review' | 'failed' | 'processing',
            filename: result.filename,
            confidence: result.confidence,
            material_id: result.material_id,
            pending_id: result.pending_id,
            message: result.message,
            error: (result as any).error,
          };

          // 更新结果
          uploadResults.push(uploadResult);

          if (uploadResult.status === 'auto_archived') {
            autoArchived++;
          } else if (uploadResult.status === 'pending_review') {
            pendingReview++;
          } else {
            failed++;
          }

          // 更新当前文件状态为完成
          setFileProgress(prev => {
            const updated = [...prev];
            updated[i] = {
              ...updated[i],
              status: 'completed',
              result: uploadResult,
            };
            return updated;
          });

        } catch (error) {
          console.error(`处理文件失败: ${file.name}`, error);
          failed++;

          const errorResult: UploadResult = {
            status: 'failed',
            filename: file.name,
            error: error instanceof Error ? error.message : '处理失败',
          };
          uploadResults.push(errorResult);

          // 更新当前文件状态为失败
          setFileProgress(prev => {
            const updated = [...prev];
            updated[i] = {
              ...updated[i],
              status: 'failed',
              result: errorResult,
            };
            return updated;
          });
        }
      }

      // 汇总结果
      const batchResult: BatchResult = {
        total: files.length,
        auto_archived: autoArchived,
        pending_review: pendingReview,
        failed: failed,
        items: uploadResults,
      };

      setResults(batchResult);

      if (autoArchived > 0) {
        toast.success(`成功自动归档 ${autoArchived} 个文件`);
      }
      if (pendingReview > 0) {
        toast(`${pendingReview} 个文件需要人工审核`, { icon: '⚠️' });
      }
      if (failed > 0) {
        toast.error(`${failed} 个文件处理失败`);
      }

      // 清空文件列表
      setFiles([]);

    } catch (error) {
      console.error('上传错误:', error);
      toast.error('批量上传失败');
    } finally {
      setUploading(false);

      // 清除定时器
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
        progressIntervalRef.current = null;
      }
    }
  };

  const getFileIcon = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase();
    if (['jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff'].includes(ext || '')) {
      return <ImageIcon className="w-5 h-5 text-blue-500" />;
    }
    return <FileText className="w-5 h-5 text-gray-500" />;
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* 标题 */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">智能批量导入</h1>
        <p className="mt-2 text-sm text-gray-600">
          拖拽或选择文件，系统将自动识别、分类和归档
        </p>
      </div>

      {/* 拖拽上传区 */}
      <div
        className={`
          border-2 border-dashed rounded-lg p-12 text-center transition-colors
          ${dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-white'}
          ${files.length === 0 ? '' : 'cursor-pointer'}
        `}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <Upload className="w-16 h-16 mx-auto text-gray-400 mb-4" />
        <p className="text-lg font-medium text-gray-700 mb-2">
          拖拽文件到这里，或点击选择
        </p>
        <p className="text-sm text-gray-500 mb-4">
          支持 Word、PDF、图片等格式
        </p>
        <input
          type="file"
          multiple
          accept=".jpg,.jpeg,.png,.pdf,.doc,.docx,.bmp,.tiff,.gif"
          onChange={handleFileSelect}
          className="hidden"
          id="file-upload"
        />
        <label
          htmlFor="file-upload"
          className="inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 cursor-pointer"
        >
          选择文件
        </label>
      </div>

      {/* 文件列表 */}
      {files.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium">待上传文件 ({files.length})</h3>
            <button
              onClick={() => setFiles([])}
              className="text-sm text-red-600 hover:text-red-700"
            >
              清空列表
            </button>
          </div>

          <div className="space-y-2 max-h-96 overflow-y-auto">
            {files.map((file, index) => (
              <div
                key={index}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  {getFileIcon(file.name)}
                  <span className="text-sm font-medium text-gray-900 truncate">
                    {file.name}
                  </span>
                  <span className="text-sm text-gray-500">
                    {formatFileSize(file.size)}
                  </span>
                </div>
                <button
                  onClick={() => removeFile(index)}
                  className="ml-4 text-sm text-red-600 hover:text-red-700"
                >
                  删除
                </button>
              </div>
            ))}
          </div>

          <button
            onClick={handleBatchUpload}
            disabled={uploading}
            className="mt-4 w-full flex items-center justify-center gap-2 px-4 py-3 border border-transparent text-base font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {uploading ? (
              <>
                <Loader className="w-5 h-5 animate-spin" />
                处理中...
              </>
            ) : (
              <>
                <Upload className="w-5 h-5" />
                开始智能导入 ({files.length} 个文件)
              </>
            )}
          </button>
        </div>
      )}

      {/* 实时进度 */}
      {uploading && fileProgress.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="text-lg font-medium mb-4">处理进度</h3>

          <div className="space-y-4">
            {fileProgress.map((fileProg, index) => (
              <div key={index} className="border border-gray-200 rounded-lg p-4">
                {/* 文件名和状态 */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    {fileProg.status === 'waiting' && (
                      <div className="w-5 h-5 rounded-full border-2 border-gray-300" />
                    )}
                    {fileProg.status === 'processing' && (
                      <Loader className="w-5 h-5 text-blue-600 animate-spin" />
                    )}
                    {fileProg.status === 'completed' && (
                      <CheckCircle className="w-5 h-5 text-green-600" />
                    )}
                    {fileProg.status === 'failed' && (
                      <XCircle className="w-5 h-5 text-red-600" />
                    )}
                    <span className="font-medium text-gray-900">{fileProg.filename}</span>
                  </div>
                  <span className={`text-sm px-2 py-1 rounded ${
                    fileProg.status === 'waiting' ? 'bg-gray-100 text-gray-600' :
                    fileProg.status === 'processing' ? 'bg-blue-100 text-blue-700' :
                    fileProg.status === 'completed' ? 'bg-green-100 text-green-700' :
                    'bg-red-100 text-red-700'
                  }`}>
                    {fileProg.status === 'waiting' && '等待中'}
                    {fileProg.status === 'processing' && '处理中'}
                    {fileProg.status === 'completed' && '完成'}
                    {fileProg.status === 'failed' && '失败'}
                  </span>
                </div>

                {/* OCR 进度详情 */}
                {fileProg.status === 'processing' && fileProg.progress && (
                  <div className="mt-3 space-y-3">
                    {/* 当前阶段 */}
                    <div className="bg-blue-50 rounded-lg p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <Loader className="w-4 h-4 text-blue-600 animate-spin" />
                        <span className="text-sm font-medium text-blue-900">
                          {fileProg.progress.message}
                        </span>
                      </div>
                      {fileProg.progress.total_pages > 0 && (
                        <div className="text-xs text-blue-700">
                          进度: {fileProg.progress.current_page} / {fileProg.progress.total_pages} 页
                        </div>
                      )}
                    </div>

                    {/* OCR 识别结果 */}
                    {fileProg.progress.ocr_results && fileProg.progress.ocr_results.length > 0 && (
                      <div className="max-h-64 overflow-y-auto space-y-2">
                        <div className="text-sm font-medium text-blue-900 mb-2">
                          OCR识别结果：
                        </div>
                        {fileProg.progress.ocr_results.map((result) => (
                          <div key={result.page} className="bg-white rounded-lg p-3 border border-blue-200">
                            <div className="flex items-center justify-between mb-2">
                              <span className="font-medium text-sm text-gray-900">
                                第 {result.page} 页
                              </span>
                              <span className={`text-xs px-2 py-1 rounded ${
                                result.status === 'success'
                                  ? 'bg-green-100 text-green-700'
                                  : 'bg-red-100 text-red-700'
                              }`}>
                                {result.status === 'success' ? `✓ ${result.chars} 字符` : '✗ 识别失败'}
                              </span>
                            </div>
                            {result.preview && (
                              <div className="text-xs text-gray-600 font-mono whitespace-pre-wrap break-all">
                                {result.preview}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* 完成结果 */}
                {fileProg.status === 'completed' && fileProg.result && (
                  <div className="mt-2 text-sm text-gray-600">
                    {fileProg.result.message}
                    {fileProg.result.confidence !== undefined && (
                      <span className="ml-2 text-gray-500">
                        (置信度: {(fileProg.result.confidence * 100).toFixed(0)}%)
                      </span>
                    )}
                  </div>
                )}

                {/* 失败信息 */}
                {fileProg.status === 'failed' && fileProg.result?.error && (
                  <div className="mt-2 text-sm text-red-600">
                    {fileProg.result.error}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 处理结果 */}
      {results && (
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h3 className="text-lg font-medium mb-4">处理结果</h3>

          {/* 统计卡片 */}
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="bg-green-50 rounded-lg p-4">
              <div className="flex items-center gap-2 text-green-700 mb-2">
                <CheckCircle className="w-5 h-5" />
                <span className="font-medium">自动归档</span>
              </div>
              <div className="text-2xl font-bold text-green-900">
                {results.auto_archived}
              </div>
            </div>

            <div className="bg-yellow-50 rounded-lg p-4">
              <div className="flex items-center gap-2 text-yellow-700 mb-2">
                <AlertCircle className="w-5 h-5" />
                <span className="font-medium">待审核</span>
              </div>
              <div className="text-2xl font-bold text-yellow-900">
                {results.pending_review}
              </div>
            </div>

            <div className="bg-red-50 rounded-lg p-4">
              <div className="flex items-center gap-2 text-red-700 mb-2">
                <XCircle className="w-5 h-5" />
                <span className="font-medium">失败</span>
              </div>
              <div className="text-2xl font-bold text-red-900">
                {results.failed}
              </div>
            </div>
          </div>

          {/* 详细列表 */}
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {results.items.map((item, index) => (
              <div
                key={index}
                className={`
                  p-3 rounded-lg border
                  ${item.status === 'auto_archived' ? 'bg-green-50 border-green-200' : ''}
                  ${item.status === 'pending_review' ? 'bg-yellow-50 border-yellow-200' : ''}
                  ${item.status === 'failed' ? 'bg-red-50 border-red-200' : ''}
                `}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    {item.status === 'auto_archived' && (
                      <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
                    )}
                    {item.status === 'pending_review' && (
                      <AlertCircle className="w-5 h-5 text-yellow-600 flex-shrink-0" />
                    )}
                    {item.status === 'failed' && (
                      <XCircle className="w-5 h-5 text-red-600 flex-shrink-0" />
                    )}

                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900 truncate">
                        {item.filename}
                      </div>
                      <div className="text-sm text-gray-600">
                        {item.status === 'failed' ? (item.error || item.message) : (item.message || item.error || '')}
                      </div>
                    </div>
                  </div>

                  {item.confidence !== undefined && (
                    <div className="ml-4 text-sm text-gray-500">
                      置信度: {(item.confidence * 100).toFixed(0)}%
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* 操作按钮 */}
          {results.pending_review > 0 && (
            <div className="mt-6 pt-6 border-t border-gray-200">
              <button
                onClick={() => {
                  // 通过全局事件或者父组件传递的方法切换tab
                  // 这里我们先简单reload页面到审核队列
                  window.location.reload();
                }}
                className="w-full px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-yellow-600 hover:bg-yellow-700"
              >
                刷新页面查看审核队列 ({results.pending_review} 项待审核)
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
