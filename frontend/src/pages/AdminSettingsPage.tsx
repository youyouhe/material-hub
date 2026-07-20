import { useState, useEffect, useCallback } from 'react';
import { Settings, Save, TestTube2, Eye, EyeOff, Brain, Server } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { getSettings, batchUpdateSettings, testOcr, testLlm } from '../services/api-v2';
import type { SystemSettings } from '../types/dms';

const OCR_PROVIDERS = [
  { value: 'deepseek', label: 'DeepSeek-OCR-2 (本地服务)' },
  { value: 'bigmodel', label: 'BigModel 智谱 (云端API)' },
  { value: 'paddleocr', label: 'PaddleOCR (本地引擎)' },
];

const LLM_PROVIDERS = [
  { value: 'deepseek', label: 'DeepSeek', desc: 'api.deepseek.com' },
  { value: 'openrouter', label: 'OpenRouter', desc: 'openrouter.ai (多模型)' },
  { value: 'anthropic', label: 'Anthropic', desc: 'Claude API' },
];

const LLM_DEFAULT_MODELS: Record<string, string> = {
  deepseek: 'deepseek-chat',
  openrouter: 'anthropic/claude-3.5-sonnet',
  anthropic: 'claude-3-5-sonnet-20241022',
};

const TOOL_TYPES = [
  { value: 'hand_write', label: '手写体' },
  { value: 'print', label: '印刷体' },
  { value: 'both', label: '混合' },
];

