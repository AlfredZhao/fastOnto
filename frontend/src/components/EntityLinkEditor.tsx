import { FormEvent, useState } from 'react';
import { GitFork, Plus } from 'lucide-react';
import { api } from '../api';

type Mapping = {id: string; ontology_id: string; code: string; title: string; source_code?: string; source_id?: string | null; source_object_name?: string | null};

export default function EntityLinkEditor({ontologyId, mappings, onSaved}: {ontologyId: string; mappings: Mapping[]; onSaved: () => Promise<void>}) {
  const [open, setOpen] = useState(false), [left, setLeft] = useState(''), [right, setRight] = useState(''), [leftKey, setLeftKey] = useState(''), [rightKey, setRightKey] = useState(''), [title, setTitle] = useState(''), [code, setCode] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  if (mappings.length < 2) return <small>至少保存两个映射草稿后，才能声明跨源实体对齐。</small>;
  if (!open) return <button onClick={() => setOpen(true)}><Plus size={14}/>新建实体对齐</button>;
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { await api('/governance/entity-links', {method: 'POST', body: JSON.stringify({ontology_id: ontologyId, code, title, left_mapping_id: left, right_mapping_id: right, definition: {version: 1, kind: 'IDENTITY', left_key: leftKey, right_key: rightKey}})}); await onSaved(); setOpen(false); }
    catch (e) { setError(e instanceof Error ? e.message : '保存实体对齐失败。'); } finally { setBusy(false); }
  }
  const describe = (item: Mapping) => `${item.title} · ${item.source_object_name ?? item.source_code ?? '数据源'}`;
  return <form className="mapping-editor" onSubmit={save}><div className="mapping-title"><GitFork size={14}/><strong>跨源实体对齐草稿</strong><button type="button" onClick={() => setOpen(false)}>关闭</button></div>{error && <div className="notice error">{error}</div>}
    <label>左侧映射<select required value={left} onChange={e => setLeft(e.target.value)}><option value="">请选择</option>{mappings.map(item => <option key={item.id} value={item.id}>{describe(item)}</option>)}</select></label><label>左侧对齐字段<input required maxLength={128} value={leftKey} onChange={e => setLeftKey(e.target.value.toUpperCase())} placeholder="例如 CUSTOMER_ID"/></label>
    <label>右侧映射<select required value={right} onChange={e => setRight(e.target.value)}><option value="">请选择</option>{mappings.filter(item => item.id !== left).map(item => <option key={item.id} value={item.id}>{describe(item)}</option>)}</select></label><label>右侧对齐字段<input required maxLength={128} value={rightKey} onChange={e => setRightKey(e.target.value.toUpperCase())} placeholder="例如 USER_ID"/></label>
    <label>对齐名称<input required maxLength={200} value={title} onChange={e => { setTitle(e.target.value); if (!code) setCode(e.target.value.replace(/[^A-Za-z0-9_]/g, '_').slice(0, 80)); }}/></label><label>技术标识<input required maxLength={80} value={code} onChange={e => setCode(e.target.value.replace(/[^A-Za-z0-9_]/g, '_'))}/></label>
    <button className="primary" disabled={busy || !left || !right || !leftKey || !rightKey || left === right}>{busy ? '保存中…' : '保存实体对齐草稿'}</button><small>仅声明两个已映射字段代表同一实体；不执行跨源 join、匹配或查询。字段必须已在各自映射中使用。</small>
  </form>;
}
