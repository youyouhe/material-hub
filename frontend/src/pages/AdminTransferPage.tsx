import { useState } from 'react';
import { Download, Upload, AlertTriangle, CheckCircle } from 'lucide-react';
import toast from 'react-hot-toast';

export default function AdminTransferPage() {
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);

  const handleExport = async () => {
    try {
      const token = localStorage.getItem('materialhub_auth_token');
      const res = await fetch('/api/v2/admin/export', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Export failed' }));
        throw new Error(err.detail);
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const disposition = res.headers.get('content-disposition') || '';
      const match = disposition.match(/filename="?(.+?)"?$/);
      a.download = match?.[1] || 'materialhub-export.zip';
      a.click();
      window.URL.revokeObjectURL(url);
      toast.success(`导出完成 (${(blob.size / 1024 / 1024).toFixed(1)} MB)`);
    } catch (err: any) {
      toast.error(`导出失败: ${err.message}`);
    }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!confirm('⚠️ 导入将替换当前所有数据和文件！\n\n系统会自动创建备份，但请确认：\n1. 已停止上传新文件\n2. 当前无正在处理的文档\n\n确定要继续吗？')) {
      e.target.value = '';
      return;
    }

    setImporting(true);
    setImportResult(null);
    try {
      const token = localStorage.getItem('materialhub_auth_token');
      const form = new FormData();
      form.append('file', file);
      const res = await fetch('/api/v2/admin/import', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      setImportResult(data);
      toast.success('导入成功！请重启服务器。');
    } catch (err: any) {
      toast.error(`导入失败: ${err.message}`);
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-orbitron font-bold text-cp-text">数据迁移</h1>
        <p className="text-cp-muted text-sm mt-1">导出/导入完整系统数据，用于服务器迁移</p>
      </div>

      {/* Export */}
      <div className="cp-card rounded-lg p-6">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-lg bg-cp-purple/10 flex items-center justify-center shrink-0">
            <Download className="w-6 h-6 text-cp-purple" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-cp-text">导出数据</h3>
            <p className="text-cp-muted text-sm mt-1">
              打包数据库 + 全部上传文件为 ZIP 归档。下载后在新服务器上使用"导入"功能恢复。
            </p>
            <div className="mt-3 flex items-center gap-2 text-xs text-cp-dim">
              <CheckCircle className="w-3.5 h-3.5 text-cp-green" /> SQLite 数据库
              <CheckCircle className="w-3.5 h-3.5 text-cp-green" /> 全部文档文件
              <CheckCircle className="w-3.5 h-3.5 text-cp-green" /> 版本清单 (manifest)
            </div>
            <button onClick={handleExport}
              className="mt-4 inline-flex items-center gap-2 px-5 py-2.5 cp-btn-primary rounded-lg">
              <Download className="w-4 h-4" /> 导出 ZIP
            </button>
          </div>
        </div>
      </div>

      {/* Import */}
      <div className="cp-card rounded-lg p-6">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-lg bg-cp-rose/10 flex items-center justify-center shrink-0">
            <Upload className="w-6 h-6 text-cp-rose" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-cp-text">导入数据</h3>
            <p className="text-cp-muted text-sm mt-1">
              上传之前导出的 ZIP 归档，替换当前数据库和文件。系统会自动创建备份。
            </p>
            <div className="mt-3 p-3 rounded bg-cp-rose/10 border border-cp-rose/20 text-sm text-cp-rose flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">导入后必须重启服务器</p>
                <p className="text-xs mt-0.5 opacity-80">数据库连接需要重新初始化才能生效</p>
              </div>
            </div>
            <label className="mt-4 inline-flex items-center gap-2 px-5 py-2.5 cp-btn-rose rounded-lg cursor-pointer">
              <Upload className="w-4 h-4" />
              {importing ? '导入中...' : '选择 ZIP 并导入'}
              <input type="file" accept=".zip" onChange={handleImport} className="hidden" disabled={importing} />
            </label>
          </div>
        </div>
      </div>

      {/* Import result */}
      {importResult && (
        <div className="cp-card rounded-lg p-4 border-cp-green/30">
          <h3 className="text-cp-green font-semibold flex items-center gap-2">
            <CheckCircle className="w-5 h-5" /> 导入成功
          </h3>
          <div className="mt-2 text-sm text-cp-muted space-y-1">
            <p>恢复文件数: {importResult.restored_files}</p>
            <p>备份位置: <code className="text-xs bg-cp-purple/10 px-1 rounded">{importResult.backup_dir}</code></p>
          </div>
          <p className="mt-3 text-cp-rose text-sm font-medium">
            ⚠️ 请立即重启服务器！
          </p>
        </div>
      )}
    </div>
  );
}
