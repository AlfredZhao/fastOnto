import { useEffect, useState, type FormEvent } from 'react';
import { Layers3, LockKeyhole, Moon, Sun } from 'lucide-react';
import { api, ApiError, setAuthSession, type AuthSession } from '../api';
import App from '../App';
import PasswordForm from './PasswordForm';


export default function AuthGate() {
  const [session, setSession] = useState<AuthSession | null>(null), [loading, setLoading] = useState(true);
  const [error, setError] = useState(''), [username, setUsername] = useState('admin'), [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false), [retry, setRetry] = useState(0);
  const [theme, setTheme] = useState(document.documentElement.dataset.theme === 'light' ? 'light' : 'dark');
  function accept(value: AuthSession) {setAuthSession(value); setSession(value); setError('');}
  useEffect(() => {
    const controller = new AbortController(); setLoading(true);
    api<AuthSession>('/auth/me', {signal: controller.signal}).then(r => {if (!controller.signal.aborted) accept(r);})
      .catch(e => {if (!controller.signal.aborted && !(e instanceof ApiError && e.status === 401)) setError(e.message);})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [retry]);
  useEffect(() => {
    const expired = () => {setAuthSession(null); setSession(null); setPassword(''); setError('会话已失效，请重新登录。');};
    window.addEventListener('fastonto-session-expired', expired);
    return () => window.removeEventListener('fastonto-session-expired', expired);
  }, []);
  async function login(e: FormEvent) {
    e.preventDefault(); if (busy) return;
    setBusy(true); setError('');
    try {accept(await api<AuthSession>('/auth/login', {method: 'POST', body: JSON.stringify({username, password})})); setPassword('');}
    catch(e) {setError(e instanceof Error ? e.message : '登录失败'); setPassword('');}
    finally {setBusy(false);}
  }
  async function logout() {
    try {await api('/auth/logout', {method: 'POST', body: '{}'}); setAuthSession(null); setSession(null); setPassword(''); setError('');}
    catch(e) {setError(e instanceof Error ? e.message : '退出失败，请重试'); throw e;}
  }
  function toggleTheme() {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next; setTheme(next);
    try {localStorage.setItem('fastonto.theme.v1', next);} catch {}
  }
  if (loading) return <div className="auth-shell"><div className="auth-card panel" role="status">正在检查登录状态…</div></div>;
  if (session && !session.user.must_change_password) return <App key={session.user.id} session={session} onSessionUpdate={accept} onLogout={logout}/>;
  return <main className="auth-shell"><section className="auth-card panel">
    <div className="auth-brand"><Layers3 size={30}/><strong>fastOnto</strong><button className="icon-button" aria-label={theme === 'dark' ? '切换浅色主题' : '切换深色主题'} onClick={toggleTheme}>{theme === 'dark' ? <Sun size={18}/> : <Moon size={18}/>}</button></div>
    <div className="eyebrow">ONTOLOGY WORKSPACE</div><h1>{session ? '设置你的登录密码' : '登录本体工作台'}</h1>
    <p>模型与业务数据仅在登录后可访问。</p>
    {session ? <><PasswordForm forced onComplete={accept}/><button className="auth-logout" onClick={() => void logout().catch(() => {})}>退出登录</button></> : <form className="auth-form" onSubmit={e => void login(e)}>
      <label htmlFor="login-username">用户名</label><input id="login-username" autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required minLength={3} maxLength={64} disabled={busy}/>
      <label htmlFor="login-password">密码</label><input id="login-password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required maxLength={1024} disabled={busy}/>
      <button className="primary" type="submit" disabled={busy}><LockKeyhole size={16}/>{busy ? '登录中…' : '登录'}</button>
    </form>}
    {error && <div className="notice error" role="alert">{error}</div>}
    {!session && <button className="auth-retry" onClick={() => setRetry(t => t + 1)} disabled={busy}>重新检查连接</button>}
    <div className="caption">无公开注册入口 · 首次登录强制改密 · SH 只读连接</div>
  </section></main>;
}
