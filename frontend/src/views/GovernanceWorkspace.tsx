import { FormEvent, useEffect, useState } from 'react';
import { FolderTree, Network, Plus, Waypoints } from 'lucide-react';
import { api, type Saved } from '../api';
import MappingEditor from '../components/MappingEditor';
import EntityLinkEditor from '../components/EntityLinkEditor';
import SemanticAssetEditor from '../components/SemanticAssetEditor';
import ApplicationBlueprint from '../components/ApplicationBlueprint';

type Domain = {id: string; code: string; title: string; description?: string; lifecycle: string};
type Ontology = {id: string; domain_id: string; code: string; title: string; description?: string; lifecycle: string; model_id?: string | null; model_revision?: number | null};
type Mapping = {id: string; ontology_id: string; code: string; title: string; source_code?: string; source_id?: string | null; source_object_name?: string | null};
type EntityLink = {id: string; ontology_id: string};
type Asset = {id: string; ontology_id: string; asset_kind: 'RULE' | 'METRIC' | 'ACTION'; code: string; title: string; description?: string; lifecycle: string};
type Catalog = {domains: Domain[]; ontologies: Ontology[]; mappings: Mapping[]; entity_links: EntityLink[]; assets: Asset[]; notice: string};

const empty: Catalog = {domains: [], ontologies: [], mappings: [], entity_links: [], assets: [], notice: ''};
function list<T>(value: unknown): T[] { return Array.isArray(value) ? value as T[] : []; }
function normalizeCatalog(value: Partial<Catalog>): Catalog {
  // A freshly deployed frontend may briefly meet an older backend during a restart.
  // Missing newer collections must render as empty, not make the whole route unavailable.
  return {
    domains: list<Domain>(value.domains),
    ontologies: list<Ontology>(value.ontologies),
    mappings: list<Mapping>(value.mappings),
    entity_links: list<EntityLink>(value.entity_links),
    assets: list<Asset>(value.assets),
    notice: typeof value.notice === 'string' ? value.notice : '',
  };
}
function technical(value: string) { return value.trim().replace(/[^A-Za-z0-9_]/g, '_').replace(/^([^A-Za-z_])/, '_$1').slice(0, 80); }

