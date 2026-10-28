import { useState, type FormEvent } from 'react';
import { api, type AuthSession } from '../api';

export default function PasswordForm({ onComplete, forced = false }: {onComplete: (session: AuthSession) => void; forced?: boolean}) {
  const [current, setCurrent] = useState(''), [next, setNext] = useState(''), [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function submit(e: FormEvent) {
    e.preventDefault(); if (busy) return;
    setError('');
    if (next !== confirm) {setError('两次输入的新密码不一致。'); return;}
    setBusy(true);
    try {
      const session = await api<AuthSession>('/auth/password', {method: 'POST', body: JSON.stringify({current_password: current, new_password: next})});
      setCurrent(''); setNext(''); setConfirm(''); onComplete(session);
    } catch (e) {setError(e instanceof Error ? e.message : '修改失败');}
    finally {setBusy(false);}
  }
  return <form className="auth-form" onSubmit={e => void submit(e)}>
    <h2>{forced ? '首次登录，请修改临时密码' : '修改登录密码'}</h2>
    <p>新密码至少 15 个字符。修改成功后其他会话立即失效，本次会话会重新签发。</p>
    <label htmlFor="current-password">{forced ? '临时密码' : '当前密码'}</label><input id="current-password" type="password" autoComplete="current-password" required maxLength={1024} value={current} onChange={e => setCurrent(e.target.value)} disabled={busy}/>
    <label htmlFor="new-password">新密码</label><input id="new-password" type="password" autoComplete="new-password" required minLength={15} maxLength={128} value={next} onChange={e => setNext(e.target.value)} disabled={busy}/>
    <label htmlFor="confirm-password">确认新密码</label><input id="confirm-password" type="password" autoComplete="new-password" required minLength={15} maxLength={128} value={confirm} onChange={e => setConfirm(e.target.value)} disabled={busy}/>
    {error && <div className="notice error" role="alert">{error}</div>}
    <button className="primary" type="submit" disabled={busy}>{busy ? '修改中…' : '确认修改密码'}</button>
  </form>;
}
