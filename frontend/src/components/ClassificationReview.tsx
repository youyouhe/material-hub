import { RenderValue } from '../utils/format';
import { useState, useEffect } from 'react';
import { Brain, Save, FolderOpen, Tag, AlertCircle, Plus, Check, X } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { createDocType } from '../services/api-v2';
import type { ProcessingStatus, DocType, FolderTreeNode } from '../types/dms';

interface ClassificationReviewProps {
  data: ProcessingStatus;
  docTypes: DocType[];
  folders: FolderTreeNode[];
  onSave: (updates: {
    title: string;
    doc_type_id: number | null;
    folder_id: number | null;
    material_type: string | null;
  }) => void;
  onFinalize: (updates: {
    title: string;
    doc_type_id: number | null;
    folder_id: number | null;
  }) => void;
  onDocTypesChanged?: () => void;
  saving?: boolean;
  finalizing?: boolean;
}

function flattenFolders(nodes: FolderTreeNode[], depth = 0): { id: number; name: string; indent: number }[] {
  const result: { id: number; name: string; indent: number }[] = [];
  for (const n of nodes) {
    result.push({ id: n.id, name: n.name, indent: depth });
    if (n.children) result.push(...flattenFolders(n.children, depth + 1));
  }
  return result;
}

const CONFIDENCE_COLORS: Record<string, string> = {
  high: 'text-green-400',
  medium: 'text-amber-400',
  low: 'text-cp-rose',
};

const CATEGORY_OPTIONS = [
  { value: 'company', label: '企业资质' },
  { value: 'personnel', label: '人员证件' },
  { value: 'project', label: '项目文档' },
  { value: 'bid', label: '投标文档' },
  { value: 'general', label: '通用文档' },
];

function getConfidenceLevel(c: number | null): string {
  if (!c) return 'low';
  if (c >= 0.8) return 'high';
  if (c >= 0.5) return 'medium';
  return 'low';
}

/** Build a suggested title from LLM-extracted metadata. */
function buildSuggestedTitle(data: ProcessingStatus): string | null {
  const ext = data.extracted_data;
  if (!ext || Object.keys(ext).length === 0) return null;

  const nameKeys = [
    'contract_name', 'certificate_name', 'document_name', 'license_name',
    'project_name', 'title', 'name',
  ];
  const primary = nameKeys.find((k) => ext[k] && String(ext[k]).trim());
  if (!primary) return null;

  const parts: string[] = [String(ext[primary]).trim()];

  const secondaryMap: Record<string, string[]> = {
    contract_name: ['project_name', 'client_party', 'trustee_party'],
    certificate_name: ['holder', 'company_name', 'issuer'],
    license_name: ['company_name', 'holder'],
    document_name: ['company_name', 'project_name'],
    project_name: ['company_name', 'client_party'],
  };
  const candidates = secondaryMap[primary] || ['company_name', 'project_name'];
  const secondary = candidates.find((k) => ext[k] && String(ext[k]).trim() && k !== primary);
  if (secondary) {
    parts.push(String(ext[secondary]).trim());
  }

  return parts.join(' - ');
}

