import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { ArrowUpRight, Database, FolderTree, Layers3, Moon, Settings2, ShieldCheck, Sun } from 'lucide-react';
import { api, type Health, type AuthSession } from './api';
import PasswordForm from './components/PasswordForm';
import Dialog from './components/Dialog';
import { useWorkspace } from './useWorkspace';
import ModelWorkspace from './views/ModelWorkspace';
import SourceWorkspace from './views/SourceWorkspace';
import GovernanceWorkspace from './views/GovernanceWorkspace';

const nav = [{path: '/models', label: '模型工作台', icon: Layers3}, {path: '/governance', label: '业务域治理', icon: FolderTree}, {path: '/sources', label: '业务数据源', icon: Database}, {path: '/system', label: '连接与边界', icon: Settings2}, {path: '/account', label: '账户安全', icon: ShieldCheck}];

function SystemView() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  async function check(path = '/database/status') {setBusy(true); setError(''); setStatus(null); try {setStatus(await api(path));} catch(e) {setError(e instanceof Error ? e.message : '检查失败');} finally {setBusy(false);} }
  return <section className="page"><div className="page-heading"><div><div className="eyebrow">SYSTEM / 03</div><h1>连接与运行边界</h1><p>所有业务接口均需登录；HTTP 仅用于临时测试，正式访问请启用 HTTPS。</p></div></div><div className="panel system-panel"><h2>Oracle 应用连接</h2><p>后端仅使用 FASTONTO。请在项目根目录的本机 <code>.env</code> 配置凭据；不会读取 SQLcl 保存密码。</p><button className="primary" disabled={busy} onClick={() => void check()}>{busy ? '检查中…' : '检查数据库连接'}</button> <button disabled={busy} onClick={() => void check('/graph/products')}>验证产品虚拟 RDF</button>{error && <div className="notice error" role="alert">{error}</div>}{status && <pre className="system-result">{JSON.stringify(status, null, 2)}</pre>}<hr/><h2>此阶段已提供</h2><ul><li>LinkML 源码编辑、结构校验、生成产物与版本保存。</li><li>8 张 SH 核心业务表的白名单只读预览。</li><li>客户、产品的 R2RML 虚拟映射迁移与 SQL/SPARQL 验证脚本。</li></ul><h2>明确未提供</h2><ul><li>业务源写入、实例导入、任意 SQL/SPARQL 执行。</li><li>审批发布、自动迁移业务数据、完整 OWL 编辑、SSO/MFA 和多租户隔离。</li></ul><p className="caption">端口 8025 / 8026 · Conda fastonto · 迁移必须显式执行，应用启动不自动建表。</p></div></section>;
}

function AccountView({session,onUpdate}: {session: AuthSession; onUpdate: (value: AuthSession) => void}) {
  const [message,setMessage] = useState('');
  return <section className="page"><div className="page-heading"><div><div className="eyebrow">ACCOUNT SECURITY / 04</div><h1>账户安全</h1><p>当前用户：{session.user.username}。密码只保存为 Argon2id 哈希。</p></div></div><div className="panel system-panel">{message && <div role="status" className="notice">{message}</div>}<PasswordForm onComplete={value => {onUpdate(value); setMessage('密码已修改，其他会话已失效。');}}/></div></section>;
}

export default function App({session,onSessionUpdate,onLogout}: {session: AuthSession; onSessionUpdate: (value: AuthSession) => void; onLogout: () => Promise<void>}) {
  const work = useWorkspace();
  const location = useLocation();
  const [theme, setTheme] = useState(document.documentElement.dataset.theme === 'light' ? 'light' : 'dark');
  const [health, setHealth] = useState<Health | null>(null), [healthError, setHealthError] = useState('');
  const [confirmLogout,setConfirmLogout] = useState(false), [logoutBusy,setLogoutBusy] = useState(false), [logoutError,setLogoutError] = useState('');
  async function logout() {setConfirmLogout(false); setLogoutBusy(true); setLogoutError(''); try {await onLogout();} catch(e) {setLogoutError(e instanceof Error ? e.message : '退出失败');} finally {setLogoutBusy(false);}}
  useEffect(() => {document.documentElement.dataset.theme = theme; try {localStorage.setItem('fastonto.theme.v1', theme);} catch {}}, [theme]);
  useEffect(() => { const controller = new AbortController(); api<Health>('/system', {signal: controller.signal}).then(setHealth).catch(e => {if (!controller.signal.aborted) setHealthError(e.message);}); return () => controller.abort(); }, []);
  return <div className="app-shell"><aside className="app-sidebar"><NavLink className="brand" to="/models"><span className="brand-icon"><Layers3 size={23}/></span><span>fastOnto<small>ONTOLOGY WORKSPACE</small></span></NavLink><div className="nav-label">工作空间</div><nav aria-label="主导航">{nav.map(n => <NavLink key={n.path} to={n.path} className={({isActive}) => `nav-item ${isActive ? 'active' : ''}`}><n.icon size={18}/>{n.label}<ArrowUpRight size={14} className="nav-arrow"/></NavLink>)}</nav><div className="sidebar-bottom"><ShieldCheck size={19}/><strong>语义连接，不搬运数据</strong><p>LinkML × Oracle RDF<br/>SH 始终保持只读</p><span className="tag">AUTHENTICATED WORKSPACE</span></div></aside>
    <div className="app-main"><header className="topbar"><span className="breadcrumb">工作空间 <span>/</span> 通用本体建模</span><div className="actions"><NavLink className="account-name" to="/account">{session.user.username}</NavLink><button disabled={logoutBusy} onClick={() => {if (work.dirty || work.importDirty) setConfirmLogout(true); else void logout();}}>{logoutBusy ? '退出中…' : '退出'}</button><span className="connection-state"><span className={`dot ${health ? '' : 'warning'}`}/>{health ? 'API 已连接' : 'API 未连接'}</span><button className="icon-button" aria-label={theme === 'dark' ? '切换浅色主题' : '切换深色主题'} onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={18}/> : <Moon size={18}/>}</button></div></header>
      {session.insecure_http && <div className="setup-banner">HTTP 测试环境：登录密码与会话传输未加密，请勿复用密码；建议限制来源 IP 并尽快启用 HTTPS。</div>}
      {(healthError || (health && !health.database_configured)) && <div className="setup-banner">{healthError ? `后端不可用：${healthError}` : 'Python 数据库连接尚未配置。模型校验与导出可用；保存与业务查询需填写本机 .env 后重启后端。'}</div>}
      {logoutError && <div className="notice error" role="alert">{logoutError}</div>}
      <div hidden={location.pathname !== '/models'}><ModelWorkspace work={work} active={location.pathname === '/models'}/></div>
      <Routes><Route path="/models" element={null}/><Route path="/governance" element={<GovernanceWorkspace/>}/><Route path="/sources" element={<SourceWorkspace/>}/><Route path="/system" element={<SystemView/>}/><Route path="/account" element={<AccountView session={session} onUpdate={onSessionUpdate}/>}/><Route path="*" element={<Navigate to="/models" replace/>}/></Routes>
      <Dialog open={confirmLogout} title="退出并放弃未保存草稿？" message="退出登录会清除当前页面中的未保存草稿。可先取消并导出 YAML。" confirmLabel="放弃草稿并退出" onCancel={() => setConfirmLogout(false)} onConfirm={() => void logout()}/>
      <footer>fastOnto <span>模型主源 · 显式映射 · 只读业务连接</span></footer>
    </div></div>;
}
