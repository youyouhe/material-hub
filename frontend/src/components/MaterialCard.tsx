import { useState } from 'react';
import { Calendar, Trash2, Edit3, Check, X } from 'lucide-react';
import clsx from 'clsx';
import type { MaterialInfo } from '../types';

interface MaterialCardProps {
  material: MaterialInfo;
  onUpdateExpiry: (id: number, date: string) => Promise<unknown>;
  onDelete: (id: number) => void;
  onImageClick: (url: string, title: string) => void;
}

export default function MaterialCard({
  material,
  onUpdateExpiry,
  onDelete,
  onImageClick,
}: MaterialCardProps) {
  const [editingExpiry, setEditingExpiry] = useState(false);
  const [expiryValue, setExpiryValue] = useState(material.expiry_date || '');

  const handleSaveExpiry = async () => {
    if (expiryValue) {
      await onUpdateExpiry(material.id, expiryValue);
    }
    setEditingExpiry(false);
  };

  const label =
    material.section && material.section !== material.title
      ? `${material.section} ${material.title}`
      : material.title;

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden hover:shadow-md transition-shadow">
      {/* Image thumbnail */}
      <div
        className="aspect-[4/3] bg-gray-50 cursor-pointer overflow-hidden"
        onClick={() => onImageClick(material.image_url, label)}
      >
        <img
          src={material.image_url}
          alt={label}
          className="w-full h-full object-contain"
          loading="lazy"
        />
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
                material.is_expired === true &&
                  'bg-red-50 text-red-700 border border-red-200',
                material.is_expired === false &&
                  'bg-green-50 text-green-700 border border-green-200',
                material.is_expired === null &&
                  'bg-gray-50 text-gray-500 border border-gray-200'
              )}
            >
              <Calendar className="w-3 h-3" />
              {material.expiry_date
                ? material.is_expired
                  ? `已过期 ${material.expiry_date}`
                  : `有效至 ${material.expiry_date}`
                : '未设置有效期'}
              <Edit3 className="w-3 h-3 ml-0.5 opacity-50" />
            </button>
          )}
        </div>

        {/* Actions */}
        <div className="mt-2 flex justify-end">
          <button
            onClick={() => onDelete(material.id)}
            className="p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded"
            title="Delete"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