function QuickCreateDocType({ initialName, onCreated, onCancel }: {
  initialName: string;
  onCreated: (dt: DocType) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initialName);
  const [code, setCode] = useState('');
  const [category, setCategory] = useState('general');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    // Auto-generate code from name
    if (name && !code) {
      const auto = name.trim().toLowerCase().replace(/[\s]+/g, '-').replace(/[^a-z0-9-]/g, '') || 'custom-type';
      setCode(auto);
    }
  }, []);

  const handleSubmit = async () => {
    if (!name.trim() || !code.trim()) { toast.error('名称和Code不能为空'); return; }
    setSubmitting(true);
    try {
      const dt = await createDocType({ name: name.trim(), code: code.trim(), category });
      toast.success(`文档类型「${dt.name}」已创建`);
      onCreated(dt);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '创建失败');
    } finally { setSubmitting(false); }
  };

  return (
    <div className="mt-2 p-3 rounded-lg bg-cp-bg/80 border border-cp-cyan/30 space-y-2">
      <div className="flex items-center gap-2 mb-1">
        <Plus className="w-3.5 h-3.5 text-cp-cyan" />
        <span className="text-xs font-medium text-cp-cyan">快速新建文档类型</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs text-cp-dim mb-0.5">类型名称</label>
          <input value={name} onChange={e => setName(e.target.value)} className="cp-input w-full rounded px-2 py-1.5 text-sm" placeholder="如：PMP证书" />
        </div>
        <div>
          <label className="block text-xs text-cp-dim mb-0.5">Code</label>
          <input value={code} onChange={e => setCode(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))} className="cp-input w-full rounded px-2 py-1.5 text-sm font-mono" placeholder="如：pmp-cert" />
        </div>
      </div>
      <div>
        <label className="block text-xs text-cp-dim mb-0.5">分类</label>
        <select value={category} onChange={e => setCategory(e.target.value)} className="cp-select w-full rounded px-2 py-1.5 text-sm">
          {CATEGORY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
      <div className="flex justify-end gap-2 pt-1">
        <button onClick={onCancel} className="cp-btn-ghost px-3 py-1 text-xs rounded flex items-center gap-1">
          <X className="w-3 h-3" /> 取消
        </button>
        <button onClick={handleSubmit} disabled={submitting} className="cp-btn-primary px-3 py-1 text-xs rounded flex items-center gap-1">
          <Check className="w-3 h-3" /> {submitting ? '创建中...' : '创建并选择'}
        </button>
      </div>
    </div>
  );
}

