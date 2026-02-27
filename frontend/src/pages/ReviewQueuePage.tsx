import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Building2, User, Calendar } from 'lucide-react';
import toast from 'react-hot-toast';
import { getPendingReviews, getPendingReviewPreviewUrl, approvePendingReview, rejectPendingReview } from '../services/api';

interface PendingItem {
  id: number;
  filename: string;
  confidence: number;
  status: string;
  created_at: string;
  analysis: {
    material_type: string;
    material_name: string;
    company_info?: {
      name: string;
      legal_person?: string;
      credit_code?: string;
    };
    person_info?: {
      name: string;
      id_number?: string;
    };
    key_dates?: {
      expiry_date?: string;
    };
  };
  entities: {
    company_id?: number;
    company_name?: string;
    company_match_type?: string;
    person_id?: number;
    person_name?: string;
    alternatives?: Array<{
      company_id: number;
      company_name: string;
      similarity: number;
    }>;
    new_company_info?: any;
  };
}

const TYPE_LABELS: Record<string, string> = {
  license: '营业执照',
  qualification: '资质证书',
  iso_cert: 'ISO认证',
  id_card: '身份证',
  education_cert: '学历证书',
  legal_person_cert: '法人证明',
  contract: '合同',
  unknown: '未知类型'
};

export default function ReviewQueuePage() {
  const [items, setItems] = useState<PendingItem[]>([]);
  const [currentItem, setCurrentItem] = useState<PendingItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [corrections, setCorrections] = useState<any>({});

  useEffect(() => {
    loadPendingItems();
  }, []);

  const loadPendingItems = async () => {
    try {
      const data = await getPendingReviews('pending', 50);
      setItems(data.items);
      if (data.items.length > 0) {
        setCurrentItem(data.items[0]);
      }
    } catch (error) {
      console.error('加载失败:', error);
      toast.error('加载待审核列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!currentItem) return;

    try {
      await approvePendingReview(currentItem.id, corrections);
      toast.success('已批准并归档');
      // 移除当前项，显示下一项
      const newItems = items.filter(item => item.id !== currentItem.id);
      setItems(newItems);
      setCurrentItem(newItems.length > 0 ? newItems[0] : null);
      setCorrections({});
    } catch (error) {
      console.error('批准错误:', error);
      toast.error('批准失败');
    }
  };

  const handleReject = async () => {
    if (!currentItem) return;

    const reason = prompt('请输入拒绝原因（可选）:');

    try {
      await rejectPendingReview(currentItem.id, reason || '');
      toast.success('已拒绝');
      const newItems = items.filter(item => item.id !== currentItem.id);
      setItems(newItems);
      setCurrentItem(newItems.length > 0 ? newItems[0] : null);
      setCorrections({});
    } catch (error) {
      console.error('拒绝错误:', error);
      toast.error('拒绝失败');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">加载中...</p>
        </div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="text-center py-12">
        <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-900 mb-2">
          没有待审核项
        </h3>
        <p className="text-gray-600">
          所有材料都已处理完毕
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-12 gap-6 h-[calc(100vh-12rem)]">
      {/* 左侧：队列列表 */}
      <div className="col-span-4 bg-white rounded-lg border border-gray-200 overflow-hidden flex flex-col">
        <div className="p-4 border-b border-gray-200 bg-gray-50">
          <h2 className="text-lg font-semibold text-gray-900">
            待审核队列 ({items.length})
          </h2>
        </div>

        <div className="flex-1 overflow-y-auto">
          {items.map((item) => (
            <div
              key={item.id}
              onClick={() => setCurrentItem(item)}
              className={`
                p-4 border-b border-gray-200 cursor-pointer transition-colors
                ${currentItem?.id === item.id ? 'bg-blue-50 border-l-4 border-l-blue-500' : 'hover:bg-gray-50'}
              `}
            >
              <div className="font-medium text-gray-900 text-sm mb-1 truncate">
                {item.filename}
              </div>

              <div className="flex items-center gap-2 text-xs text-gray-600 mb-2">
                <span className={`
                  px-2 py-0.5 rounded
                  ${item.confidence >= 70 ? 'bg-green-100 text-green-700' :
                    item.confidence >= 50 ? 'bg-yellow-100 text-yellow-700' :
                    'bg-red-100 text-red-700'}
                `}>
                  {item.confidence}%
                </span>
                <span>
                  {TYPE_LABELS[item.analysis?.material_type] || '未知'}
                </span>
              </div>

              {item.entities?.company_name && (
                <div className="flex items-center gap-1 text-xs text-gray-600">
                  <Building2 className="w-3 h-3" />
                  <span className="truncate">{item.entities.company_name}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 右侧：审核详情 */}
      {currentItem && (
        <div className="col-span-8 bg-white rounded-lg border border-gray-200 overflow-hidden flex flex-col">
          <div className="p-4 border-b border-gray-200 bg-gray-50">
            <h2 className="text-lg font-semibold text-gray-900">
              审核详情
            </h2>
          </div>

          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* 文件预览 */}
            <div>
              <h3 className="text-sm font-medium text-gray-700 mb-2">文件预览</h3>
              <div className="bg-gray-100 rounded-lg p-4 h-96 flex items-center justify-center overflow-hidden">
                {currentItem.file_type === 'image' ? (
                  <img
                    src={getPendingReviewPreviewUrl(currentItem.id)}
                    alt="预览"
                    className="max-h-full max-w-full object-contain"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none';
                      e.currentTarget.parentElement!.innerHTML = '<p class="text-gray-500">图片加载失败</p>';
                    }}
                  />
                ) : currentItem.file_type === 'document' ? (
                  <iframe
                    src={getPendingReviewPreviewUrl(currentItem.id)}
                    className="w-full h-full border-0"
                    title="文档预览"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none';
                      e.currentTarget.parentElement!.innerHTML = '<p class="text-gray-500">文档加载失败</p>';
                    }}
                  />
                ) : (
                  <div className="text-center">
                    <p className="text-gray-500 mb-2">无法预览此文件类型</p>
                    <a
                      href={getPendingReviewPreviewUrl(currentItem.id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:text-blue-700 underline"
                    >
                      下载查看
                    </a>
                  </div>
                )}
              </div>
            </div>

            {/* 材料类型 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                材料类型
              </label>
              <select
                value={corrections.material_type || currentItem.analysis.material_type}
                onChange={(e) => setCorrections({ ...corrections, material_type: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {Object.entries(TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>

            {/* 材料名称 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                材料名称
              </label>
              <input
                type="text"
                value={corrections.material_name || currentItem.analysis.material_name || ''}
                onChange={(e) => setCorrections({ ...corrections, material_name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* 公司匹配 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                关联公司
              </label>

              {currentItem.entities.company_match_type === 'exact_name' ||
               currentItem.entities.company_match_type === 'exact_credit_code' ? (
                <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-md">
                  <CheckCircle className="w-5 h-5 text-green-600" />
                  <div>
                    <div className="text-sm font-medium text-green-900">
                      精确匹配
                    </div>
                    <div className="text-sm text-green-700">
                      {currentItem.entities.company_name}
                    </div>
                  </div>
                </div>
              ) : currentItem.entities.company_match_type === 'fuzzy_low' ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                    <AlertTriangle className="w-5 h-5 text-yellow-600" />
                    <div className="text-sm text-yellow-700">
                      可能的匹配，请选择：
                    </div>
                  </div>

                  {currentItem.entities.alternatives?.map((alt) => (
                    <button
                      key={alt.company_id}
                      onClick={() => setCorrections({ ...corrections, company_id: alt.company_id })}
                      className={`
                        w-full p-3 text-left rounded-md border transition-colors
                        ${corrections.company_id === alt.company_id ?
                          'border-blue-500 bg-blue-50' :
                          'border-gray-300 hover:border-gray-400'}
                      `}
                    >
                      <div className="text-sm font-medium text-gray-900">
                        {alt.company_name}
                      </div>
                      <div className="text-xs text-gray-600">
                        相似度: {(alt.similarity * 100).toFixed(0)}%
                      </div>
                    </button>
                  ))}

                  <button
                    onClick={() => setCorrections({ ...corrections, company_id: 'new' })}
                    className={`
                      w-full p-3 text-left rounded-md border transition-colors
                      ${corrections.company_id === 'new' ?
                        'border-blue-500 bg-blue-50' :
                        'border-gray-300 hover:border-gray-400'}
                    `}
                  >
                    <div className="text-sm font-medium text-gray-900">
                      新建公司: {currentItem.entities.company_name}
                    </div>
                  </button>
                </div>
              ) : (
                <div className="p-3 bg-blue-50 border border-blue-200 rounded-md">
                  <div className="text-sm font-medium text-blue-900 mb-1">
                    新公司
                  </div>
                  <div className="text-sm text-blue-700">
                    {currentItem.entities.company_name}
                  </div>
                </div>
              )}
            </div>

            {/* 有效期 */}
            {currentItem.analysis.key_dates?.expiry_date && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  有效期至
                </label>
                <input
                  type="date"
                  value={corrections.expiry_date || currentItem.analysis.key_dates.expiry_date}
                  onChange={(e) => setCorrections({ ...corrections, expiry_date: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}

            {/* 其他信息 */}
            {currentItem.analysis.company_info && (
              <div className="p-4 bg-gray-50 rounded-lg space-y-2">
                <h4 className="text-sm font-medium text-gray-700">识别的公司信息</h4>
                {currentItem.analysis.company_info.legal_person && (
                  <div className="text-sm text-gray-600">
                    法定代表人: {currentItem.analysis.company_info.legal_person}
                  </div>
                )}
                {currentItem.analysis.company_info.credit_code && (
                  <div className="text-sm text-gray-600">
                    信用代码: {currentItem.analysis.company_info.credit_code}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 操作按钮 */}
          <div className="p-4 border-t border-gray-200 bg-gray-50 flex gap-3">
            <button
              onClick={handleApprove}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700"
            >
              <CheckCircle className="w-4 h-4" />
              确认归档
            </button>
            <button
              onClick={handleReject}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
            >
              <XCircle className="w-4 h-4" />
              拒绝
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
