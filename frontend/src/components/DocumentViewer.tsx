import { useRef, useEffect, useState } from 'react';
import { Calendar, Edit3, Check, X, Trash2, ChevronLeft, ChevronRight } from 'lucide-react';
import clsx from 'clsx';
import type { MaterialInfo } from '../types';

interface DocumentViewerProps {
  materials: MaterialInfo[];
  documentId: number;
  onUpdateExpiry: (id: number, date: string) => Promise<unknown>;
  onDelete: (id: number) => void;
}

export default function DocumentViewer({
  materials,
  documentId,
  onUpdateExpiry,
  onDelete,
}: DocumentViewerProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [selectedMaterialId, setSelectedMaterialId] = useState<number | null>(null);
  const [editingExpiry, setEditingExpiry] = useState<number | null>(null);
  const [expiryValue, setExpiryValue] = useState('');
  const [isLeftPanelCollapsed, setIsLeftPanelCollapsed] = useState(false);

  // Load the document preview in iframe
  useEffect(() => {
    if (iframeRef.current && documentId) {
      iframeRef.current.src = `/api/documents/${documentId}/preview`;
    }
  }, [documentId]);

  const handleImageClick = (material: MaterialInfo) => {
    setSelectedMaterialId(material.id);

    // Scroll to the section in the iframe
    if (iframeRef.current?.contentWindow) {
      const sectionId = `section-${material.id}`;
      iframeRef.current.contentWindow.postMessage(
        { type: 'scrollToSection', sectionId },
        '*'
      );

      // Fallback: try to scroll using iframe's contentDocument
      setTimeout(() => {
        try {
          const iframeDoc = iframeRef.current?.contentDocument;
          if (iframeDoc) {
            const element = iframeDoc.getElementById(sectionId);
            if (element) {
              element.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
          }
        } catch (e) {
          console.error('Failed to scroll to section:', e);
        }
      }, 100);
    }
  };

  const handleSaveExpiry = async (materialId: number) => {
    if (expiryValue) {
      await onUpdateExpiry(materialId, expiryValue);
    }
    setEditingExpiry(null);
  };

  const startEditExpiry = (material: MaterialInfo) => {
    setEditingExpiry(material.id);
    setExpiryValue(material.expiry_date || '');
  };

  return (
    <div className="flex h-[calc(100vh-12rem)] gap-4">
      {/* Left panel - Image thumbnails */}
      <div
        className={clsx(
          'flex flex-col bg-white border border-gray-200 rounded-lg overflow-hidden transition-all duration-300',
          isLeftPanelCollapsed ? 'w-12' : 'w-80'
        )}
      >
        {/* Collapse toggle button */}
        <button
          onClick={() => setIsLeftPanelCollapsed(!isLeftPanelCollapsed)}
          className="flex items-center justify-center p-2 bg-gray-50 hover:bg-gray-100 border-b border-gray-200"
          title={isLeftPanelCollapsed ? 'Expand' : 'Collapse'}
        >
          {isLeftPanelCollapsed ? (
            <ChevronRight className="w-5 h-5 text-gray-600" />
          ) : (
            <ChevronLeft className="w-5 h-5 text-gray-600" />
          )}
        </button>

        {!isLeftPanelCollapsed && (
          <>
            <div className="p-3 border-b border-gray-200 bg-gray-50">
              <h3 className="text-sm font-semibold text-gray-900">
                Images ({materials.length})
              </h3>
            </div>

            <div className="flex-1 overflow-y-auto">
              {materials.map((material) => {
                const label =
                  material.section && material.section !== material.title
                    ? `${material.section} ${material.title}`
                    : material.title;

                return (
                  <div
                    key={material.id}
                    className={clsx(
                      'border-b border-gray-200 cursor-pointer transition-colors hover:bg-gray-50',
                      selectedMaterialId === material.id && 'bg-blue-50 border-l-4 border-l-blue-500'
                    )}
                    onClick={() => handleImageClick(material)}
                  >
                    {/* Thumbnail */}
                    <div className="p-2">
                      <div className="aspect-[4/3] bg-gray-100 rounded overflow-hidden">
                        <img
                          src={material.image_url}
                          alt={label}
                          className="w-full h-full object-contain"
                          loading="lazy"
                        />
                      </div>
                    </div>

                    {/* Info */}
                    <div className="px-2 pb-2">
                      <h4 className="text-xs font-medium text-gray-900 truncate" title={label}>
                        {label}
                      </h4>

                      {/* Expiry date */}
                      <div className="mt-1">
                        {editingExpiry === material.id ? (
                          <div className="flex items-center gap-1">
                            <input
                              type="date"
                              value={expiryValue}
                              onChange={(e) => setExpiryValue(e.target.value)}
                              onClick={(e) => e.stopPropagation()}
                              className="text-xs border border-gray-300 rounded px-1 py-0.5 w-full"
                            />
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleSaveExpiry(material.id);
                              }}
                              className="p-0.5 text-green-600 hover:bg-green-50 rounded"
                            >
                              <Check className="w-3 h-3" />
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setEditingExpiry(null);
                              }}
                              className="p-0.5 text-gray-400 hover:bg-gray-50 rounded"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center justify-between">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                startEditExpiry(material);
                              }}
                              className={clsx(
                                'inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full',
                                material.is_expired === true &&
                                  'bg-red-50 text-red-700 border border-red-200',
                                material.is_expired === false &&
                                  'bg-green-50 text-green-700 border border-green-200',
                                material.is_expired === null &&
                                  'bg-gray-50 text-gray-500 border border-gray-200'
                              )}
                            >
                              <Calendar className="w-2.5 h-2.5" />
                              <span className="text-[10px]">
                                {material.expiry_date
                                  ? material.is_expired
                                    ? `已过期`
                                    : `有效期`
                                  : '未设置'}
                              </span>
                              <Edit3 className="w-2.5 h-2.5 opacity-50" />
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                if (confirm('确定要删除这个素材吗？')) {
                                  onDelete(material.id);
                                }
                              }}
                              className="p-0.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded"
                              title="Delete"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>

      {/* Right panel - Document preview */}
      <div className="flex-1 bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="h-full">
          <iframe
            ref={iframeRef}
            className="w-full h-full border-0"
            title="Document Preview"
            sandbox="allow-same-origin allow-scripts"
          />
        </div>
      </div>
    </div>
  );
}
