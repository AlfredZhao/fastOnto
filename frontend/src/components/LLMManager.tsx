import { FormEvent, useEffect, useState } from 'react';
import { Bot, Plus, PlugZap, Star } from 'lucide-react';
import { api } from '../api';

type LLMModel = {id: string; code: string; title: string; base_url: string; model_name: string; enabled: boolean; is_default: boolean};
function technical(value: string) { return value.trim().replace(/[^A-Za-z0-9_]/g, '_').replace(/^([^A-Za-z_])/, '_$1').slice(0, 80); }

export default function LLMManager() {
  const [items, setItems] = useState<LLMModel[]>([]), [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const [title, setTitle] = useState(''), [code, setCode] = useState(''), [baseUrl, setBaseUrl] = useState(''), [modelName, setModelName] = useState(''), [apiKey, setApiKey] = useState(''), [makeDefault, setMakeDefault] = useState(true);
  async function refresh() { const result = await api<{items: LLMModel[]}>('/llm-models'); setItems(result.items); }
  useEffect(() => { void refresh().catch(e => setError(e instanceof Error ? e.message : '无法读取 LLM 配置。')); }, []);
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('');
    try { await api('/llm-models', {method: 'POST', body: JSON.stringify({code, title, base_url: baseUrl, model_name: modelName, api_key: apiKey, make_default: makeDefault})}); await refresh(); setTitle(''); setCode(''); setBaseUrl(''); setModelName(''); setApiKey(''); setMessage('LLM 已加密保存。API Key 不会再次显示。'); }
    catch (e) { setError(e instanceof Error ? e.message : '保存 LLM 失败。'); } finally { setBusy(false); }
  }
  async function test(item: LLMModel) { setBusy(true); setError(''); setMessage(''); try { const result = await api<{notice: string; sample: string}>(`/llm-models/${encodeURIComponent(item.id)}/test`, {method: 'POST'}); setMessage(`${item.title}：${result.notice} 返回：${result.sample}`); } catch (e) { setError(e instanceof Error ? e.message : '连通性测试失败。'); } finally { setBusy(false); } }
  async function setDefault(item: LLMModel) { setBusy(true); setError(''); try { await api(`/llm-models/${encodeURIComponent(item.id)}/default`, {method: 'PUT'}); await refresh(); setMessage(`已将“${item.title}”设为默认 LLM。`); } catch (e) { setError(e instanceof Error ? e.message : '设置默认模型失败。'); } finally { setBusy(false); } }
  return <section className="page" aria-label="LLM 配置"><div className="page-heading"><div><div className="eyebrow">LLM CONFIGURATION / 05</div><h1>LLM 模型配置</h1><p>配置兼容 OpenAI Chat Completions 的模型服务，用于文档辅助提取 LinkML 候选。API Key 仅以 AES-256-GCM 密文保存。</p></div><span className="tag">OPENAI COMPATIBLE</span></div>
    {error && <div className="notice error" role="alert">{error}</div>}{message && <div className="notice" role="status">{message}</div>}
    <div className="governance-grid"><section className="panel"><div className="panel-title"><Plus size={16}/><h2>新增 LLM</h2></div><form className="governance-form" onSubmit={save}>
      <label>显示名称<input required maxLength={200} value={title} onChange={event => {setTitle(event.target.value); if (!code) setCode(technical(event.target.value));}} placeholder="例如：企业知识模型"/></label>
      <label>技术标识<input required maxLength={80} value={code} onChange={event => setCode(technical(event.target.value))}/></label>
      <label>服务基础地址<input required maxLength={1000} value={baseUrl} onChange={event => setBaseUrl(event.target.value)} placeholder="http://llm.example.com/v1 或 https://api.example.com/v1"/></label>
      <label>模型标识<input required maxLength={200} value={modelName} onChange={event => setModelName(event.target.value)} placeholder="例如：gpt-4.1-mini"/></label>
      <label>API Key<input required type="password" autoComplete="new-password" maxLength={1000} value={apiKey} onChange={event => setApiKey(event.target.value)}/></label>
      <label><input type="checkbox" checked={makeDefault} onChange={event => setMakeDefault(event.target.checked)}/> 设为默认文档分析模型</label>
      <button className="primary" disabled={busy}><Plus size={15}/>{busy ? '保存中…' : '加密保存模型'}</button>
    </form></section>
      <section className="panel"><div className="panel-title"><Bot size={16}/><h2>已配置模型</h2><span className="count">{items.length}</span></div><div className="governance-list">{!items.length && <div className="empty compact">尚未配置 LLM。新增并测试一个 HTTPS 模型后，可在文件导入时选择它。</div>}{items.map(item => <article className="governance-card" key={item.id}><strong><Bot size={15}/>{item.title}</strong><code>{item.code} · {item.model_name}</code><small>{item.base_url}</small><div className="actions">{item.is_default ? <span className="tag">默认模型</span> : <button disabled={busy || !item.enabled} onClick={() => void setDefault(item)}><Star size={14}/>设为默认</button>}<button disabled={busy || !item.enabled} onClick={() => void test(item)}><PlugZap size={14}/>测试连通性</button></div></article>)}</div></section>
    </div></section>;
}