export default function ClassificationReview({
  data, docTypes, folders, onSave, onFinalize, onDocTypesChanged, saving, finalizing,
}: ClassificationReviewProps) {
  const suggestedTitle = buildSuggestedTitle(data);
  const [title, setTitle] = useState(suggestedTitle || data.title);
  const [docTypeId, setDocTypeId] = useState<number>(data.doc_type?.id || data.suggested_doc_type?.id || 0);
  const [folderId, setFolderId] = useState<number>(data.folder?.id || data.suggested_folder?.id || 0);
  const [materialType, setMaterialType] = useState(data.material_type || '');
  const [showCreateType, setShowCreateType] = useState(false);

  useEffect(() => {
    const suggested = buildSuggestedTitle(data);
    setTitle(suggested || data.title);
    setDocTypeId(data.doc_type?.id || data.suggested_doc_type?.id || 0);
    setFolderId(data.folder?.id || data.suggested_folder?.id || 0);
    setMaterialType(data.material_type || '');
  }, [data]);

  const flatFolders = flattenFolders(folders);
  const confidence = data.confidence;
  const level = getConfidenceLevel(confidence);

  const handleDocTypeCreated = (dt: DocType) => {
    setDocTypeId(dt.id);
    setShowCreateType(false);
    onDocTypesChanged?.();
  };

  const handleDocTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    if (val === '__create__') {
      setShowCreateType(true);
    } else {
      setDocTypeId(Number(val));
      setShowCreateType(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Classification result summary */}
      <div className="cp-card rounded-lg p-4 border border-cp-border/50">
        <div className="flex items-center gap-2 mb-3">
          <Brain className="w-4 h-4 text-cp-cyan" />
          <h4 className="text-sm font-orbitron font-semibold text-cp-text">LLM 分类结果</h4>
          {confidence !== null && (
            <span className={clsx('text-xs', CONFIDENCE_COLORS[level])}>
              置信度: {Math.round(confidence * 100)}%
            </span>
          )}
        </div>

        {data.summary && (
          <p className="text-sm text-cp-muted mb-3">{data.summary}</p>
        )}

        {data.material_type && (
          <div className="flex items-center gap-2 text-xs text-cp-dim mb-2">
            <Tag className="w-3 h-3" />
            <span>识别类型: <span className="text-cp-purple-light">{data.material_type}</span></span>
          </div>
        )}

        {data.extracted_data && Object.keys(data.extracted_data).length > 0 && (
          <div className="mt-3 p-3 rounded bg-cp-bg/50 border border-cp-border/30">
            <p className="text-xs text-cp-dim mb-2">提取的元数据:</p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              {Object.entries(data.extracted_data).map(([key, value]) => (
                <div key={key} className="text-xs">
                  <span className="text-cp-dim">{key}: </span>
                  <span className="text-cp-muted">{<RenderValue value={value} />}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {level === 'low' && (
          <div className="flex items-center gap-2 mt-3 p-2 rounded bg-cp-rose/10 border border-cp-rose/20">
            <AlertCircle className="w-4 h-4 text-cp-rose shrink-0" />
            <p className="text-xs text-cp-rose">置信度较低，请仔细核实分类结果</p>
          </div>
        )}
      </div>

      {/* Editable fields */}
      <div className="space-y-3">
        <div>
          <label className="block text-sm font-medium text-cp-muted mb-1">
            文档标题
            {suggestedTitle && (
              <span className="text-xs text-cp-purple-light ml-1">(AI生成)</span>
            )}
          </label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="cp-input w-full rounded-md px-3 py-2 text-sm"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-cp-muted mb-1">
              文档类型
              {data.suggested_doc_type && !data.doc_type && (
                <span className="text-xs text-cp-purple-light ml-1">(AI推荐)</span>
              )}
            </label>
            <select
              value={showCreateType ? '__create__' : docTypeId}
              onChange={handleDocTypeChange}
              className="cp-select w-full rounded-md px-3 py-2 text-sm"
            >
              <option value={0}>-- 选择类型 --</option>
              {docTypes.map((dt) => (
                <option key={dt.id} value={dt.id}>{dt.name}</option>
              ))}
              <option value="__create__">➕ 新建文档类型...</option>
            </select>

            {showCreateType && (
              <QuickCreateDocType
                initialName={data.material_type || ''}
                onCreated={handleDocTypeCreated}
                onCancel={() => { setShowCreateType(false); setDocTypeId(0); }}
              />
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-cp-muted mb-1">
              <FolderOpen className="w-3 h-3 inline mr-1" />
              文件夹
              {data.suggested_folder && !data.folder && (
                <span className="text-xs text-cp-purple-light ml-1">(AI推荐)</span>
              )}
            </label>
            <select
              value={folderId}
              onChange={(e) => setFolderId(Number(e.target.value))}
              className="cp-select w-full rounded-md px-3 py-2 text-sm"
            >
              <option value={0}>-- 选择文件夹 --</option>
              {flatFolders.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.indent === 0 ? `📁 ${f.name}` : `${'\u00A0\u00A0\u00A0\u00A0'.repeat(f.indent)}└ ${f.name}`}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-4 border-t border-cp-border/50">
        <button
          onClick={() => onSave({
            title,
            doc_type_id: docTypeId || null,
            folder_id: folderId || null,
            material_type: materialType || null,
          })}
          disabled={saving}
          className="cp-btn-ghost flex items-center gap-1 px-4 py-2 text-sm rounded-lg border border-cp-border"
        >
          <Save className="w-4 h-4" />
          {saving ? '保存中...' : '保存修改'}
        </button>
        <button
          onClick={() => onFinalize({
            title,
            doc_type_id: docTypeId || null,
            folder_id: folderId || null,
          })}
          disabled={finalizing}
          className="cp-btn-primary flex items-center gap-1 px-4 py-2 text-sm rounded-lg disabled:opacity-40"
        >
          {finalizing ? '入库中...' : '确认入库'}
        </button>
      </div>
    </div>
  );
}
