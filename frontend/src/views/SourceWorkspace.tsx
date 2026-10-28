import { useEffect, useRef, useState } from 'react';
import { Database, RefreshCw } from 'lucide-react';
import { api, type Preview, type Source } from '../api';
import BusinessSourceManager from '../components/BusinessSourceManager';

export default function SourceWorkspace() {
  const [sources, setSources] = useState<Source[]>([]), [name, setName] = useState('PRODUCTS');
  const [offset, setOffset] = useState(0), [tick, setTick] = useState(0);
  const [preview, setPreview] = useState<Preview | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState('');
  const seq = useRef(0);
  useEffect(() => {
    const controller = new AbortController();
    api<{items: Source[]}>('/sources', {signal: controller.signal}).then(r => {
      if (!controller.signal.aborted) setSources(Array.isArray(r.items) ? r.items : []);
    }).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const request = ++seq.current, controller = new AbortController();
    setLoading(true); setError(''); setPreview(null);
    api<Preview>(`/sources/${name}/preview?offset=${offset}&limit=20`, {signal: controller.signal})
      .then(r => { if (seq.current === request && !controller.signal.aborted) {
        if (r.source !== name || !Array.isArray(r.rows) || !Array.isArray(r.columns)) throw new Error('源数据响应不匹配。');
        setPreview(r);
      } }).catch(e => { if (!controller.signal.aborted && seq.current === request) setError(e.message); })
      .finally(() => { if (!controller.signal.aborted && seq.current === request) setLoading(false); });
    return () => controller.abort();
  }, [name, offset, tick]);
  const current = sources.find(s => s.name === name);
  return <section className="page"><div className="page-heading"><div><div className="eyebrow">BUSINESS SOURCES / 02</div><h1>数据留在业务系统</h1><p>通过 FASTONTO 的 READ 授权直连 SH。白名单查询，无导入、无副本、无回写。</p></div><span className="tag">LIVE · 只读</span></div>
    <div className="source-layout"><aside className="panel resource-tree"><div className="panel-title"><Database size={16}/><h2>SH 数据源</h2></div><p className="caption">配置清单；连接状态以实际查询为准。</p>{sources.map(s => <button key={s.name} className={`tree-item ${name === s.name ? 'selected' : ''}`} onClick={() => {setName(s.name); setOffset(0);}}><Database size={15}/><span>{s.title}<small>{s.owner}.{s.name}</small></span></button>)}</aside>
      <section className="panel source-panel"><div className="panel-title"><h2>{current?.title ?? name}</h2><code>SH.{name}</code><button className="icon-button" aria-label="刷新源数据" onClick={() => setTick(t => t + 1)} disabled={loading}><RefreshCw size={16}/></button></div>
        {error && <div className="notice error" role="alert">{error}<button onClick={() => setTick(t => t + 1)}>重试</button></div>}
        {loading ? <div className="empty" role="status">正在读取业务源…</div> : preview ? <><div className="table-scroll" tabIndex={0} aria-label="只读源数据表"><table><thead><tr>{preview.columns.map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{preview.rows.map((row, i) => <tr key={i}>{row.map((value, j) => <td key={j}>{value === null ? <span className="muted">NULL</span> : String(value)}</td>)}</tr>)}</tbody></table>{preview.rows.length === 0 && <div className="empty">当前范围没有记录。</div>}</div><div className="pagination"><span>偏移 {offset} · 当前 {preview.rows.length} 条</span><div className="actions"><button disabled={offset === 0} onClick={() => setOffset(o => Math.max(0, o - 20))}>上一页</button><button disabled={!preview.has_more || offset >= 10000} onClick={() => setOffset(o => o + 20)}>下一页</button></div></div></> : null}
        <div className="notice subtle">身份策略：{current?.identity ?? '—'}。{preview?.notice ?? '不把 ROWID 或行号当作永久实体 URI。'}</div>
      </section></div>
    <BusinessSourceManager/>
  </section>;
}