const LANGUAGE_TYPES = [
  { value: 'CHN_ENG', label: '中英文' },
  { value: 'CHN', label: '仅中文' },
  { value: 'ENG', label: '仅英文' },
];

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingOcr, setTestingOcr] = useState(false);
  const [testingLlm, setTestingLlm] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});
  const [showApiKey, setShowApiKey] = useState(false);
  const [showLlmKey, setShowLlmKey] = useState(false);
  const [dirty, setDirty] = useState(false);

  const fetchSettings = useCallback(async () => {
    try {
      const data = await getSettings();
      setSettings(data.settings);
      const initial: Record<string, string> = {};
      for (const [key, info] of Object.entries(data.settings)) {
        initial[key] = info.sensitive ? '' : (info.value || '');
      }
      setForm(initial);
      setDirty(false);
    } catch { toast.error('加载设置失败'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  const handleChange = (key: string, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const toSave: Record<string, string> = {};
      for (const [key, value] of Object.entries(form)) {
        if (settings?.[key]?.sensitive && !value) continue;
        toSave[key] = value;
      }
      await batchUpdateSettings(toSave);
      toast.success('设置已保存');
      setDirty(false);
      fetchSettings();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败');
    } finally { setSaving(false); }
  };

  const handleTestOcr = async () => {
    setTestingOcr(true);
    try {
      const result = await testOcr();
      if (result.available) {
        toast.success(result.message);
      } else {
        toast.error(result.message);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '测试失败');
    } finally { setTestingOcr(false); }
  };

  const handleTestLlm = async () => {
    setTestingLlm(true);
    try {
      const result = await testLlm();
      if (result.available) {
        toast.success(result.message);
      } else {
        toast.error(result.message);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'LLM测试失败');
    } finally { setTestingLlm(false); }
  };

  const ocrProvider = form.ocr_provider || 'deepseek';
  const llmProvider = form.llm_provider || 'deepseek';

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-orbitron font-semibold text-cp-text flex items-center gap-2">
          <Settings className="w-5 h-5 text-cp-cyan" /> 系统设置
        </h2>
      </div>

      {loading ? (
        <div className="text-center py-12 text-cp-dim">加载中...</div>
      ) : (
        <div className="space-y-6">
          {/* LLM Section */}
          <div className="cp-card rounded-lg p-5">
            <h3 className="text-sm font-orbitron font-semibold text-cp-purple-light mb-4 flex items-center gap-2">
              <Brain className="w-4 h-4" /> LLM 智能分类服务
            </h3>

            <div className="space-y-4">
              {/* LLM Provider selector */}
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">LLM 提供者</label>
                <div className="flex gap-3">
                  {LLM_PROVIDERS.map((p) => (
                    <button
                      key={p.value}
                      onClick={() => handleChange('llm_provider', p.value)}
                      className={clsx(
                        'flex-1 px-4 py-3 text-sm rounded-lg border transition-colors text-left',
                        llmProvider === p.value
                          ? 'border-cp-purple bg-cp-purple/10 text-cp-purple-light'
                          : 'border-cp-border text-cp-muted hover:border-cp-purple/50 cp-hover'
                      )}
                    >
                      <span className="font-medium block">{p.label}</span>
                      <span className="text-xs text-cp-dim">{p.desc}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* API Key */}
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">
                  API 密钥
                </label>
                <div className="relative">
                  <input
                    type={showLlmKey ? 'text' : 'password'}
                    value={form.llm_api_key || ''}
                    onChange={(e) => handleChange('llm_api_key', e.target.value)}
                    placeholder={settings?.llm_api_key?.value ? '已设置 (留空保持不变)' : '输入API密钥'}
                    className="cp-input w-full rounded-md px-3 py-2 text-sm pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowLlmKey(!showLlmKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-cp-dim hover:text-cp-text"
                  >
                    {showLlmKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <p className="text-xs text-cp-dim mt-1">
                  {llmProvider === 'deepseek' && '在 platform.deepseek.com 获取API密钥'}
                  {llmProvider === 'openrouter' && '在 openrouter.ai/keys 获取API密钥'}
                  {llmProvider === 'anthropic' && '在 console.anthropic.com 获取API密钥'}
                </p>
              </div>

              {/* Model & Base URL */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-cp-muted mb-1">模型名称</label>
                  <input
                    value={form.llm_model || ''}
                    onChange={(e) => handleChange('llm_model', e.target.value)}
                    placeholder={LLM_DEFAULT_MODELS[llmProvider] || '留空使用默认'}
                    className="cp-input w-full rounded-md px-3 py-2 text-sm"
                  />
                  <p className="text-xs text-cp-dim mt-1">
                    留空使用默认: {LLM_DEFAULT_MODELS[llmProvider]}
                  </p>
                </div>
                {llmProvider === 'deepseek' && (
                  <div>
                    <label className="block text-sm font-medium text-cp-muted mb-1">API 地址</label>
                    <input
                      value={form.llm_base_url || ''}
                      onChange={(e) => handleChange('llm_base_url', e.target.value)}
                      placeholder="https://api.deepseek.com"
                      className="cp-input w-full rounded-md px-3 py-2 text-sm"
                    />
                    <p className="text-xs text-cp-dim mt-1">留空使用官方地址</p>
                  </div>
                )}
              </div>
            </div>

            {/* LLM Actions */}
            <div className="flex items-center gap-3 mt-6 pt-4 border-t border-cp-border/50">
              <button
                onClick={handleSave}
                disabled={saving || !dirty}
                className="cp-btn-primary flex items-center gap-1 px-4 py-2 text-sm rounded-lg disabled:opacity-40"
              >
                <Save className="w-4 h-4" />
                {saving ? '保存中...' : '保存设置'}
              </button>
              <button
                onClick={handleTestLlm}
                disabled={testingLlm}
                className="cp-btn-ghost flex items-center gap-1 px-4 py-2 text-sm rounded-lg border border-cp-border"
              >
                <TestTube2 className="w-4 h-4" />
                {testingLlm ? '测试中...' : '测试LLM'}
              </button>
            </div>
          </div>

          {/* OCR Provider Section */}
          <div className="cp-card rounded-lg p-5">
            <h3 className="text-sm font-orbitron font-semibold text-cp-purple-light mb-4">OCR 识别服务</h3>

            <div className="space-y-4">
              {/* Provider selector */}
              <div>
                <label className="block text-sm font-medium text-cp-muted mb-1">OCR 提供者</label>
                <div className="flex gap-3">
                  {OCR_PROVIDERS.map((p) => (
                    <button
                      key={p.value}
                      onClick={() => handleChange('ocr_provider', p.value)}
                      className={clsx(
                        'flex-1 px-4 py-3 text-sm rounded-lg border transition-colors text-left',
                        ocrProvider === p.value
                          ? 'border-cp-purple bg-cp-purple/10 text-cp-purple-light'
                          : 'border-cp-border text-cp-muted hover:border-cp-purple/50 cp-hover'
                      )}
                    >
                      <span className="font-medium">{p.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* DeepSeek settings */}
              {ocrProvider === 'deepseek' && (
                <div>
                  <label className="block text-sm font-medium text-cp-muted mb-1">
                    DeepSeek OCR 服务地址
                  </label>
                  <input
                    value={form.ocr_service_url || ''}
                    onChange={(e) => handleChange('ocr_service_url', e.target.value)}
                    placeholder={settings?.ocr_service_url?.default || 'http://host.docker.internal:8010'}
                    className="cp-input w-full rounded-md px-3 py-2 text-sm"
                  />
                  <p className="text-xs text-cp-dim mt-1">本地部署的DeepSeek-OCR-2服务URL</p>
                </div>
              )}

              {/* BigModel settings */}
              {ocrProvider === 'bigmodel' && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-cp-muted mb-1">
                      BigModel API 密钥
                    </label>
                    <div className="relative">
                      <input
                        type={showApiKey ? 'text' : 'password'}
                        value={form.bigmodel_api_key || ''}
                        onChange={(e) => handleChange('bigmodel_api_key', e.target.value)}
                        placeholder={settings?.bigmodel_api_key?.value ? '已设置 (留空保持不变)' : '输入API密钥'}
                        className="cp-input w-full rounded-md px-3 py-2 text-sm pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-cp-dim hover:text-cp-text"
                      >
                        {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                    <p className="text-xs text-cp-dim mt-1">
                      在 open.bigmodel.cn 获取API密钥
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-cp-muted mb-1">识别模式</label>
                      <select
                        value={form.bigmodel_tool_type || 'hand_write'}
                        onChange={(e) => handleChange('bigmodel_tool_type', e.target.value)}
                        className="cp-select w-full rounded-md px-3 py-2 text-sm"
                      >
                        {TOOL_TYPES.map((t) => (
                          <option key={t.value} value={t.value}>{t.label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-cp-muted mb-1">语言</label>
                      <select
                        value={form.bigmodel_language_type || 'CHN_ENG'}
                        onChange={(e) => handleChange('bigmodel_language_type', e.target.value)}
                        className="cp-select w-full rounded-md px-3 py-2 text-sm"
                      >
                        {LANGUAGE_TYPES.map((l) => (
                          <option key={l.value} value={l.value}>{l.label}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                </>
              )}

              {/* PaddleOCR settings */}
              {ocrProvider === 'paddleocr' && (
                <div>
                  <label className="block text-sm font-medium text-cp-muted mb-1">识别语言</label>
                  <select
                    value={form.paddleocr_lang || 'ch'}
                    onChange={(e) => handleChange('paddleocr_lang', e.target.value)}
                    className="cp-select w-full rounded-md px-3 py-2 text-sm"
                  >
                    <option value="ch">中英文 (ch)</option>
                    <option value="en">英文 (en)</option>
                    <option value="japan">日语 (japan)</option>
                    <option value="korean">韩语 (korean)</option>
                    <option value="french">法语 (french)</option>
                    <option value="german">德语 (german)</option>
                  </select>
                  <p className="text-xs text-cp-dim mt-1">
                    需安装: pip install paddlepaddle paddleocr，首次使用会自动下载模型
                  </p>
                </div>
              )}
            </div>

            {/* OCR Actions */}
            <div className="flex items-center gap-3 mt-6 pt-4 border-t border-cp-border/50">
              <button
                onClick={handleSave}
                disabled={saving || !dirty}
                className="cp-btn-primary flex items-center gap-1 px-4 py-2 text-sm rounded-lg disabled:opacity-40"
              >
                <Save className="w-4 h-4" />
                {saving ? '保存中...' : '保存设置'}
              </button>
              <button
                onClick={handleTestOcr}
                disabled={testingOcr}
                className="cp-btn-ghost flex items-center gap-1 px-4 py-2 text-sm rounded-lg border border-cp-border"
              >
                <TestTube2 className="w-4 h-4" />
                {testingOcr ? '测试中...' : '测试OCR'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MCP Server Status */}
      <MCPStatusCard />
    </div>
  );
}

function MCPStatusCard() {
  const [status, setStatus] = useState<'loading' | 'online' | 'offline'>('loading');
  const [, setInfo] = useState<{ url?: string; token?: string }>({});
  const [busy, setBusy] = useState(false);
  const [tokens, setTokens] = useState<any[]>([]);
  const [roles, setRoles] = useState<any[]>([]);
  const [newTokenName, setNewTokenName] = useState('');
  const [newTokenRoleId, setNewTokenRoleId] = useState<number | ''>('');

  const auth = () => ({ Authorization: `Bearer ${localStorage.getItem('materialhub_auth_token')}` });

  const check = () => {
    setStatus('loading');
    fetch('/api/v2/settings/mcp/status', { headers: auth() })
      .then(r => r.json()).then(d => { setStatus(d.running ? 'online' : 'offline'); setInfo(d); })
      .catch(() => setStatus('offline'));
  };

  const loadTokens = () => {
    fetch('/api/v2/settings/mcp/tokens', { headers: auth() })
      .then(r => r.json()).then(d => setTokens(d.tokens || []));
  };
  const loadRoles = () => {
    fetch('/api/v2/admin/roles/', { headers: auth() })
      .then(r => r.json()).then(d => setRoles(d.roles || []));
  };

  useEffect(() => { check(); loadTokens(); loadRoles(); }, []);

  const action = async (act: 'start' | 'stop') => {
    setBusy(true);
    try {
      await fetch(`/api/v2/settings/mcp/${act}`, { method: 'POST', headers: auth() });
      setTimeout(check, 2000);
    } catch { toast.error('操作失败'); }
    finally { setBusy(false); }
  };

  const createToken = async () => {
    if (!newTokenName || !newTokenRoleId) return;
    try {
      const r = await fetch('/api/v2/settings/mcp/tokens', {
        method: 'POST', headers: { ...auth(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newTokenName, role_id: newTokenRoleId }),
      });
      const d = await r.json();
      toast.success(`Token 已创建: ${d.sse_token?.slice(0, 20)}...`);
      setNewTokenName(''); setNewTokenRoleId('');
      loadTokens();
    } catch { toast.error('创建失败'); }
  };

  const deleteToken = async (id: number) => {
    if (!confirm('删除此 token？')) return;
    await fetch(`/api/v2/settings/mcp/tokens/${id}`, { method: 'DELETE', headers: auth() });
    loadTokens();
  };

  const doCopy = async (text: string) => {
    // 安全上下文（HTTPS / localhost）才可用 Clipboard API；局域网 IP 访问时为 undefined
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        toast.success('已复制');
        return;
      } catch { /* 回退到 execCommand */ }
    }
    // 非安全上下文 fallback：textarea 必须在 execCommand 执行期间留在 DOM 中
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0;z-index:99999';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    ta.setSelectionRange(0, 99999);
    let ok = false;
    try { ok = document.execCommand('copy'); } catch { ok = false; }
    document.body.removeChild(ta);
    if (ok) toast.success('已复制');
    else toast.error('复制失败，请手动选中复制');
  };

  return (
    <div className="cp-card rounded-lg p-4 mt-4 space-y-4">
      {/* Status header */}
      <div className="flex items-center gap-3">
        <Server className="w-5 h-5 text-cp-purple-light" />
        <div>
          <h3 className="text-sm font-semibold text-cp-text">MCP Server (SSE)</h3>
          <p className="text-xs text-cp-muted">Claude Desktop / LLM 客户端远程连接</p>
        </div>
        <div className="flex-1" />
        <span className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-full ${
          status === 'online' ? 'bg-cp-green/15 text-cp-green' :
          status === 'offline' ? 'bg-cp-rose/15 text-cp-rose' : 'bg-cp-muted/15 text-cp-muted'
        }`}>
          <span className={`w-2 h-2 rounded-full ${status === 'online' ? 'bg-cp-green' : 'bg-cp-rose'}`} />
          {status === 'online' ? '运行中' : status === 'offline' ? '未启动' : '...'}
        </span>
      </div>
      <div className="flex items-center gap-2">
        {status === 'offline' ? (
          <button onClick={() => action('start')} disabled={busy} className="px-4 py-1.5 text-xs cp-btn-primary rounded">启动</button>
        ) : (
          <button onClick={() => action('stop')} disabled={busy} className="px-4 py-1.5 text-xs cp-btn-rose rounded">停止</button>
        )}
        <button onClick={check} className="px-3 py-1.5 text-xs border border-cp-border rounded text-cp-muted">刷新</button>
      </div>

      {/* Token list */}
      <div className="border-t border-cp-border pt-3">
        <h4 className="text-xs font-semibold text-cp-text mb-2">访问令牌（token→角色绑定）</h4>
        <div className="space-y-1 max-h-48 overflow-y-auto">
          {tokens.map((t: any) => (
            <div key={t.id} className="flex items-center gap-2 text-xs py-1 px-2 rounded cp-hover">
              <span className="text-cp-text font-mono">{t.sse_token}</span>
              <span className={`px-1 py-0.5 rounded text-xs ${
                t.agent_role === 'admin' ? 'bg-cp-purple/15 text-cp-purple-light' :
                t.agent_role === 'editor' ? 'bg-cp-cyan/15 text-cp-cyan' : 'bg-cp-muted/15 text-cp-muted'
              }`}>{t.agent_role}</span>
              <span className="text-cp-dim">{t.name}</span>
              {!t.is_active && <span className="text-cp-rose text-xs">已禁用</span>}
              <div className="flex-1" />
              <button onClick={async () => {
                  const r = await fetch(`/api/v2/settings/mcp/tokens/${t.id}/reveal`, { headers: auth() });
                  const d = await r.json();
                  if (d.url) doCopy(d.url);
                }} className="text-cp-purple-light hover:text-cp-purple">复制</button>
              <button onClick={() => deleteToken(t.id)} className="text-cp-dim hover:text-cp-rose">删除</button>
            </div>
          ))}
        </div>
        {/* Create new */}
        <div className="flex items-center gap-2 mt-2">
          <input value={newTokenName} onChange={e => setNewTokenName(e.target.value)}
            placeholder="名称" className="cp-input text-xs px-2 py-1 rounded w-24" />
          <select value={newTokenRoleId} onChange={e => setNewTokenRoleId(Number(e.target.value) || '')}
            className="cp-input text-xs px-2 py-1 rounded flex-1">
            <option value="">选择角色</option>
            {roles.map((r: any) => (
              <option key={r.id} value={r.id}>{r.name} {r.is_system ? '(系统)' : ''} — {r.user_count}人</option>
            ))}
          </select>
          <button onClick={createToken} disabled={!newTokenName || !newTokenRoleId}
            className="px-3 py-1 text-xs cp-btn-primary rounded disabled:opacity-40">创建</button>
        </div>
      </div>
    </div>
  );
}
