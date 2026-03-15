import { X, Download, ExternalLink } from 'lucide-react';

interface FilePreviewModalProps {
  url: string;
  filename: string;
  mimeType: string | null;
  onClose: () => void;
}

export default function FilePreviewModal({ url, filename, mimeType, onClose }: FilePreviewModalProps) {
  const isImage = mimeType?.startsWith('image/');
  const isPdf = mimeType === 'application/pdf';
  // Add preview=true to avoid Content-Disposition: attachment for inline display
  const previewUrl = `${url}${url.includes('?') ? '&' : '?'}preview=true`;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="relative bg-cp-card rounded-lg overflow-hidden shadow-2xl flex flex-col"
        style={{ maxWidth: isPdf ? '90vw' : '80vw', maxHeight: '90vh', width: isPdf ? '900px' : 'auto' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-cp-border shrink-0">
          <h3 className="text-sm font-medium text-cp-text truncate mr-4">{filename}</h3>
          <div className="flex items-center gap-1 shrink-0">
            <a
              href={url}
              download={filename}
              className="p-1.5 text-cp-dim hover:text-cp-text hover:bg-white/5 rounded"
              title="下载"
            >
              <Download className="w-4 h-4" />
            </a>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 text-cp-dim hover:text-cp-text hover:bg-white/5 rounded"
              title="新窗口打开"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
            <button
              onClick={onClose}
              className="p-1.5 text-cp-dim hover:text-cp-text hover:bg-white/5 rounded"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="overflow-auto flex-1" style={{ maxHeight: 'calc(90vh - 48px)' }}>
          {isImage && (
            <img src={previewUrl} alt={filename} className="w-full h-auto" />
          )}
          {isPdf && (
            <iframe
              src={previewUrl}
              title={filename}
              className="w-full border-0"
              style={{ height: 'calc(90vh - 48px)' }}
            />
          )}
          {!isImage && !isPdf && (
            <div className="flex flex-col items-center justify-center py-16 text-cp-dim">
              <p className="mb-3">此文件类型不支持预览</p>
              <a
                href={url}
                download={filename}
                className="cp-btn-primary px-4 py-2 text-sm rounded-lg inline-flex items-center gap-2"
              >
                <Download className="w-4 h-4" />
                下载文件
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
