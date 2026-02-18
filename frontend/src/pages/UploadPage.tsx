import { useState, useCallback, useEffect } from 'react';
import { Upload, FileText, CheckCircle, AlertCircle, Loader2, Image as ImageIcon } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import * as api from '../services/api';
import type { ExtractionResult, MaterialInfo, CompanyInfo } from '../types';

interface UploadPageProps {
  onExtracted: () => void;
}

type UploadMode = 'document' | 'image';

export default function UploadPage({ onExtracted }: UploadPageProps) {
  const [mode, setMode] = useState<UploadMode>('document');
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [uploadedImage, setUploadedImage] = useState<MaterialInfo | null>(null);

  // 单张图片上传
  const [imageTitle, setImageTitle] = useState('');
  const [imageSection, setImageSection] = useState('手动上传');

  // 公司选择
  const [selectedCompany, setSelectedCompany] = useState<number | undefined>();
  const [companies, setCompanies] = useState<CompanyInfo[]>([]);

  useEffect(() => {
    loadCompanies();
  }, []);

  const loadCompanies = async () => {
    try {
      const data = await api.listCompanies();
      setCompanies(data);
    } catch (err) {
      console.error('Failed to load companies:', err);
    }
  };

  const handleDocumentFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith('.docx')) {
        toast.error('仅支持 .docx 文件');
        return;
      }

      setUploading(true);
      setResult(null);

      try {
        const res = await api.uploadDocument(file, selectedCompany);
        setResult(res);
        toast.success(
          `已从 ${res.section_count} 个章节提取 ${res.image_count} 张图片`
        );
        onExtracted();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : '上传失败');
      } finally {
        setUploading(false);
      }
    },
    [onExtracted, selectedCompany]
  );

  const handleImageFile = useCallback(
    async (file: File) => {
      if (!file.type.startsWith('image/')) {
        toast.error('仅支持图片文件 (PNG, JPG)');
        return;
      }

      setUploading(true);
      setUploadedImage(null);

      try {
        const title = imageTitle || file.name.replace(/\.[^/.]+$/, '');
        const res = await api.uploadSingleImage(file, title, imageSection, selectedCompany);
        setUploadedImage(res);
        toast.success('图片上传成功');
        setImageTitle('');
        onExtracted();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : '上传失败');
      } finally {
        setUploading(false);
      }
    },
    [imageTitle, imageSection, onExtracted, selectedCompany]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) {
        if (mode === 'document') {
          handleDocumentFile(file);
        } else {
          handleImageFile(file);
        }
      }
    },
    [mode, handleDocumentFile, handleImageFile]
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        if (mode === 'document') {
          handleDocumentFile(file);
        } else {
          handleImageFile(file);
        }
      }
    },
    [mode, handleDocumentFile, handleImageFile]
  );

  return (
    <div className="max-w-2xl mx-auto">
      {/* Mode Selector */}
      <div className="mb-6 flex items-center gap-2 bg-white rounded-lg p-1 border">
        <button
          onClick={() => {
            setMode('document');
            setResult(null);
            setUploadedImage(null);
          }}
          className={clsx(
            'flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-md transition-colors',
            mode === 'document'
              ? 'bg-blue-500 text-white'
              : 'text-gray-600 hover:bg-gray-100'
          )}
        >
          <FileText className="w-4 h-4" />
          批量上传 (DOCX)
        </button>
        <button
          onClick={() => {
            setMode('image');
            setResult(null);
            setUploadedImage(null);
          }}
          className={clsx(
            'flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-md transition-colors',
            mode === 'image'
              ? 'bg-blue-500 text-white'
              : 'text-gray-600 hover:bg-gray-100'
          )}
        >
          <ImageIcon className="w-4 h-4" />
          单张图片 (PNG/JPG)
        </button>
      </div>

      {/* Company Selector (Optional) */}
      <div className="mb-4 bg-white rounded-lg border p-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          所属公司 (可选，留空则自动识别)
        </label>
        <select
          value={selectedCompany ?? ''}
          onChange={(e) => setSelectedCompany(e.target.value ? Number(e.target.value) : undefined)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">自动识别</option>
          {companies.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-gray-500">
          选择公司后，上传的材料将直接关联到该公司（跳过OCR识别）
        </p>
      </div>

      {/* Image Upload Settings */}
      {mode === 'image' && (
        <div className="mb-4 bg-white rounded-lg border p-4 space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              标题 (可选)
            </label>
            <input
              type="text"
              value={imageTitle}
              onChange={(e) => setImageTitle(e.target.value)}
              placeholder="留空则使用文件名"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              分类
            </label>
            <input
              type="text"
              value={imageSection}
              onChange={(e) => setImageSection(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            />
          </div>
        </div>
      )}

      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={clsx(
          'border-2 border-dashed rounded-xl p-12 text-center transition-colors',
          dragging
            ? 'border-blue-400 bg-blue-50'
            : 'border-gray-300 bg-white hover:border-gray-400'
        )}
      >
        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-10 h-10 text-blue-500 animate-spin" />
            <p className="text-sm text-gray-600">
              {mode === 'document' ? '正在提取材料...' : '正在上传图片...'}
            </p>
          </div>
        ) : (
          <label className="cursor-pointer flex flex-col items-center gap-3">
            {mode === 'document' ? (
              <>
                <Upload className="w-10 h-10 text-gray-400" />
                <p className="text-sm text-gray-600">
                  拖放 <strong>.docx</strong> 文件到这里，或点击选择文件
                </p>
                <input
                  type="file"
                  accept=".docx"
                  onChange={handleInputChange}
                  className="hidden"
                />
              </>
            ) : (
              <>
                <ImageIcon className="w-10 h-10 text-gray-400" />
                <p className="text-sm text-gray-600">
                  拖放 <strong>PNG/JPG</strong> 图片到这里，或点击选择文件
                </p>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/jpg"
                  onChange={handleInputChange}
                  className="hidden"
                />
              </>
            )}
          </label>
        )}
      </div>

      {/* Document Extraction result */}
      {result && mode === 'document' && (
        <div className="mt-6 bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle className="w-5 h-5 text-green-500" />
            <h3 className="font-medium text-gray-900">提取完成</h3>
          </div>

          <div className="flex items-center gap-4 text-sm text-gray-600 mb-4">
            <span className="flex items-center gap-1">
              <FileText className="w-4 h-4" />
              {result.filename}
            </span>
            <span>{result.section_count} 个章节</span>
            <span>{result.image_count} 张图片</span>
          </div>

          <div className="space-y-2 max-h-64 overflow-y-auto">
            {result.materials.map((m) => (
              <div
                key={m.id}
                className="flex items-center gap-3 px-3 py-2 bg-gray-50 rounded text-sm"
              >
                <img
                  src={m.image_url}
                  alt={m.title}
                  className="w-10 h-10 object-cover rounded"
                />
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-gray-900 truncate">
                    {m.section ? `${m.section} ` : ''}
                    {m.title}
                  </p>
                  {m.expiry_date && (
                    <p className="text-xs text-gray-500">
                      有效期: {m.expiry_date}
                    </p>
                  )}
                </div>
                {m.is_expired ? (
                  <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
                ) : m.expiry_date ? (
                  <CheckCircle className="w-4 h-4 text-green-500 shrink-0" />
                ) : null}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Single Image Upload result */}
      {uploadedImage && mode === 'image' && (
        <div className="mt-6 bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle className="w-5 h-5 text-green-500" />
            <h3 className="font-medium text-gray-900">上传成功</h3>
          </div>

          <div className="flex items-center gap-3 px-3 py-2 bg-gray-50 rounded">
            <img
              src={uploadedImage.image_url}
              alt={uploadedImage.title}
              className="w-20 h-20 object-cover rounded"
            />
            <div className="flex-1 min-w-0">
              <p className="font-medium text-gray-900">
                {uploadedImage.title}
              </p>
              <p className="text-sm text-gray-500">
                {uploadedImage.section}
              </p>
              <p className="text-xs text-gray-400 mt-1">
                ID: {uploadedImage.id} • {(uploadedImage.file_size / 1024).toFixed(1)} KB
              </p>
            </div>
          </div>

          <div className="mt-3 text-sm text-gray-600">
            <p>提示: 可以在素材库中编辑标题、设置有效期，或手动触发OCR识别。</p>
          </div>
        </div>
      )}
    </div>
  );
}
