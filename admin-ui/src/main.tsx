import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  CheckCircle2,
  Clipboard,
  Eye,
  EyeOff,
  Gauge,
  KeyRound,
  LayoutDashboard,
  LockKeyhole,
  LogOut,
  PlugZap,
  RefreshCw,
  Save,
  Server,
  Settings,
  Shield,
  Trash2,
  WandSparkles,
} from 'lucide-react';
import * as api from './api';
import type { AdminConfig, Health } from './api';
import './style.css';

type Page = 'dashboard' | 'access' | 'upstream' | 'settings' | 'security';

const emptyConfig: AdminConfig = {
  settings: { upstream_base_url: '', model: 'gpt-5.5', force_model: false },
  api_keys: { count: 0, masked: [] },
  proxy_api_keys: { count: 0, values: [], masked: [], enabled: false },
  admin: { username: 'admin', using_default_password: true },
  service: { port: 9996, env_file: '' },
};

function maskKey(key: string) {
  if (!key) return '';
  if (key.length <= 14) return key;
  return `${key.slice(0, 10)}...${key.slice(-6)}`;
}

function Login({ onLogin }: { onLogin: () => Promise<void> }) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    try {
      await api.login(username, password);
      await onLogin();
    } catch (err: any) {
      setError(err.message || '登录失败');
    }
  }

  return <div className="login-page">
    <form className="login-card" onSubmit={submit}>
      <div className="brand-block">
        <Shield size={40} />
        <div>
          <h1>Codex AnyRouter</h1>
          <p>管理本地 Responses 代理、上游 Key 与第三方接入凭据</p>
        </div>
      </div>
      <label>用户名<input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" /></label>
      <label>密码<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" /></label>
      {error && <div className="alert error">{error}</div>}
      <button className="primary full"><LockKeyhole size={17} />登录</button>
    </form>
  </div>;
}

