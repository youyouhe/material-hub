import { useState } from 'react';
import { X, Download, ExternalLink, RotateCw, Loader2 } from 'lucide-react';
import { getToken } from '../services/auth';
import { rotateFile } from '../services/api-v2';

interface FilePreviewModalProps {
  url: string;
  filename: string;
  mimeType: string | null;
  onClose: () => void;
}

export default function FilePreviewModal({ url, filename, mimeType, onClose }: FilePreviewModalProps) {
  const isImage = mimeType?.startsWith('image/');
  const isPdf = mimeType === 'application/pdf';
  // Append auth token to all file URLs — since C-1 fix, /api/v2/files/* requires auth.
  // Token goes in query param (browser img/iframe/a tags can't set Authorization header).
  const token = getToken();
  const _withAuth = (u: string) => token ? `${u}${u.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}` : u;
  const previewUrl = _withAuth(`${url}${url.includes('?') ? '&' : '?'}preview=true`);

  // 旋转状态：cacheBust 用于旋转成功后强制刷新图片缓存
  const [rotating, setRotating] = useState(false);
  const [cacheBust, setCacheBust] = useState(0);
  const [rotateHint, setRotateHint] = useState('');

  // 从 /api/v2/files/{id} 形式的 URL 中解析文件 ID（解析不到则不能旋转）
  const fileIdMatch = /\/api\/v2\/files\/(\d+)/.exec(url);
  const fileId = fileIdMatch ? Number(fileIdMatch[1]) : null;

  const handleRotate = async () => {
    if (!fileId || rotating) return;
    setRotating(true);
    setRotateHint('');
    try {
      await rotateFile(fileId, 90);
      setCacheBust(Date.now());
      setRotateHint('已顺时针旋转 90° 并保存。如需更新 OCR 结果，请对该文档执行「重新处理」。');
    } catch (e) {
      alert(`旋转失败: ${e instanceof Error ? e.message : e}`);
    } finally {
      setRotating(false);
    }
  };

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
            {isImage && fileId && (
              <button
                onClick={handleRotate}
                disabled={rotating}
                className="p-1.5 text-cp-dim hover:text-cp-text cp-hover rounded disabled:opacity-50"
                title="顺时针旋转 90°（保存到原文件）"
              >
                {rotating ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCw className="w-4 h-4" />}
              </button>
            )}
            <a
              href={_withAuth(url)}
              download={filename}
              className="p-1.5 text-cp-dim hover:text-cp-text cp-hover rounded"
              title="下载"
            >
              <Download className="w-4 h-4" />
            </a>
            <a
              href={_withAuth(url)}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 text-cp-dim hover:text-cp-text cp-hover rounded"
              title="新窗口打开"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
            <button
              onClick={onClose}
              className="p-1.5 text-cp-dim hover:text-cp-text cp-hover rounded"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* 旋转提示 */}
        {rotateHint && (
          <div className="px-4 py-1.5 text-xs text-green-700 bg-green-50 border-b border-green-200 shrink-0">
            {rotateHint}
          </div>
        )}

        {/* Content */}
        <div className="overflow-auto flex-1" style={{ maxHeight: 'calc(90vh - 48px)' }}>
          {isImage && (
            <img
              src={cacheBust ? `${previewUrl}&_r=${cacheBust}` : previewUrl}
              alt={filename}
              className="w-full h-auto"
            />
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
                href={_withAuth(url)}
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
