import { useState, useEffect } from 'react';
import { X, Search, CheckSquare } from 'lucide-react';
import type { MaterialInfo } from '../types';
import { searchMaterials } from '../services/api';

interface MaterialPickerProps {
  onSelect: (materialIds: number[], section?: string) => void;
  onClose: () => void;
  excludeIds?: number[];
  filterByType?: string[];
}

export default function MaterialPicker({
  onSelect,
  onClose,
  excludeIds = [],
  filterByType
}: MaterialPickerProps) {
  const [materials, setMaterials] = useState<MaterialInfo[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [section, setSection] = useState('');

  useEffect(() => {
    loadMaterials();
  }, [query]);

  const loadMaterials = async () => {
    setLoading(true);
    try {
      // 只获取未关联的材料（company_id 和 person_id 都为 null）
      const data = await searchMaterials({
        q: query,
        status: 'all',
        linked_status: 'unlinked'
      });

      // Filter out already linked materials (additional safety check)
      let filtered = data.filter(m => !excludeIds.includes(m.id));

      // Optional: filter by type
      if (filterByType && filterByType.length > 0) {
        filtered = filtered.filter(m =>
          filterByType.includes(m.material_type || 'other')
        );
      }

      setMaterials(filtered);
    } catch (error) {
      console.error('Failed to load materials:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (id: number) => {
    const newSelected = new Set(selected);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelected(newSelected);
  };

  const selectGroup = (groupMaterials: MaterialInfo[]) => {
    const newSelected = new Set(selected);
    groupMaterials.forEach(m => newSelected.add(m.id));
    setSelected(newSelected);
  };

  // 按标题分组材料
  const groupedMaterials = materials.reduce((acc, m) => {
    const key = m.title;
    if (!acc[key]) {
      acc[key] = [];
    }
    acc[key].push(m);
    return acc;
  }, {} as Record<string, MaterialInfo[]>);

  const handleConfirm = () => {
    onSelect(Array.from(selected), section || undefined);
  };

  // ESC to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[55] bg-black/50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg max-w-6xl w-full max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-4 border-b">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-semibold text-gray-900">选择要关联的材料</h3>
            <button
              onClick={onClose}
              className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              title="关闭 (ESC)"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Search input */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索材料标题或内容..."
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              autoFocus
            />
          </div>

          {/* Section input */}
          <div className="mt-3">
            <label className="block text-xs font-medium text-gray-700 mb-1">
              分类/Section（可选，为选中的材料统一设置）
            </label>
            <input
              type="text"
              value={section}
              onChange={(e) => setSection(e.target.value)}
              placeholder="例如：技术服务合同、资质材料等"
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        </div>

        {/* Material Grid */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="text-center py-12 text-gray-400">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto"></div>
              <p className="mt-3 text-sm">加载中...</p>
            </div>
          ) : materials.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <p className="text-sm">未找到可关联的材料</p>
              {query && <p className="text-xs mt-1">尝试修改搜索条件</p>}
            </div>
          ) : (
            <div className="space-y-6">
              {Object.entries(groupedMaterials).map(([title, groupMaterials]) => {
                const allSelected = groupMaterials.every(m => selected.has(m.id));
                const someSelected = groupMaterials.some(m => selected.has(m.id));

                return (
                  <div key={title} className="space-y-2">
                    {/* Group Header */}
                    <div className="flex items-center justify-between px-2 py-1 bg-gray-100 rounded">
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-medium text-gray-700 truncate" title={title}>
                          {title}
                        </h4>
                        <span className="text-xs px-2 py-0.5 bg-gray-200 text-gray-600 rounded-full">
                          {groupMaterials.length} 页
                        </span>
                      </div>
                      <button
                        onClick={() => selectGroup(groupMaterials)}
                        className={`flex items-center gap-1 text-xs px-2 py-1 rounded transition-colors ${
                          allSelected
                            ? 'bg-blue-500 text-white'
                            : someSelected
                            ? 'bg-blue-100 text-blue-700 hover:bg-blue-200'
                            : 'bg-white text-gray-600 hover:bg-gray-50 border border-gray-300'
                        }`}
                      >
                        <CheckSquare className="w-3 h-3" />
                        {allSelected ? '已全选' : '全选'}
                      </button>
                    </div>

                    {/* Group Materials */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                      {groupMaterials.map(m => {
                        const isSelected = selected.has(m.id);
                        const label =
                          m.section && m.section !== m.title
                            ? `${m.section} ${m.title}`
                            : m.title;

                        return (
                          <div
                            key={m.id}
                            onClick={() => toggleSelect(m.id)}
                            className={`cursor-pointer border-2 rounded-lg overflow-hidden transition-all hover:shadow-md relative ${
                              isSelected
                                ? 'border-blue-500 ring-2 ring-blue-200 bg-blue-50'
                                : 'border-gray-200 hover:border-blue-300'
                            }`}
                          >
                            {/* Checkbox indicator */}
                            {isSelected && (
                              <div className="absolute top-2 right-2 bg-blue-500 text-white rounded-full p-0.5 z-10">
                                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                  <path
                                    fillRule="evenodd"
                                    d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                                    clipRule="evenodd"
                                  />
                                </svg>
                              </div>
                            )}

                            {/* Page number badge */}
                            {groupMaterials.length > 1 && (
                              <div className="absolute top-2 left-2 bg-gray-800/70 text-white text-xs px-1.5 py-0.5 rounded z-10">
                                {groupMaterials.indexOf(m) + 1}/{groupMaterials.length}
                              </div>
                            )}

                            {/* Image */}
                            <div className="relative aspect-[4/3] bg-gray-100">
                              <img
                                src={m.image_url}
                                alt={label}
                                className="w-full h-full object-contain"
                                loading="lazy"
                              />
                            </div>

                            {/* Info */}
                            <div className={`p-2 ${isSelected ? 'bg-blue-50' : 'bg-white'}`}>
                              <p className="text-xs text-gray-900 truncate font-medium" title={label}>
                                {m.image_filename}
                              </p>
                              {m.material_type && (
                                <p className="text-xs text-gray-500 mt-0.5">
                                  {m.material_type}
                                </p>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t bg-gray-50 flex items-center justify-between">
          <p className="text-sm text-gray-600">
            已选择 <span className="font-semibold text-blue-600">{selected.size}</span> 个材料
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleConfirm}
              disabled={selected.size === 0}
              className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              确认关联 ({selected.size})
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
