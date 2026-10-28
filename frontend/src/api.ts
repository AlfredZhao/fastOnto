export interface Field { name: string; title: string; range: string; required: boolean; multivalued: boolean; identifier: boolean }
export interface ModelClass { name: string; title: string; description: string; uri: string; slots: Field[] }
export interface Report { valid: boolean; name: string; title: string; sha256: string; classes: ModelClass[]; relationships: {source: string; target: string; label: string; kind: string}[]; enum_count: number; warnings: string[] }
export interface Saved { id: string; title: string; revision: number }
export interface Source { name: string; title: string; owner: string; columns: string[]; identity: string }
export interface Preview { source: string; columns: string[]; rows: (string | number | null)[][]; offset: number; limit: number; has_more: boolean; notice: string }
export interface Health { database_configured: boolean; mode: string; version: string; insecure_http?: boolean }
export interface AuthSession { user: { id: string; username: string; must_change_password: boolean }; csrf_token: string; insecure_http: boolean }
let csrfToken = '';
let sessionEpoch = 0;
export function setAuthSession(session: AuthSession | null) { csrfToken = session?.csrf_token ?? ''; sessionEpoch += 1; }
export class ApiError extends Error { constructor(message: string, public status: number, public code: string) { super(message); } }
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const epoch = sessionEpoch;
  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  if (csrfToken && !['GET', 'HEAD'].includes((options.method ?? 'GET').toUpperCase())) headers.set('X-CSRF-Token', csrfToken);
  const response = await fetch(`/api${path}`, { ...options, cache: 'no-store', credentials: 'same-origin', headers });
  const data = await response.json().catch(() => null);
  if (epoch !== sessionEpoch) throw new ApiError('会话已变化，忽略旧请求。', 0, 'stale_session');
  if (!response.ok) {
    const message = typeof data?.detail === 'string' ? data.detail : data?.detail?.message ?? `请求失败 (${response.status})`;
    const code = data?.code ?? data?.detail?.code ?? 'request_failed';
    if ((response.status === 401 && code === 'unauthenticated' && path !== '/auth/me') || code === 'password_change_required') window.dispatchEvent(new Event('fastonto-session-expired'));
    throw new ApiError(message, response.status, code);
  }
  if (data == null || typeof data !== 'object') throw new Error('接口返回了无法识别的数据。');
  return data as T;
}
export function download(content: string, filename: string, type = 'text/plain;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