export default function GovernanceWorkspace() {
  const [catalog, setCatalog] = useState<Catalog>(empty), [domainId, setDomainId] = useState('');
  const [title, setTitle] = useState(''), [code, setCode] = useState(''), [kind, setKind] = useState<'domain'|'ontology'>('domain');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const [models, setModels] = useState<Saved[]>([]), [modelChoice, setModelChoice] = useState<Record<string, string>>({});
  async function refresh() { setCatalog(normalizeCatalog(await api<Partial<Catalog>>('/governance/catalog'))); }
  useEffect(() => { void refresh().catch(e => setError(e instanceof Error ? e.message : '无法读取治理目录。')); void api<{items: Saved[]}>('/models').then(r => setModels(r.items)).catch(() => setModels([])); }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setMessage('');
    try {
      if (kind === 'domain') await api('/governance/domains', {method: 'POST', body: JSON.stringify({code, title})});
      else await api('/governance/ontologies', {method: 'POST', body: JSON.stringify({domain_id: domainId, code, title})});
      await refresh(); setTitle(''); setCode(''); setMessage('已创建草稿；所有资产默认未发布。');
    } catch (e) { setError(e instanceof Error ? e.message : '创建失败。'); } finally { setBusy(false); }
  }
  async function attach(ontology: Ontology) {
    const choice = modelChoice[ontology.id]; const model = models.find(item => item.id === choice); if (!model) return;
    setBusy(true); setError('');
    try { await api(`/governance/ontologies/${encodeURIComponent(ontology.id)}/model`, {method: 'PUT', body: JSON.stringify({model_id: model.id, model_revision: model.revision})}); await refresh(); setMessage('已关联 LinkML 模型版本。'); }
    catch (e) { setError(e instanceof Error ? e.message : '关联失败。'); } finally { setBusy(false); }
  }
  return <section className="page" aria-label="业务域治理">
    <div className="page-heading"><div><div className="eyebrow">SEMANTIC GOVERNANCE / 02</div><h1>业务域与本体</h1><p>业务域是当前唯一顶层边界。本体、映射草稿和规则/指标/操作资产都归属业务域；业务数据仍留在只读源；一个业务域可配置多个外部源。</p></div><span className="tag">治理基础版</span></div>
    {error && <div className="notice error" role="alert">{error}</div>}{message && <div className="notice" role="status">{message}</div>}
    <div className="governance-grid">
      <section className="panel"><div className="panel-title"><Plus size={16}/><h2>创建业务资产</h2></div><form className="governance-form" onSubmit={submit}>
        <label>创建类型<select value={kind} onChange={e => setKind(e.target.value as typeof kind)}><option value="domain">业务域</option><option value="ontology">本体</option></select></label>
        {kind === 'ontology' && <label>业务域<select required value={domainId} onChange={e => setDomainId(e.target.value)}><option value="">请选择</option>{catalog.domains.filter(d => d.lifecycle === 'ACTIVE').map(d => <option key={d.id} value={d.id}>{d.title} ({d.code})</option>)}</select></label>}
        <label>名称<input required maxLength={200} value={title} onChange={e => {setTitle(e.target.value); if (!code) setCode(technical(e.target.value));}}/></label>
        <label>技术标识<input required maxLength={80} value={code} onChange={e => setCode(technical(e.target.value))}/></label>
        <button className="primary" disabled={busy || (kind === 'ontology' && !domainId)}>{busy ? '创建中…' : '创建草稿'}</button>
      </form></section>
      <section className="panel"><div className="panel-title"><FolderTree size={16}/><h2>业务域目录</h2><span className="count">{catalog.domains.length}</span></div><div className="governance-list">
        {!catalog.domains.length && <div className="empty compact">尚无业务域。请先创建例如“销售域”。</div>}
        {catalog.domains.map(d => <article key={d.id} className="governance-card"><strong><Waypoints size={15}/>{d.title}</strong><code>{d.code}</code><span className="tag">{d.lifecycle}</span>{catalog.ontologies.filter(o => o.domain_id === d.id).map(o => <div className="governance-ontology" key={o.id}><strong><Network size={14}/>{o.title}</strong><code>{o.code}</code><span className="tag">{o.lifecycle}</span>{o.model_id ? <><small>已关联 LinkML v{o.model_revision}</small><MappingEditor ontology={o} onSaved={refresh}/><EntityLinkEditor ontologyId={o.id} mappings={catalog.mappings.filter(m => m.ontology_id === o.id)} onSaved={refresh}/><SemanticAssetEditor ontologyId={o.id} assets={catalog.assets.filter(a => a.ontology_id === o.id)} onSaved={refresh}/><ApplicationBlueprint ontology={o} mappings={catalog.mappings.filter(m => m.ontology_id === o.id).length} entityLinks={catalog.entity_links.filter(link => link.ontology_id === o.id).length} assets={catalog.assets.filter(a => a.ontology_id === o.id).length}/></> : <div className="model-link"><select aria-label={`${o.title} 的 LinkML 模型`} value={modelChoice[o.id] ?? ''} onChange={e => setModelChoice({...modelChoice, [o.id]: e.target.value})}><option value="">关联已保存模型…</option>{models.map(m => <option key={m.id} value={m.id}>{m.title} · v{m.revision}</option>)}</select><button disabled={busy || !modelChoice[o.id]} onClick={() => void attach(o)}>关联</button></div>}<small>{catalog.mappings.filter(m => m.ontology_id === o.id).length} 个映射草稿 · {catalog.entity_links.filter(link => link.ontology_id === o.id).length} 个跨源实体对齐草稿 · {catalog.assets.filter(a => a.ontology_id === o.id).length} 个规则/指标/操作草稿</small></div>)}</article>)}
      </div></section>
    </div>
    <div className="notice subtle">{catalog.notice || '映射、规则、指标、操作目前为声明式草稿资产；不执行用户 SQL/SPARQL，不自动生成或修改 SH DDL。'}</div>
  </section>;
}
