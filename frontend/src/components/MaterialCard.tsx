import { useState } from 'react';
import { Calendar, Trash2, Edit3, Check, X, Scan, Eye, Loader2, RotateCcw, Unlink, Building2, Users } from 'lucide-react';
import clsx from 'clsx';
import type { MaterialInfo } from '../types';

interface MaterialCardProps {
  material: MaterialInfo;
  onUpdateExpiry: (id: number, date: string) => Promise<unknown>;
  onDelete: (id: number) => void;
  onImageClick: (url: string, title: string) => void;
  onTriggerOCR?: (id: number) => void;
  onViewOCR?: (material: MaterialInfo) => void;
  onUnlink?: () => void;
}

export default function MaterialCard({
  material,
  onUpdateExpiry,
  onDelete,
  onImageClick,
  onTriggerOCR,
  onViewOCR,
  onUnlink,
}: MaterialCardProps) {
  const [editingExpiry, setEditingExpiry] = useState(false);
  const [expiryValue, setExpiryValue] = useState(material.expiry_date || '');

  const hasOCR = material.ocr_status === 'completed' && material.ocr_text;
  const isProcessing = material.ocr_status === 'processing';
  const hasFailed = material.ocr_status === 'failed';

  const handleSaveExpiry = async () => {
    if (expiryValue) {
      await onUpdateExpiry(material.id, expiryValue);
    }
    setEditingExpiry(false);
  };

  const handleDelete = () => {
    if (confirm(`确定要删除这张图片吗？\n\n${label}\n\n此操作不可恢复。`)) {
      onDelete(material.id);
    }
  };

  const label =
    material.section && material.section !== material.title
      ? `${material.section} ${material.title}`
      : material.title;

  // 检查是否已关联
  const isLinked = material.company_id !== null || material.person_id !== null;
  const linkType = material.company_id ? 'company' : material.person_id ? 'person' : null;

  // 计算过期状态
  const getExpiryStatus = () => {
    if (!material.expiry_date) return null;

    const today = new Date();
    const expiryDate = new Date(material.expiry_date);
    const diffTime = expiryDate.getTime() - today.getTime();
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays < 0) {
      return 'expired'; // 已过期
    } else if (diffDays <= 30) {
      return 'expiring-soon'; // 30天内过期
    }
    return 'valid'; // 有效
  };

  const expiryStatus = getExpiryStatus();

  return (
    <div className={clsx(
      "bg-white rounded-lg border-2 shadow-sm overflow-hidden hover:shadow-md transition-shadow",
      expiryStatus === 'expired' && "border-red-400 ring-2 ring-red-300",
      expiryStatus === 'expiring-soon' && "border-yellow-400 animate-pulse",
      expiryStatus === 'valid' && "border-green-400",
      !expiryStatus && "border-gray-200"
    )}>
      {/* Image thumbnail */}
      <div
        className="aspect-[4/3] bg-gray-50 cursor-pointer overflow-hidden relative"
        onClick={() => onImageClick(material.image_url, label)}
      >
        <img
          src={material.image_url}
          alt={label}
          className="w-full h-full object-contain"
          loading="lazy"
        />

        {/* 已过期红色遮罩 */}
        {expiryStatus === 'expired' && (
          <div className="absolute inset-0 bg-red-600 bg-opacity-25 flex items-center justify-center">
            <div className="bg-red-600 text-white px-3 py-1 rounded-full text-xs font-bold shadow-lg">
              已过期
            </div>
          </div>
        )}

        {/* 即将过期警告角标 */}
        {expiryStatus === 'expiring-soon' && (
          <div className="absolute top-2 right-2">
            <div className="bg-yellow-500 text-white px-2 py-0.5 rounded text-xs font-bold shadow-lg animate-bounce">
              即将过期
            </div>
          </div>
        )}

        {/* 已关联标识 */}
        {isLinked && (
          <div className="absolute top-2 left-2">
            <div className={clsx(
              "px-2 py-0.5 rounded text-xs font-bold shadow-lg flex items-center gap-1",
              linkType === 'company' ? "bg-blue-500 text-white" : "bg-green-500 text-white"
            )}>
              {linkType === 'company' ? (
                <>
                  <Building2 className="w-3 h-3" />
                  已关联公司
                </>
              ) : (
                <>
                  <Users className="w-3 h-3" />
                  已关联人员
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="p-3">
        <h3 className="text-sm font-medium text-gray-900 truncate" title={label}>
          {label}
        </h3>

        <p className="text-xs text-gray-500 mt-1 truncate">
          {material.source_filename}
        </p>

        {/* Expiry date */}
        <div className="mt-2 flex items-center gap-1">
          {editingExpiry ? (
            <div className="flex items-center gap-1">
              <input
                type="date"
                value={expiryValue}
                onChange={(e) => setExpiryValue(e.target.value)}
                className="text-xs border border-gray-300 rounded px-1 py-0.5"
              />
              <button
                onClick={handleSaveExpiry}
                className="p-0.5 text-green-600 hover:bg-green-50 rounded"
              >
                <Check className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setEditingExpiry(false)}
                className="p-0.5 text-gray-400 hover:bg-gray-50 rounded"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <button
              onClick={() => setEditingExpiry(true)}
              className={clsx(
                'inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full',
                expiryStatus === 'expired' &&
                  'bg-red-50 text-red-700 border border-red-200 font-semibold',
                expiryStatus === 'expiring-soon' &&
                  'bg-yellow-50 text-yellow-700 border border-yellow-300 font-semibold',
                expiryStatus === 'valid' &&
                  'bg-green-50 text-green-700 border border-green-200',
                !expiryStatus &&
                  'bg-gray-50 text-gray-500 border border-gray-200'
              )}
            >
              <Calendar className="w-3 h-3" />
              {material.expiry_date
                ? expiryStatus === 'expired'
                  ? `已过期 ${material.expiry_date}`
                  : expiryStatus === 'expiring-soon'
                  ? `即将过期 ${material.expiry_date}`
                  : `有效至 ${material.expiry_date}`
                : '未设置有效期'}
              <Edit3 className="w-3 h-3 ml-0.5 opacity-50" />
            </button>
          )}
        </div>

        {/* OCR Status & Actions */}
        <div className="mt-2 flex items-center justify-between gap-2">
          {/* OCR Actions */}
          <div className="flex items-center gap-1">
            {!hasOCR && !isProcessing && !hasFailed && onTriggerOCR && (
              <button
                onClick={() => onTriggerOCR(material.id)}
                className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-blue-50 text-blue-600 hover:bg-blue-100 rounded border border-blue-200 transition-colors"
                title="OCR识别"
              >
                <Scan className="w-3 h-3" />
                识别
              </button>
            )}

            {isProcessing && (
              <div className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-yellow-50 text-yellow-600 rounded border border-yellow-200">
                <Loader2 className="w-3 h-3 animate-spin" />
                识别中...
              </div>
            )}

            {hasFailed && onTriggerOCR && (
              <button
                onClick={() => onTriggerOCR(material.id)}
                className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-red-50 text-red-600 hover:bg-red-100 rounded border border-red-200 transition-colors"
                title={material.ocr_error || '识别失败，点击重试'}
              >
                <RotateCcw className="w-3 h-3" />
                重试
              </button>
            )}

            {hasOCR && onViewOCR && (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => onViewOCR(material)}
                  className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-green-50 text-green-600 hover:bg-green-100 rounded border border-green-200 transition-colors"
                  title="查看识别结果"
                >
                  <Eye className="w-3 h-3" />
                  查看结果
                </button>
                {onTriggerOCR && (
                  <button
                    onClick={() => onTriggerOCR(material.id)}
                    className="p-1 text-green-600 hover:bg-green-100 rounded border border-green-200 transition-colors"
                    title="重新识别"
                  >
                    <RotateCcw className="w-3 h-3" />
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1">
            {onUnlink && (
              <button
                onClick={onUnlink}
                className="p-1.5 text-gray-400 hover:text-orange-600 hover:bg-orange-50 rounded transition-colors border border-transparent hover:border-orange-200"
                title="取消关联"
              >
                <Unlink className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={handleDelete}
              className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors border border-transparent hover:border-red-200"
              title="删除此图片"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
