import { FormEvent, useEffect, useState } from 'react';
import { Link2, Plus } from 'lucide-react';
import { api, type ModelClass, type Saved, type Source } from '../api';

type Ontology = {id: string; domain_id: string; title: string; model_id?: string | null; model_revision?: number | null};
type SourceModel = Saved & {source: string};
type BusinessSource = {id: string; domain_id: string; code: string; title: string; owner_schema: string; enabled: boolean};
type ObjectItem = {name: string; type: string};
type Metadata = {name: string; columns: {name: string}[]};
type ActiveSource = {kind: 'sh'; sourceCode: string; label: string; columns: string[]} | {kind: 'business'; sourceId: string; objectName: string; label: string; columns: string[]};

export default function MappingEditor({ontology, onSaved}: {ontology: Ontology; onSaved: () => Promise<void>}) {
  const [open, setOpen] = useState(false), [classes, setClasses] = useState<ModelClass[]>([]), [sources, setSources] = useState<Source[]>([]), [business, setBusiness] = useState<BusinessSource[]>([]);
  const [className, setClassName] = useState(''), [selection, setSelection] = useState(''), [objects, setObjects] = useState<ObjectItem[]>([]), [objectName, setObjectName] = useState(''), [active, setActive] = useState<ActiveSource | null>(null);
  const [subjectColumn, setSubjectColumn] = useState(''), [template, setTemplate] = useState(''), [title, setTitle] = useState(''), [code, setCode] = useState(''), [columns, setColumns] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const cls = classes.find(item => item.name === className);
  useEffect(() => {
    if (!open || !ontology.model_id) return;
    setError('');
    Promise.all([api<SourceModel>(`/models/${encodeURIComponent(ontology.model_id)}`), api<{items: Source[]}>('/sources'), api<{items: BusinessSource[]}>('/business-sources')]).then(([model, catalog, external]) => api<{classes: ModelClass[]}>('/models/validate', {method: 'POST', body: JSON.stringify({source: model.source})}).then(report => { setClasses(report.classes); setSources(catalog.items); setBusiness(external.items.filter(item => item.domain_id === ontology.domain_id && item.enabled)); })).catch(e => setError(e instanceof Error ? e.message : '无法读取模型或数据源。'));
  }, [open, ontology.model_id, ontology.domain_id]);
  function resetSource() { setObjectName(''); setObjects([]); setActive(null); setSubjectColumn(''); setTemplate(''); setColumns({}); }
  function chooseClass(next: string) { setClassName(next); setColumns({}); const item = classes.find(c => c.name === next); if (item) { setTitle(`${item.title} 映射`); setCode(`${item.name}_mapping`); } }
  async function chooseSource(next: string) {
    setSelection(next); resetSource(); if (!next) return;
    if (next.startsWith('sh:')) { const source = sources.find(item => item.name === next.slice(3)); if (source) setActive({kind: 'sh', sourceCode: source.name, label: `SH.${source.name}`, columns: source.columns}); return; }
    const sourceId = next.slice(9); setBusy(true); setError('');
    try { const result = await api<{items: ObjectItem[]}>(`/business-sources/${encodeURIComponent(sourceId)}/discover`, {method: 'POST'}); setObjects(result.items); }
    catch (e) { setError(e instanceof Error ? e.message : '无法探查业务数据源。'); } finally { setBusy(false); }
  }
  async function chooseObject(next: string) {
    setObjectName(next); setActive(null); setSubjectColumn(''); setTemplate(''); setColumns({}); if (!next) return;
    const sourceId = selection.slice(9); setBusy(true); setError('');
    try { const metadata = await api<Metadata>(`/business-sources/${encodeURIComponent(sourceId)}/objects/${encodeURIComponent(next)}/metadata`); setActive({kind: 'business', sourceId, objectName: metadata.name, label: `${business.find(item => item.id === sourceId)?.title ?? '业务源'}.${metadata.name}`, columns: metadata.columns.map(item => item.name)}); }
    catch (e) { setError(e instanceof Error ? e.message : '无法读取表/视图字段。'); } finally { setBusy(false); }
  }
  function chooseSubject(next: string) { setSubjectColumn(next); const sourceName = active?.kind === 'sh' ? active.sourceCode.toLowerCase() : active?.objectName.toLowerCase(); setTemplate(`https://fastonto.example/entity/${sourceName}/{${next}}`); }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!cls || !active || !subjectColumn) return;
    const properties = Object.entries(columns).filter(([, column]) => column).map(([property, column]) => ({property, column}));
    setBusy(true); setError('');
    try {
      const sourceBinding = active.kind === 'sh' ? {source_code: active.sourceCode} : {source_id: active.sourceId, source_object_name: active.objectName};
      await api('/governance/mappings', {method: 'POST', body: JSON.stringify({ontology_id: ontology.id, code, title, ...sourceBinding, mapping_kind: 'R2RML_DRAFT', definition: {version: 1, class: cls.name, subject: {column: subjectColumn, iri_template: template}, properties}})});
      await onSaved(); setOpen(false);
    } catch (e) { setError(e instanceof Error ? e.message : '保存映射失败。'); } finally { setBusy(false); }
  }
  if (!ontology.model_id) return <small>请先关联 LinkML 模型，才能建立字段映射。</small>;
  if (!open) return <button onClick={() => setOpen(true)}><Plus size={14}/>新建字段映射</button>;
  const scalarSlots = cls?.slots.filter(slot => !classes.some(candidate => candidate.name === slot.range)) ?? [];
  return <form className="mapping-editor" onSubmit={save}><div className="mapping-title"><Link2 size={14}/><strong>字段映射草稿</strong><button type="button" onClick={() => setOpen(false)}>关闭</button></div>{error && <div className="notice error">{error}</div>}
    <label>本体类<select required value={className} onChange={e => chooseClass(e.target.value)}><option value="">请选择</option>{classes.map(item => <option key={item.name} value={item.name}>{item.title} ({item.name})</option>)}</select></label>
    <label>数据源<select required value={selection} onChange={e => void chooseSource(e.target.value)} disabled={busy}><option value="">请选择</option><optgroup label="内置 SH 白名单">{sources.map(item => <option key={`sh:${item.name}`} value={`sh:${item.name}`}>{item.title} · SH.{item.name}</option>)}</optgroup>{business.length > 0 && <optgroup label="当前业务域的外部只读源">{business.map(item => <option key={item.id} value={`business:${item.id}`}>{item.title} · {item.owner_schema}</option>)}</optgroup>}</select></label>
    {selection.startsWith('business:') && <label>表 / 视图<select required value={objectName} onChange={e => void chooseObject(e.target.value)} disabled={busy}><option value="">请选择（实时探查）</option>{objects.map(item => <option key={item.name} value={item.name}>{item.name} · {item.type}</option>)}</select></label>}
    {active && <><label>主体标识字段<select required value={subjectColumn} onChange={e => chooseSubject(e.target.value)}><option value="">请选择</option>{active.columns.map(column => <option key={column}>{column}</option>)}</select></label><label>实例 IRI 模板<input required maxLength={1000} value={template} onChange={e => setTemplate(e.target.value)} placeholder="https://…/{ID}"/></label></>}
    {scalarSlots.length > 0 && active && <div className="mapping-properties"><strong>标量属性映射</strong>{scalarSlots.map(slot => <label key={slot.name}>{slot.title}<select value={columns[slot.name] ?? ''} onChange={e => setColumns({...columns, [slot.name]: e.target.value})}><option value="">不映射</option>{active.columns.map(column => <option key={column}>{column}</option>)}</select></label>)}</div>}
    <label>映射名称<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)}/></label><label>技术标识<input required maxLength={80} value={code} onChange={e => setCode(e.target.value.replace(/[^A-Za-z0-9_]/g, '_'))}/></label>
    <button className="primary" disabled={busy || !className || !active || !subjectColumn || !Object.values(columns).some(Boolean)}>{busy ? '处理中…' : '保存映射草稿'}</button><small>外部源仅实时读取数据字典来校验字段；不读取或复制业务行，不执行 SQL、join 或对象关系映射。</small>
  </form>;
}
