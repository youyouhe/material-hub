import { useState, useEffect } from 'react';
import { X, Brain, AlertTriangle, CheckCircle2, FileWarning, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { reprocessCheck, reprocessDocuments, type ReprocessCheckItem } from '../services/api-v2';

interface ReprocessModalProps {
  docIds: number[];
  onClose: () => void;
  onDone: (queuedIds: number[]) => void;
}

const FIELD_LABELS: Record<string, string> = {
  company_name: '公司名称', legal_person: '法定代表人', credit_code: '信用代码',
  address: '地址', registered_capital: '注册资本', name: '姓名',
  id_number: '身份证号', cert_name: '证书名称', cert_number: '证书编号',
  issue_date: '发证日期', expiry_date: '到期日期', party_a: '甲方',
  party_b: '乙方', contract_number: '合同编号', contract_amount: '合同金额',
  project_name: '项目名称', sign_date: '签订日期', holder: '持有人',
  scope: '认证范围', issue_authority: '签发机关',
};

export default function ReprocessModal({ docIds, onClose, onDone }: ReprocessModalProps) {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [items, setItems] = useState<ReprocessCheckItem[]>([]);
  const [forceOverwrite, setForceOverwrite] = useState(false);

  useEffect(() => {
    reprocessCheck(docIds)
      .then((data) => setItems(data.documents))
      .catch(() => toast.error('检查文档状态失败'))
      .finally(() => setLoading(false));
  }, [docIds]);

  const withMeta = items.filter((d) => d.has_metadata);
  const withoutMeta = items.filter((d) => !d.has_metadata && d.has_file);
  const noFile = items.filter((d) => !d.has_file);

  const willProcess = forceOverwrite
    ? items.filter((d) => d.has_file)
    : withoutMeta;

  const handleSubmit = async () => {
    if (willProcess.length === 0) {
      toast.error('没有需要处理的文档');
      return;
    }
    setSubmitting(true);
    try {
      const ids = willProcess.map((d) => d.id);
      const result = await reprocessDocuments(ids, forceOverwrite);
      toast.success(`已提交 ${result.queued} 份文档进行重新分析`);
      onDone(result.queued_ids);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '提交失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl mx-4 cp-card rounded-xl border border-cp-border shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-cp-border">
          <h3 className="text-base font-orbitron font-semibold text-cp-text flex items-center gap-2">
            <Brain className="w-5 h-5 text-cp-cyan" />
            OCR + AI 重新分析
          </h3>
          <button onClick={onClose} className="p-1 text-cp-dim hover:text-cp-text rounded hover:bg-white/10">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 max-h-[60vh] overflow-y-auto">
          {loading ? (
            <div className="text-center py-8 text-cp-dim">
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
              检查文档状态...
            </div>
          ) : (
            <div className="space-y-4">
              {/* Summary */}
              <div className="text-sm text-cp-muted">
                已选择 <span className="text-cp-text font-medium">{items.length}</span> 份文档
              </div>

              {/* Documents without metadata — will process directly */}
              {withoutMeta.length > 0 && (
                <div>
                  <div className="flex items-center gap-1.5 text-sm font-medium text-green-400 mb-2">
                    <CheckCircle2 className="w-4 h-4" />
                    无元数据，可直接分析 ({withoutMeta.length})
                  </div>
                  <div className="space-y-1">
                    {withoutMeta.map((d) => (
                      <div key={d.id} className="text-sm px-3 py-1.5 rounded bg-green-900/10 border border-green-900/20 text-cp-muted">
                        {d.title}
                        {d.summary && <span className="text-cp-dim ml-2">- {d.summary.slice(0, 40)}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Documents with metadata — need confirmation */}
              {withMeta.length > 0 && (
                <div>
                  <div className="flex items-center gap-1.5 text-sm font-medium text-yellow-400 mb-2">
                    <AlertTriangle className="w-4 h-4" />
                    已有元数据 ({withMeta.length})
                  </div>
                  <div className="space-y-1">
                    {withMeta.map((d) => (
                      <div key={d.id} className="text-sm px-3 py-1.5 rounded bg-yellow-900/10 border border-yellow-900/20">
                        <div className="text-cp-muted">{d.title}</div>
                        <div className="text-xs text-cp-dim mt-0.5">
                          已提取: {d.metadata_fields.map((f) => FIELD_LABELS[f] || f).join('、')}
                        </div>
                      </div>
                    ))}
                  </div>
                  <label className="flex items-center gap-2 mt-2 text-sm text-yellow-400 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={forceOverwrite}
                      onChange={(e) => setForceOverwrite(e.target.checked)}
                      className="rounded border-yellow-600 text-yellow-500 focus:ring-yellow-500"
                    />
                    覆盖已有元数据，重新分析这些文档
                  </label>
                </div>
              )}

              {/* Documents without file — cannot process */}
              {noFile.length > 0 && (
                <div>
                  <div className="flex items-center gap-1.5 text-sm font-medium text-cp-dim mb-2">
                    <FileWarning className="w-4 h-4" />
                    无原始文件，无法分析 ({noFile.length})
                  </div>
                  <div className="space-y-1">
                    {noFile.map((d) => (
                      <div key={d.id} className="text-sm px-3 py-1.5 rounded bg-white/5 text-cp-dim line-through">
                        {d.title}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Process count */}
              <div className="pt-2 border-t border-cp-border text-sm text-cp-muted">
                将处理 <span className="text-cp-text font-medium">{willProcess.length}</span> 份文档
                {forceOverwrite && withMeta.length > 0 && (
                  <span className="text-yellow-400 ml-1">(含 {withMeta.filter(d => d.has_file).length} 份覆盖)</span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-cp-border">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-cp-muted hover:text-cp-text rounded-lg border border-cp-border hover:border-cp-purple/30 transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading || submitting || willProcess.length === 0}
            className="cp-btn-primary px-4 py-2 text-sm rounded-lg disabled:opacity-30 flex items-center gap-2"
          >
            {submitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                提交中...
              </>
            ) : (
              <>
                <Brain className="w-4 h-4" />
                开始分析 ({willProcess.length})
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
