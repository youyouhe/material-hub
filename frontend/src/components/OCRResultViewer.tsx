import { useState } from 'react';
import { X, FileText, Database } from 'lucide-react';
import clsx from 'clsx';
import type { MaterialInfo } from '../types';

interface OCRResultViewerProps {
  material: MaterialInfo;
  onClose: () => void;
}

type TabType = 'text' | 'data';

export default function OCRResultViewer({ material, onClose }: OCRResultViewerProps) {
  const [activeTab, setActiveTab] = useState<TabType>('text');

  const label =
    material.section && material.section !== material.title
      ? `${material.section} ${material.title}`
      : material.title;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-7xl h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">OCR识别结果</h2>
            <p className="text-sm text-gray-500 mt-0.5">{label}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden flex">
          {/* Left: Image */}
          <div className="w-1/2 border-r border-gray-200 bg-gray-50 p-6 overflow-auto">
            <div className="flex items-center justify-center h-full">
              <img
                src={material.image_url}
                alt={label}
                className="max-w-full max-h-full object-contain rounded-lg shadow-lg"
              />
            </div>
          </div>

          {/* Right: OCR Text & Data */}
          <div className="w-1/2 flex flex-col">
            {/* Tabs */}
            <div className="flex border-b border-gray-200 px-6">
              <button
                onClick={() => setActiveTab('text')}
                className={clsx(
                  'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
                  activeTab === 'text'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-600 hover:text-gray-900'
                )}
              >
                <FileText className="w-4 h-4" />
                OCR文本
              </button>
              <button
                onClick={() => setActiveTab('data')}
                className={clsx(
                  'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
                  activeTab === 'data'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-600 hover:text-gray-900'
                )}
              >
                <Database className="w-4 h-4" />
                提取数据
              </button>
            </div>

            {/* Tab Content */}
            <div className="flex-1 overflow-auto p-6">
              {activeTab === 'text' && (
                <div>
                  {material.ocr_text ? (
                    <pre className="text-sm text-gray-700 whitespace-pre-wrap font-mono bg-gray-50 p-4 rounded-lg border border-gray-200">
                      {material.ocr_text}
                    </pre>
                  ) : (
                    <div className="text-center py-12 text-gray-400">
                      <FileText className="w-12 h-12 mx-auto mb-2 opacity-50" />
                      <p className="text-sm">暂无OCR文本</p>
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'data' && (
                <div>
                  {material.extracted_data ? (
                    <div className="space-y-4">
                      {/* Material Type */}
                      {material.material_type && (
                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                          <div className="text-xs font-medium text-blue-600 mb-1">材料类型</div>
                          <div className="text-sm text-blue-900">{getMaterialTypeName(material.material_type)}</div>
                        </div>
                      )}

                      {/* Confidence */}
                      {material.extracted_data.confidence !== undefined && (
                        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                          <div className="text-xs font-medium text-gray-600 mb-1">识别置信度</div>
                          <div className="text-sm text-gray-900">
                            {(material.extracted_data.confidence * 100).toFixed(1)}%
                          </div>
                        </div>
                      )}

                      {/* Summary */}
                      {material.extracted_data.summary && (
                        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                          <div className="text-xs font-medium text-amber-600 mb-1">摘要</div>
                          <div className="text-sm text-amber-900">{material.extracted_data.summary}</div>
                        </div>
                      )}

                      {/* Extracted Data */}
                      {material.extracted_data.extracted_data && (
                        <div className="bg-white border border-gray-200 rounded-lg p-4">
                          <div className="text-xs font-medium text-gray-600 mb-3">提取的结构化数据</div>
                          <div className="space-y-2">
                            {Object.entries(material.extracted_data.extracted_data).map(([key, value]) => (
                              <div key={key} className="flex">
                                <div className="w-32 text-xs text-gray-500 flex-shrink-0">{getFieldName(key)}:</div>
                                <div className="text-sm text-gray-900 flex-1">{String(value)}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Raw JSON */}
                      <details className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                        <summary className="text-xs font-medium text-gray-600 cursor-pointer">原始JSON数据</summary>
                        <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono mt-3 overflow-auto">
                          {JSON.stringify(material.extracted_data, null, 2)}
                        </pre>
                      </details>
                    </div>
                  ) : (
                    <div className="text-center py-12 text-gray-400">
                      <Database className="w-12 h-12 mx-auto mb-2 opacity-50" />
                      <p className="text-sm">暂无提取数据</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Helper functions
function getMaterialTypeName(type: string): string {
  const typeMap: Record<string, string> = {
    license: '营业执照',
    legal_person_cert: '法定代表人资格证明书',
    id_card: '身份证',
    education: '学历证书',
    iso_cert: 'ISO认证证书',
    certificate: '证书',
    contract: '合同',
    authorization: '授权书',
    invoice: '发票',
    other: '其他',
  };
  return typeMap[type] || type;
}

function getFieldName(key: string): string {
  const fieldMap: Record<string, string> = {
    company_name: '公司名称',
    name: '姓名',
    legal_person: '法定代表人',
    credit_code: '统一社会信用代码',
    address: '地址',
    registered_capital: '注册资本',
    id_number: '身份证号',
    gender: '性别',
    nation: '民族',
    birth_date: '出生日期',
    issue_authority: '签发机关',
    valid_period: '有效期',
    education: '学历',
    degree: '学位',
    major: '专业',
    cert_name: '证书名称',
    holder: '持有人',
    cert_number: '证书编号',
    issue_date: '发证日期',
    expiry_date: '有效期至',
    scope: '认证范围',
  };
  return fieldMap[key] || key;
}