function App() {
  const [authed, setAuthed] = useState(Boolean(api.getToken()));
  const [config, setConfig] = useState<AdminConfig>(emptyConfig);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(Boolean(api.getToken()));

  async function load() {
    setLoading(true);
    try {
      const [configData, healthData] = await Promise.all([
        api.getConfig(),
        api.getHealth().catch(() => null),
      ]);
      setConfig(configData);
      setHealth(healthData);
      setAuthed(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!api.getToken()) return;
    load().catch(() => {
      api.clearToken();
      setAuthed(false);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="loading">加载中...</div>;
  if (!authed) return <Login onLogin={load} />;
  return <Layout config={config} health={health} setConfig={setConfig} refresh={load} logout={() => { api.clearToken(); setAuthed(false); }} />;
}

function Layout({
  config,
  health,
  setConfig,
  refresh,
  logout,
}: {
  config: AdminConfig;
  health: Health | null;
  setConfig: (config: AdminConfig) => void;
  refresh: () => Promise<void>;
  logout: () => void;
}) {
  const [page, setPage] = useState<Page>('dashboard');
  const [toast, setToast] = useState('');

  async function reload() {
    const result = await api.reloadConfig();
    setConfig(result.config);
    setToast('配置已从 .env 重载');
  }

  const nav = [
    ['dashboard', LayoutDashboard, '仪表盘'],
    ['access', PlugZap, '第三方接入'],
    ['upstream', KeyRound, '上游 Key'],
    ['settings', Settings, '运行配置'],
    ['security', LockKeyhole, '账号安全'],
  ] as const;

  return <div className="app-shell">
    {toast && <button className="toast" onClick={() => setToast('')}>{toast}</button>}
    <aside>
      <div className="side-title"><Shield size={24} /><span>AnyRouter 管理</span></div>
      <nav>
        {nav.map(([id, Icon, label]) => <button key={id} className={page === id ? 'active' : ''} onClick={() => setPage(id)}>
          <Icon size={18} />{label}
        </button>)}
      </nav>
      <div className="side-user">
        <strong>{config.admin.username}</strong>
        <span>管理员</span>
        <button onClick={logout}><LogOut size={17} />退出登录</button>
      </div>
    </aside>
    <main>
      <div className="page-title">
        <div>
          <Activity size={24} />
          <div>
            <h1>{nav.find(item => item[0] === page)?.[2]}</h1>
            <p>Codex / CherryStudio / sub2api 兼容代理</p>
          </div>
        </div>
        <div className="table-actions">
          <button className="ghost" onClick={() => refresh().catch((err: any) => setToast(err.message))}><RefreshCw size={16} />刷新</button>
          <button className="primary" onClick={() => reload().catch((err: any) => setToast(err.message))}><Save size={16} />重载配置</button>
        </div>
      </div>

      {page === 'dashboard' && <Dashboard config={config} health={health} />}
      {page === 'access' && <AccessPage config={config} setConfig={setConfig} setToast={setToast} />}
      {page === 'upstream' && <UpstreamKeysPage config={config} setConfig={setConfig} setToast={setToast} />}
      {page === 'settings' && <SettingsPage config={config} setConfig={setConfig} setToast={setToast} />}
      {page === 'security' && <SecurityPage config={config} setToast={setToast} logout={logout} />}
    </main>
  </div>;
}

function Dashboard({ config, health }: { config: AdminConfig; health: Health | null }) {
  const clientBaseUrl = `${window.location.origin}/v1`;
  return <>
    <div className="cards">
      <Metric icon={<Gauge />} label="服务状态" value={health?.status === 'ok' ? '正常' : '未知'} tone="ok" />
      <Metric icon={<Server />} label="默认模型" value={config.settings.model || '-'} />
      <Metric icon={<KeyRound />} label="上游 Key" value={String(config.api_keys.count)} />
      <Metric icon={<Shield />} label="代理 Key" value={String(config.proxy_api_keys.count)} />
    </div>
    <div className="grid-two">
      <section className="panel">
        <div className="toolbar"><h2>代理信息</h2><span className="chip ok"><CheckCircle2 size={14} />{health?.api_key_source || 'admin/env'}</span></div>
        <InfoRow label="请求地址" value={clientBaseUrl} copy />
        <InfoRow label="上游地址" value={config.settings.upstream_base_url} />
        <InfoRow label="服务端口" value={String(config.service.port)} />
        <InfoRow label="环境文件" value={config.service.env_file || '-'} />
      </section>
      <section className="panel">
        <div className="toolbar"><h2>Codex 配置片段</h2><CopyButton value={`base_url = "${clientBaseUrl}"`} /></div>
        <pre>{`model_provider = "custom"
model = "${config.settings.model || 'gpt-5.5'}"
model_reasoning_effort = "medium"

[model_providers.custom]
name = "custom"
wire_api = "responses"
requires_openai_auth = true
base_url = "${clientBaseUrl}"`}</pre>
      </section>
    </div>
  </>;
}

function Metric({ icon, label, value, tone = '' }: { icon: React.ReactNode; label: string; value: string; tone?: string }) {
  return <div className={`card ${tone}`}>
    <span>{icon}{label}</span>
    <strong>{value}</strong>
  </div>;
}

function AccessPage({ config, setConfig, setToast }: PageProps) {
  const [newKey, setNewKey] = useState('');
  const [showKeys, setShowKeys] = useState(false);
  const clientBaseUrl = `${window.location.origin}/v1`;

  async function generate() {
    const result = await api.generateProxyKey();
    setConfig(result.config);
    setToast(`代理 Key 已生成：${result.key}`);
  }

  async function add() {
    const key = newKey.trim();
    if (!key) {
      setToast('请输入代理 API Key');
      return;
    }
    const result = await api.addProxyKey(key);
    setConfig(result.config);
    setNewKey('');
    setToast('代理 Key 已添加');
  }

  async function remove(index: number) {
    if (!window.confirm(`确认删除第 ${index + 1} 个代理 Key？`)) return;
    const result = await api.deleteProxyKey(index);
    setConfig(result.config);
    setToast('代理 Key 已删除');
  }

  return <div className="grid-two">
    <section className="panel">
      <div className="toolbar"><h2>客户端连接</h2><span className="chip">OpenAI 兼容</span></div>
      <InfoRow label="API 地址" value={clientBaseUrl} copy />
      <InfoRow label="模型名" value={config.settings.model || 'gpt-5.5'} copy />
      <InfoRow label="Chat 接口" value={`${clientBaseUrl}/chat/completions`} />
      <InfoRow label="Responses 接口" value={`${clientBaseUrl}/responses`} />
    </section>
    <section className="panel">
      <div className="toolbar">
        <h2>对外代理 API Key</h2>
        <div className="table-actions">
          <button className="ghost" onClick={() => setShowKeys(!showKeys)}>{showKeys ? <EyeOff size={16} /> : <Eye size={16} />}{showKeys ? '隐藏' : '显示'}</button>
          <button className="primary" onClick={() => generate().catch((err: any) => setToast(err.message))}><WandSparkles size={16} />生成</button>
        </div>
      </div>
      <KeyList keys={showKeys ? config.proxy_api_keys.values : config.proxy_api_keys.masked} onDelete={remove} copyValues={config.proxy_api_keys.values} emptyText="暂无代理 Key。未配置时第三方客户端不能使用独立代理 Key 鉴权。" />
      <div className="inline-form">
        <label>添加自定义代理 Key<input value={newKey} onChange={e => setNewKey(e.target.value)} placeholder="sk-proxy-..." autoComplete="off" /></label>
        <button className="primary" onClick={() => add().catch((err: any) => setToast(err.message))}>添加</button>
      </div>
    </section>
  </div>;
}

type PageProps = {
  config: AdminConfig;
  setConfig: (config: AdminConfig) => void;
  setToast: (value: string) => void;
};

function UpstreamKeysPage({ config, setConfig, setToast }: PageProps) {
  const [newKey, setNewKey] = useState('');
  const [bulkKeys, setBulkKeys] = useState('');

  async function add() {
    const key = newKey.trim();
    if (!key) {
      setToast('请输入 AnyRouter 上游 API Key');
      return;
    }
    const result = await api.addUpstreamKey(key);
    setConfig(result.config);
    setNewKey('');
    setToast('上游 Key 已添加');
  }

  async function replace() {
    const keys = bulkKeys.split(/\n|,/).map(key => key.trim()).filter(Boolean);
    const result = await api.replaceUpstreamKeys(keys);
    setConfig(result.config);
    setBulkKeys('');
    setToast('上游 Key 列表已替换');
  }

  async function remove(index: number) {
    if (!window.confirm(`确认删除第 ${index + 1} 个上游 Key？`)) return;
    const result = await api.deleteUpstreamKey(index);
    setConfig(result.config);
    setToast('上游 Key 已删除');
  }

  return <div className="grid-two">
    <section className="panel">
      <div className="toolbar"><h2>AnyRouter 上游 Key</h2><span className="chip">{config.api_keys.count} 个</span></div>
      <KeyList keys={config.api_keys.masked} onDelete={remove} emptyText="暂无服务端上游 Key。配置代理 Key 后必须至少添加一个上游 Key。" />
      <div className="inline-form">
        <label>添加单个 Key<input value={newKey} onChange={e => setNewKey(e.target.value)} placeholder="sk-..." autoComplete="off" /></label>
        <button className="primary" onClick={() => add().catch((err: any) => setToast(err.message))}>添加</button>
      </div>
    </section>
    <section className="panel">
      <h2>批量替换</h2>
      <label>Key 列表<textarea value={bulkKeys} onChange={e => setBulkKeys(e.target.value)} placeholder="每行一个 Key，也可以用英文逗号分隔" /></label>
      <div className="table-actions">
        <button className="primary" onClick={() => replace().catch((err: any) => setToast(err.message))}><Save size={16} />替换列表</button>
      </div>
    </section>
  </div>;
}

function SettingsPage({ config, setConfig, setToast }: PageProps) {
  const [upstreamBaseUrl, setUpstreamBaseUrl] = useState(config.settings.upstream_base_url);
  const [model, setModel] = useState(config.settings.model);
  const [forceModel, setForceModel] = useState(config.settings.force_model);

  useEffect(() => {
    setUpstreamBaseUrl(config.settings.upstream_base_url);
    setModel(config.settings.model);
    setForceModel(config.settings.force_model);
  }, [config]);

  async function save() {
    const result = await api.updateSettings({ upstream_base_url: upstreamBaseUrl, model, force_model: forceModel });
    setConfig(result.config);
    setToast('运行配置已保存');
  }

  return <section className="panel narrow">
    <h2>运行配置</h2>
    <div className="form-grid">
      <label>AnyRouter OpenAI 兼容地址<input value={upstreamBaseUrl} onChange={e => setUpstreamBaseUrl(e.target.value)} placeholder="https://anyrouter.top/v1" /></label>
      <label>默认模型<input value={model} onChange={e => setModel(e.target.value)} placeholder="gpt-5.5" /></label>
    </div>
    <label className="check"><input type="checkbox" checked={forceModel} onChange={e => setForceModel(e.target.checked)} />强制所有请求使用默认模型</label>
    <button className="primary" onClick={() => save().catch((err: any) => setToast(err.message))}><Save size={16} />保存配置</button>
  </section>;
}

function SecurityPage({ config, setToast, logout }: { config: AdminConfig; setToast: (value: string) => void; logout: () => void }) {
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');

  async function save() {
    if (newPassword.length < 8) {
      setToast('新密码至少需要 8 个字符');
      return;
    }
    await api.changePassword(oldPassword, newPassword);
    setToast('密码已修改，请重新登录');
    window.setTimeout(logout, 700);
  }

  return <section className="panel narrow">
    <div className="toolbar"><h2>管理员密码</h2>{config.admin.using_default_password && <span className="chip warn">默认密码</span>}</div>
    <div className="form-grid">
      <label>当前密码<input type="password" value={oldPassword} onChange={e => setOldPassword(e.target.value)} autoComplete="current-password" /></label>
      <label>新密码<input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} autoComplete="new-password" /></label>
    </div>
    <button className="primary" onClick={() => save().catch((err: any) => setToast(err.message))}><LockKeyhole size={16} />修改密码</button>
  </section>;
}

function InfoRow({ label, value, copy = false }: { label: string; value: string; copy?: boolean }) {
  return <div className="info-row">
    <span>{label}</span>
    <code>{value}</code>
    {copy && <CopyButton value={value} />}
  </div>;
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1100);
  }
  return <button className="icon-button" onClick={() => copy().catch(() => undefined)} title="复制"><Clipboard size={16} />{copied ? '已复制' : '复制'}</button>;
}

function KeyList({
  keys,
  onDelete,
  copyValues,
  emptyText,
}: {
  keys: string[];
  onDelete: (index: number) => Promise<void>;
  copyValues?: string[];
  emptyText: string;
}) {
  if (!keys.length) return <div className="empty">{emptyText}</div>;
  return <div className="key-list">
    {keys.map((key, index) => <div className="key-item" key={`${key}-${index}`}>
      <code>{key || maskKey(copyValues?.[index] || '')}</code>
      <div className="table-actions">
        {copyValues?.[index] && <CopyButton value={copyValues[index]} />}
        <button className="ghost danger" onClick={() => onDelete(index)}><Trash2 size={15} />删除</button>
      </div>
    </div>)}
  </div>;
}

createRoot(document.getElementById('root')!).render(<App />);
