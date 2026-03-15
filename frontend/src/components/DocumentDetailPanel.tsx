import { useState, useEffect } from 'react';
import { X, Lock, Unlock, Tag, Users, FileText, Clock, Edit3, Save, XCircle, Eye, Brain, Archive, Trash2, RotateCcw } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { getDocument, updateDocument, deleteDocument, lockDocument, unlockDocument, listRevisions } from '../services/api-v2';
import type { DmsDocument, DmsFile, Revision } from '../types/dms';
import FilePreviewModal from './FilePreviewModal';

interface DocumentDetailPanelProps {
  documentId: number;
  userRole: string;
  onClose: () => void;
  onUpdated: () => void;
}

export default function DocumentDetailPanel({ documentId, userRole, onClose, onUpdated }: DocumentDetailPanelProps) {
  const [doc, setDoc] = useState<DmsDocument | null>(null);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [previewFile, setPreviewFile] = useState<DmsFile | null>(null);

  const canEdit = userRole === 'editor' || userRole === 'admin';

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getDocument(documentId),
      listRevisions(documentId),
    ]).then(([docData, revData]) => {
      setDoc(docData);
      setRevisions(revData.revisions);
      setEditTitle(docData.title);
    }).catch(() => {
      toast.error('加载文档详情失败');
    }).finally(() => setLoading(false));
  }, [documentId]);

  const handleSaveTitle = async () => {
    if (!doc || editTitle === doc.title) { setEditing(false); return; }
    try {
      const updated = await updateDocument(doc.id, { title: editTitle });
      setDoc(updated);
      setEditing(false);
      onUpdated();
      toast.success('标题已更新');
    } catch { toast.error('更新失败'); }
  };

  const handleToggleLock = async () => {
    if (!doc) return;
    try {
      if (doc.lock?.is_locked) {
        await unlockDocument(doc.id);
        toast.success('文档已解锁');
      } else {
        await lockDocument(doc.id);
        toast.success('文档已锁定');
      }
      const updated = await getDocument(doc.id);
      setDoc(updated);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '操作失败');
    }
  };

  const VALID_TRANSITIONS: Record<string, string[]> = {
    draft: ['active'],
    active: ['archived'],
    expired: ['archived'],
    archived: [],
  };

  const STATUS_LABELS: Record<string, string> = {
    draft: '草稿', active: '生效', expired: '已过期', archived: '已归档',
  };

  const handleStatusChange = async (newStatus: string) => {
    if (!doc) return;
    const label = STATUS_LABELS[newStatus] || newStatus;
    if (!confirm(`确定将文档状态变更为「${label}」？`)) return;
    try {
      const updated = await updateDocument(doc.id, { status: newStatus });
      setDoc(updated);
      onUpdated();
      toast.success(`状态已变更为「${label}」`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '状态变更失败');
    }
  };

  const handleDelete = async () => {
    if (!doc) return;
    if (!confirm(`确定要永久删除「${doc.title}」？此操作不可恢复！`)) return;
    try {
      await deleteDocument(doc.id);
      toast.success('文档已删除');
      onClose();
      onUpdated();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败');
    }
  };

  const statusColors: Record<string, string> = {
    active: 'bg-green-900/30 text-green-400',
    draft: 'bg-yellow-900/30 text-yellow-400',
    archived: 'bg-gray-800/30 text-gray-400',
    expired: 'bg-red-900/30 text-red-400',
    superseded: 'bg-purple-900/30 text-purple-400',
  };

  if (loading) {
    return (
      <div className="w-[400px] bg-cp-card border-l border-cp-border p-6 shrink-0">
        <div className="text-center text-cp-dim py-12">加载中...</div>
      </div>
    );
  }

  if (!doc) return null;

  return (
    <div className="w-[400px] bg-cp-card border-l border-cp-border shrink-0 overflow-y-auto max-h-[calc(100vh-6rem)]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-cp-border sticky top-0 bg-cp-card z-10">
        <span className="text-sm font-orbitron font-semibold text-cp-purple-light">文档详情</span>
        <button onClick={onClose} className="p-1 rounded hover:bg-white/5">
          <X className="w-4 h-4 text-cp-dim" />
        </button>
      </div>

      <div className="p-4 space-y-4">
        {/* Title */}
        <div>
          {editing ? (
            <div className="flex gap-2">
              <input
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                className="cp-input flex-1 text-lg font-semibold rounded px-2 py-1"
                autoFocus
              />
              <button onClick={handleSaveTitle} className="p-1 text-green-400 hover:bg-green-900/20 rounded"><Save className="w-4 h-4" /></button>
              <button onClick={() => { setEditing(false); setEditTitle(doc.title); }} className="p-1 text-cp-dim hover:bg-white/5 rounded"><XCircle className="w-4 h-4" /></button>
            </div>
          ) : (
            <div className="flex items-start gap-2">
              <h3 className="text-lg font-semibold text-cp-text flex-1">{doc.title}</h3>
              {canEdit && (
                <button onClick={() => setEditing(true)} className="p-1 text-cp-dim hover:bg-white/5 rounded shrink-0">
                  <Edit3 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          )}
        </div>

        {/* Status & Lock & Actions */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className={clsx('px-2 py-0.5 text-xs rounded-full', statusColors[doc.status] || 'bg-gray-800/30 text-gray-400')}>
            {STATUS_LABELS[doc.status] || doc.status}
          </span>
          {doc.lock?.is_locked && (
            <span className="flex items-center gap-1 text-xs text-amber-400">
              <Lock className="w-3 h-3" /> 已锁定
            </span>
          )}
          {canEdit && (
            <button
              onClick={handleToggleLock}
              className="text-xs text-cp-dim hover:text-cp-text flex items-center gap-1"
            >
              {doc.lock?.is_locked ? <Unlock className="w-3 h-3" /> : <Lock className="w-3 h-3" />}
              {doc.lock?.is_locked ? '解锁' : '锁定'}
            </button>
          )}
        </div>

        {/* Status transitions & Delete */}
        {canEdit && (
          <div className="flex items-center gap-2 flex-wrap">
            {VALID_TRANSITIONS[doc.status]?.map((target) => (
              <button
                key={target}
                onClick={() => handleStatusChange(target)}
                className={clsx(
                  'flex items-center gap-1 px-2.5 py-1 text-xs rounded border transition-colors',
                  target === 'archived'
                    ? 'border-gray-600 text-gray-400 hover:bg-gray-800/40'
                    : 'border-cp-purple/40 text-cp-purple-light hover:bg-cp-purple/10',
                )}
              >
                {target === 'archived' && <Archive className="w-3 h-3" />}
                {target === 'active' && <RotateCcw className="w-3 h-3" />}
                {STATUS_LABELS[target]}
              </button>
            ))}
            <button
              onClick={handleDelete}
              className="flex items-center gap-1 px-2.5 py-1 text-xs rounded border border-red-800/50 text-red-400 hover:bg-red-900/20 transition-colors ml-auto"
            >
              <Trash2 className="w-3 h-3" /> 删除
            </button>
          </div>
        )}

        {/* Metadata */}
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-cp-dim">文档类型</span>
            <span className="text-cp-text">{doc.doc_type?.name || '-'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-cp-dim">文件夹</span>
            <span className="text-cp-text">{doc.folder?.name || '-'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-cp-dim">到期日</span>
            <span className={clsx('text-cp-text', doc.status === 'expired' && 'text-cp-rose')}>
              {doc.expiry_date || '-'}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-cp-dim">创建时间</span>
            <span className="text-cp-text">{doc.created_at?.slice(0, 10) || '-'}</span>
          </div>
          {doc.description && (
            <div>
              <span className="text-cp-dim">描述</span>
              <p className="text-cp-muted mt-1">{doc.description}</p>
            </div>
          )}
        </div>

        {/* AI Extracted Metadata */}
        {doc.metadata && (doc.metadata.extracted_data || doc.metadata.summary || doc.metadata.material_type) && (() => {
          const meta = doc.metadata as Record<string, unknown>;
          const extracted = (meta.extracted_data || {}) as Record<string, unknown>;
          const summary = meta.summary as string | undefined;
          const materialType = meta.material_type as string | undefined;
          const confidence = meta.confidence as number | undefined;
          const hasExtracted = Object.keys(extracted).length > 0;

          const FIELD_LABELS: Record<string, string> = {
            company_name: '公司名称', legal_person: '法定代表人', credit_code: '统一社会信用代码',
            address: '地址', registered_capital: '注册资本', business_scope: '经营范围',
            establishment_date: '成立日期', business_term: '营业期限',
            name: '姓名', gender: '性别', nation: '民族', birth_date: '出生日期',
            id_number: '身份证号', issue_authority: '签发机关', valid_period: '有效期',
            cert_name: '证书名称', holder: '持有人/单位', cert_number: '证书编号',
            issue_date: '发证日期', expiry_date: '到期日期', scope: '认证范围',
            party_a: '甲方', party_b: '乙方', contract_number: '合同编号',
            contract_date: '签订日期', contract_amount: '合同金额', contract_term: '合同期限',
            project_name: '项目名称', project_location: '项目地点',
          };

          return (
            <div>
              <h4 className="text-sm font-medium text-cp-purple-light flex items-center gap-1 mb-2">
                <Brain className="w-3.5 h-3.5" /> AI 提取信息
              </h4>
              <div className="rounded-lg p-3 bg-cp-bg/50 border border-cp-border/30 space-y-2">
                {materialType && materialType !== 'unknown' && (
                  <div className="flex justify-between text-sm">
                    <span className="text-cp-dim">材料类型</span>
                    <span className="text-cp-purple-light">{materialType}</span>
                  </div>
                )}
                {confidence !== undefined && confidence > 0 && (
                  <div className="flex justify-between text-sm">
                    <span className="text-cp-dim">置信度</span>
                    <span className={confidence >= 0.8 ? 'text-green-400' : confidence >= 0.5 ? 'text-amber-400' : 'text-cp-rose'}>
                      {Math.round(confidence * 100)}%
                    </span>
                  </div>
                )}
                {summary && (
                  <div className="text-sm">
                    <span className="text-cp-dim">摘要</span>
                    <p className="text-cp-muted mt-0.5">{summary}</p>
                  </div>
                )}
                {hasExtracted && (
                  <div className="pt-1 border-t border-cp-border/30 space-y-1.5">
                    {Object.entries(extracted).map(([key, value]) => {
                      if (!value) return null;
                      const label = FIELD_LABELS[key] || key;
                      return (
                        <div key={key} className="flex justify-between text-sm gap-2">
                          <span className="text-cp-dim shrink-0">{label}</span>
                          <span className="text-cp-text text-right break-all">{String(value)}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          );
        })()}

        {/* Entities */}
        {doc.entities && doc.entities.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-cp-purple-light flex items-center gap-1 mb-2">
              <Users className="w-3.5 h-3.5" /> 关联实体
            </h4>
            <div className="space-y-1">
              {doc.entities.map((e) => (
                <div key={e.id} className="flex items-center gap-2 text-sm">
                  <span className="text-cp-text">{e.entity_name}</span>
                  <span className="text-xs text-cp-dim">({e.role})</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tags */}
        {doc.tags && doc.tags.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-cp-purple-light flex items-center gap-1 mb-2">
              <Tag className="w-3.5 h-3.5" /> 标签
            </h4>
            <div className="flex flex-wrap gap-1">
              {doc.tags.map((t) => (
                <span
                  key={t.tag_id}
                  className="px-2 py-0.5 text-xs rounded-full"
                  style={{
                    backgroundColor: t.tag_color ? `${t.tag_color}20` : 'rgba(124,58,237,0.1)',
                    color: t.tag_color || '#A78BFA',
                  }}
                >
                  {t.tag_name}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Revisions */}
        <div>
          <h4 className="text-sm font-medium text-cp-purple-light flex items-center gap-1 mb-2">
            <Clock className="w-3.5 h-3.5" /> 版本历史
          </h4>
          {revisions.length === 0 ? (
            <p className="text-sm text-cp-dim">无版本记录</p>
          ) : (
            <div className="space-y-2">
              {revisions.map((rev) => (
                <div key={rev.id} className="border border-cp-border/50 rounded p-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium text-cp-text">
                      v{rev.version_number}
                      {rev.is_current && <span className="ml-1 text-xs text-green-400">(当前)</span>}
                    </span>
                    <span className="text-xs text-cp-dim">{rev.created_at?.slice(0, 10)}</span>
                  </div>
                  {rev.change_note && (
                    <p className="text-xs text-cp-muted mt-1">{rev.change_note}</p>
                  )}
                  {rev.files.length > 0 && (
                    <div className="mt-1 space-y-0.5">
                      {rev.files.map((f) => (
                        <button
                          key={f.id}
                          onClick={() => setPreviewFile(f)}
                          className="flex items-center gap-1 text-xs text-cp-cyan hover:underline w-full text-left"
                        >
                          <Eye className="w-3 h-3 shrink-0" />
                          <span className="truncate">{f.filename}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* File preview modal */}
      {previewFile && (
        <FilePreviewModal
          url={previewFile.url}
          filename={previewFile.filename}
          mimeType={previewFile.mime_type}
          onClose={() => setPreviewFile(null)}
        />
      )}
    </div>
  );
}
