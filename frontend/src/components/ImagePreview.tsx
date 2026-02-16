import { X } from 'lucide-react';

interface ImagePreviewProps {
  url: string;
  title: string;
  onClose: () => void;
}

export default function ImagePreview({ url, title, onClose }: ImagePreviewProps) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="relative max-w-4xl max-h-[90vh] bg-white rounded-lg overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200">
          <h3 className="text-sm font-medium text-gray-900 truncate">{title}</h3>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-gray-600 rounded"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="overflow-auto max-h-[calc(90vh-48px)]">
          <img src={url} alt={title} className="w-full h-auto" />
        </div>
      </div>
    </div>
  );
}
