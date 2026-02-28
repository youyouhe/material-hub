import { useState, useEffect } from 'react';
import { X, ChevronDown, FolderOpen, Plus, ChevronsDown, ChevronsUp } from 'lucide-react';
import toast from 'react-hot-toast';
import type { CompanyInfo, MaterialInfo } from '../types';
import {
  getCompanyMaterials,
  unlinkMaterialFromCompany,
  updateMaterial,
  deleteMaterial,
  triggerOCR
} from '../services/api';
import MaterialCard from './MaterialCard';
import MaterialPicker from './MaterialPicker';
import OCRResultViewer from './OCRResultViewer';

interface CompanyDetailModalProps {
  company: CompanyInfo | null;
  onClose: () => void;
  onRefresh: () => void;
}

// 材料类型标签映射
const TYPE_LABELS: Record<string, string> = {
  'license': '营业执照',
  'legal_person_cert': '法定代表人证明',
  'qualification': '资质证书',
  'iso_cert': 'ISO认证',
  'certificate': '证书',
  'other': '其他材料'
};

// 按材料类型或section分组
const groupMaterialsByType = (materials: MaterialInfo[]) => {
  const groups: Record<string, MaterialInfo[]> = {};

  materials.forEach(mat => {
    // 优先使用section分组，其次使用material_type
    let groupKey: string;
    if (mat.section && mat.section.trim() !== '') {
      groupKey = `section:${mat.section}`;  // section分组
    } else {
      groupKey = mat.material_type || 'other';  // 类型分组
    }

    if (!groups[groupKey]) {
      groups[groupKey] = [];
    }
    groups[groupKey].push(mat);
  });

  return groups;
};

// 获取分组的显示名称
const getGroupLabel = (groupKey: string): string => {
  if (groupKey.startsWith('section:')) {
    return groupKey.substring(8);  // 去掉 "section:" 前缀
  }
  return TYPE_LABELS[groupKey] || groupKey;
};

