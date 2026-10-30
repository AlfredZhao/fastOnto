import { FormEvent, useState } from 'react';
import { Gauge, Plus, ShieldCheck, Workflow } from 'lucide-react';
import { api } from '../api';

type AssetKind = 'RULE' | 'METRIC' | 'ACTION';
type Asset = {id: string; asset_kind: AssetKind; code: string; title: string; description?: string; lifecycle: string};
const labels: Record<AssetKind, string> = {RULE: '规则', METRIC: '指标', ACTION: '操作'};
const icons = {RULE: ShieldCheck, METRIC: Gauge, ACTION: Workflow};
function technical(value: string) { return value.trim().replace(/[^A-Za-z0-9_]/g, '_').replace(/^([^A-Za-z_])/, '_$1').slice(0, 80); }

export default function SemanticAssetEditor({ontologyId, assets, onSaved}: {ontologyId: string; assets: Asset[]; onSaved: () => Promise<void>}) {
  const [open, setOpen] = useState(false), [kind, setKind] = useState<AssetKind>('RULE');
  const [title, setTitle] = useState(''), [code, setCode] = useState(''), [description, setDescription] = useState('');
  const [subject, setSubject] = useState(''), [input, setInput] = useState(''), [outcome, setOutcome] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    const definition = kind === 'RULE'
      ? {version: 1, kind, subject, when: input, outcome}
      : kind === 'METRIC'
        ? {version: 1, kind, subject, measure: input, presentation: outcome}
        : {version: 1, kind, subject, instruction: input, expected_result: outcome};
    try {
      await api('/governance/assets', {method: 'POST', body: JSON.stringify({ontology_id: ontologyId, asset_kind: kind, code, title, description, definition})});
      await onSaved(); setOpen(false); setTitle(''); setCode(''); setDescription(''); setSubject(''); setInput(''); setOutcome('');
    } catch (e) { setError(e instanceof Error ? e.message : '保存语义资产失败。'); } finally { setBusy(false); }
  }
  if (!open) return <div className="semantic-assets"><div className="semantic-assets-summary">{assets.map(item => <span className="tag" key={item.id}>{labels[item.asset_kind]} · {item.title}</span>)}</div><button type="button" onClick={() => setOpen(true)}><Plus size={14}/>定义规则、指标或操作</button></div>;
  const firstLabel = kind === 'RULE' ? '适用对象或范围' : kind === 'METRIC' ? '指标对象或范围' : '操作对象或范围';
  const secondLabel = kind === 'RULE' ? '触发条件（业务语言）' : kind === 'METRIC' ? '度量口径（业务语言）' : '操作说明（业务语言）';
  const thirdLabel = kind === 'RULE' ? '预期结果或处置' : kind === 'METRIC' ? '展示方式或单位' : '预期结果';
  const Icon = icons[kind];
  return <form className="semantic-editor" onSubmit={save}><div className="mapping-title"><Icon size={14}/><strong>声明式语义资产</strong><button type="button" onClick={() => setOpen(false)}>关闭</button></div>
    {error && <div className="notice error" role="alert">{error}</div>}
    <label>资产类型<select value={kind} onChange={event => setKind(event.target.value as AssetKind)}><option value="RULE">规则</option><option value="METRIC">指标</option><option value="ACTION">操作</option></select></label>
    <label>名称<input required maxLength={200} value={title} onChange={event => {setTitle(event.target.value); if (!code) setCode(technical(event.target.value));}}/></label>
    <label>技术标识<input required maxLength={80} value={code} onChange={event => setCode(technical(event.target.value))}/></label>
    <label>说明<input maxLength={1000} value={description} onChange={event => setDescription(event.target.value)}/></label>
    <label>{firstLabel}<input required maxLength={200} value={subject} onChange={event => setSubject(event.target.value)} placeholder="例如：客户、订单或销售分析"/></label>
    <label>{secondLabel}<input required maxLength={1000} value={input} onChange={event => setInput(event.target.value)} placeholder="使用自然语言描述，不填写 SQL 或脚本"/></label>
    <label>{thirdLabel}<input required maxLength={1000} value={outcome} onChange={event => setOutcome(event.target.value)} placeholder="例如：显示为经营看板中的提示"/></label>
    <button className="primary" disabled={busy}>{busy ? '保存中…' : `保存${labels[kind]}草稿`}</button>
    <small>这是可追溯的声明式定义，不会执行规则、计算指标、调用操作或修改业务数据。</small>
  </form>;
}
