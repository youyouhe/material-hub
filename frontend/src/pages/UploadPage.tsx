import { useState, useCallback } from 'react';
import { Upload, FileText, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import * as api from '../services/api';
import type { ExtractionResult } from '../types';

interface UploadPageProps {
  onExtracted: () => void;
}

export default function UploadPage({ onExtracted }: UploadPageProps) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<ExtractionResult | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith('.docx')) {
        toast.error('Only .docx files supported');
        return;
      }

      setUploading(true);
      setResult(null);

      try {
        const res = await api.uploadDocument(file);
        setResult(res);
        toast.success(
          `Extracted ${res.image_count} images from ${res.section_count} sections`
        );
        onExtracted();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Upload failed');
      } finally {
        setUploading(false);
      }
    },
    [onExtracted]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  return (
    <div className="max-w-2xl mx-auto">
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
            <p className="text-sm text-gray-600">Extracting materials...</p>
          </div>
        ) : (
          <label className="cursor-pointer flex flex-col items-center gap-3">
            <Upload className="w-10 h-10 text-gray-400" />
            <p className="text-sm text-gray-600">
              Drag & drop a <strong>.docx</strong> file here, or click to select
            </p>
            <input
              type="file"
              accept=".docx"
              onChange={handleInputChange}
              className="hidden"
            />
          </label>
        )}
      </div>

      {/* Extraction result */}
      {result && (
        <div className="mt-6 bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle className="w-5 h-5 text-green-500" />
            <h3 className="font-medium text-gray-900">Extraction Complete</h3>
          </div>

          <div className="flex items-center gap-4 text-sm text-gray-600 mb-4">
            <span className="flex items-center gap-1">
              <FileText className="w-4 h-4" />
              {result.filename}
            </span>
            <span>{result.section_count} sections</span>
            <span>{result.image_count} images</span>
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
                      Expires: {m.expiry_date}
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
    </div>
  );
}