export default function CompanyDetailModal({
  company,
  onClose,
  onRefresh
}: CompanyDetailModalProps) {
  const [materials, setMaterials] = useState<MaterialInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [imageViewerUrl, setImageViewerUrl] = useState<string | null>(null);
  const [imageViewerTitle, setImageViewerTitle] = useState<string>('');
  const [showPicker, setShowPicker] = useState(false);
  const [ocrViewerMaterial, setOcrViewerMaterial] = useState<MaterialInfo | null>(null);

  useEffect(() => {
    if (company) {
      loadMaterials();
    }
  }, [company]);

  // ESC键关闭
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (imageViewerUrl) {
          setImageViewerUrl(null);
        } else {
          onClose();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose, imageViewerUrl]);

  const loadMaterials = async () => {
    if (!company) return;

    setLoading(true);
    try {
      const data = await getCompanyMaterials(company.id);
      setMaterials(data.materials || []);
    } catch (error) {
      console.error('Failed to load materials:', error);
      toast.error('加载材料失败');
    } finally {
      setLoading(false);
    }
  };

  const toggleCollapse = (type: string) => {
    const newCollapsed = new Set(collapsed);
    if (newCollapsed.has(type)) {
      newCollapsed.delete(type);
    } else {
      newCollapsed.add(type);
    }
    setCollapsed(newCollapsed);
  };

  const expandAll = () => {
    setCollapsed(new Set());
  };

  const collapseAll = () => {
    const groupedMaterials = groupMaterialsByType(materials);
    const allGroups = Object.keys(groupedMaterials);
    setCollapsed(new Set(allGroups));
  };

  const handleUpdateExpiry = async (id: number, date: string) => {
    try {
      await updateMaterial(id, { expiry_date: date });
      toast.success('有效期已更新');
      loadMaterials();
    } catch (error) {
      console.error('Failed to update expiry:', error);
      toast.error('更新失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteMaterial(id);
      toast.success('材料已删除');
      loadMaterials();
    } catch (error) {
      console.error('Failed to delete material:', error);
      toast.error('删除失败');
    }
  };

  const handleImageClick = (url: string, title: string) => {
    setImageViewerUrl(url);
    setImageViewerTitle(title);
  };

  const handleTriggerOCR = async (id: number) => {
    try {
      await triggerOCR(id);
      toast.success('OCR识别已启动');
      setTimeout(() => loadMaterials(), 1000);
    } catch (error) {
      console.error('Failed to trigger OCR:', error);
      toast.error('OCR启动失败');
    }
  };

  const handleViewOCR = (material: MaterialInfo) => {
    setOcrViewerMaterial(material);
  };

  const handleLinkMaterials = async (materialIds: number[], section?: string) => {
    if (!company) return;

    try {
      await Promise.all(
        materialIds.map(id => {
          const updates: any = { company_id: company.id };
          if (section) {
            updates.section = section;
          }
          return updateMaterial(id, updates);
        })
      );
      toast.success(`已关联 ${materialIds.length} 个材料${section ? ` 到 "${section}"` : ''}`);
      loadMaterials();
      setShowPicker(false);
      onRefresh();
    } catch (error) {
      console.error('Failed to link materials:', error);
      toast.error('关联失败');
    }
  };

  const handleUnlink = async (materialId: number) => {
    if (!confirm('确定取消关联此材料吗？')) return;

    try {
      await unlinkMaterialFromCompany(materialId);
      toast.success('已取消关联');
      loadMaterials();
      onRefresh();
    } catch (error) {
      console.error('Failed to unlink material:', error);
      toast.error('操作失败');
    }
  };

  if (!company) return null;

  const groupedMaterials = groupMaterialsByType(materials);
  const groupKeys = Object.keys(groupedMaterials).sort();

  return (
    <>
      {/* Modal backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
        onClick={onClose}
      >
        {/* Modal content */}
        <div
          className="bg-white rounded-lg max-w-7xl w-full max-h-[90vh] overflow-hidden flex flex-col"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="p-6 border-b">
            <div className="flex items-start justify-between mb-4">
              <div className="flex-1">
                <h2 className="text-2xl font-bold text-gray-900">{company.name}</h2>
                <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                  {company.legal_person && (
                    <div className="flex items-center gap-2">
                      <span className="text-gray-500">法定代表人:</span>
                      <span className="text-gray-900">{company.legal_person}</span>
                    </div>
                  )}
                  {company.credit_code && (
                    <div className="flex items-center gap-2">
                      <span className="text-gray-500">统一社会信用代码:</span>
                      <span className="text-gray-900 font-mono">{company.credit_code}</span>
                    </div>
                  )}
                </div>
                {company.address && (
                  <div className="mt-2 flex items-start gap-2 text-sm">
                    <span className="text-gray-500">地址:</span>
                    <span className="text-gray-900">{company.address}</span>
                  </div>
                )}
              </div>
              <button
                onClick={onClose}
                className="ml-4 p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                title="关闭 (ESC)"
              >
                <X className="w-6 h-6" />
              </button>
            </div>
            {/* Actions */}
            <div className="flex items-center justify-end gap-2">
              {materials.length > 0 && (
                <>
                  <button
                    onClick={expandAll}
                    className="inline-flex items-center gap-2 px-3 py-2 text-sm border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
                    title="展开所有分组"
                  >
                    <ChevronsDown className="w-4 h-4" />
                    全部展开
                  </button>
                  <button
                    onClick={collapseAll}
                    className="inline-flex items-center gap-2 px-3 py-2 text-sm border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
                    title="折叠所有分组"
                  >
                    <ChevronsUp className="w-4 h-4" />
                    全部折叠
                  </button>
                </>
              )}
              <button
                onClick={() => setShowPicker(true)}
                className="inline-flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
              >
                <Plus className="w-4 h-4" />
                关联材料
              </button>
            </div>
          </div>

          {/* Materials content */}
          <div className="flex-1 overflow-y-auto p-6">
            {loading ? (
              <div className="text-center py-12 text-gray-400">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
                <p className="mt-4 text-sm">加载中...</p>
              </div>
            ) : materials.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <FolderOpen className="w-12 h-12 mx-auto mb-2" />
                <p className="text-sm">暂无关联材料</p>
                <button
                  onClick={() => setShowPicker(true)}
                  className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                >
                  <Plus className="w-4 h-4" />
                  关联材料
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {groupKeys.map(type => {
                  const groupMaterials = groupedMaterials[type];
                  const isCollapsed = collapsed.has(type);

                  return (
                    <div key={type} className="border rounded-lg overflow-hidden">
                      {/* Group header */}
                      <div
                        className="flex items-center justify-between p-4 bg-gray-50 cursor-pointer hover:bg-gray-100 transition-colors"
                        onClick={() => toggleCollapse(type)}
                      >
                        <h4 className="font-semibold text-gray-900">
                          {getGroupLabel(type)} ({groupMaterials.length})
                        </h4>
                        <ChevronDown
                          className={`w-5 h-5 text-gray-500 transition-transform ${
                            isCollapsed ? '-rotate-180' : ''
                          }`}
                        />
                      </div>

                      {/* Group materials */}
                      {!isCollapsed && (
                        <div className="p-4 bg-white">
                          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                            {groupMaterials.map(mat => (
                              <MaterialCard
                                key={mat.id}
                                material={mat}
                                onUpdateExpiry={handleUpdateExpiry}
                                onDelete={handleDelete}
                                onImageClick={handleImageClick}
                                onTriggerOCR={handleTriggerOCR}
                                onViewOCR={handleViewOCR}
                                onUnlink={() => handleUnlink(mat.id)}
                              />
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Material Picker */}
      {showPicker && (
        <MaterialPicker
          onSelect={handleLinkMaterials}
          onClose={() => setShowPicker(false)}
          excludeIds={materials.map(m => m.id)}
        />
      )}

      {/* Image viewer */}
      {imageViewerUrl && (
        <div
          className="fixed inset-0 z-[60] bg-black/90 flex items-center justify-center p-4"
          onClick={() => setImageViewerUrl(null)}
        >
          <div className="relative max-w-7xl max-h-full">
            <button
              onClick={() => setImageViewerUrl(null)}
              className="absolute top-4 right-4 p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-colors"
              title="关闭 (ESC)"
            >
              <X className="w-6 h-6" />
            </button>
            <img
              src={imageViewerUrl}
              alt={imageViewerTitle}
              className="max-w-full max-h-[90vh] object-contain"
              onClick={(e) => e.stopPropagation()}
            />
            <p className="text-white text-center mt-4">{imageViewerTitle}</p>
          </div>
        </div>
      )}

      {/* OCR Result Viewer */}
      {ocrViewerMaterial && (
        <OCRResultViewer
          material={ocrViewerMaterial}
          onClose={() => setOcrViewerMaterial(null)}
        />
      )}
    </>
  );
}
