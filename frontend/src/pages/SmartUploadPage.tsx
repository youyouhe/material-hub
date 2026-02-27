import { useState, useCallback } from 'react';
import { Upload, CheckCircle, AlertCircle, XCircle, FileText, Image as ImageIcon, Loader } from 'lucide-react';
import toast from 'react-hot-toast';
import { smartImportBatch } from '../services/api';

interface UploadResult {
  status: 'auto_archived' | 'pending_review' | 'failed';
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

export default function SmartUploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<BatchResult | null>(null);
  const [dragActive, setDragActive] = useState(false);

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

    try {
      const data: BatchResult = await smartImportBatch(files);
      setResults(data);

      if (data.auto_archived > 0) {
        toast.success(`成功自动归档 ${data.auto_archived} 个文件`);
      }
      if (data.pending_review > 0) {
        toast.info(`${data.pending_review} 个文件需要人工审核`);
      }
      if (data.failed > 0) {
        toast.error(`${data.failed} 个文件处理失败`);
      }

      // 清空文件列表
      setFiles([]);

    } catch (error) {
      console.error('上传错误:', error);
      toast.error('批量上传失败');
    } finally {
      setUploading(false);
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
                        {item.message || item.error || ''}
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
