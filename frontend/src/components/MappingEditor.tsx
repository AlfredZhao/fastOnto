import { FormEvent, useEffect, useState } from 'react';
import { Link2, Plus } from 'lucide-react';
import { api, type ModelClass, type Saved, type Source } from '../api';

type Ontology = {id: string; domain_id: string; title: string; model_id?: string | null; model_revision?: number | null};
type SourceModel = Saved & {source: string};
type BusinessSource = {id: string; domain_id: string; code: string; title: string; owner_schema: string; enabled: boolean};
type ObjectItem = {name: string; type: string};
type Metadata = {name: string; columns: {name: string; data_type?: string}[]; primary_key?: string[]};
type Alignment = {matched: {property: string; column: string}[]; missing: string[]; extra: string[]; subject: string; objectRelations: string[]};
type ActiveSource = {kind: 'sh'; sourceCode: string; label: string; columns: string[]; primaryKey: string[]} | {kind: 'business'; sourceId: string; objectName: string; label: string; columns: string[]; primaryKey: string[]};

export default function MappingEditor({ontology, onSaved}: {ontology: Ontology; onSaved: () => Promise<void>}) {
  const [open, setOpen] = useState(false), [classes, setClasses] = useState<ModelClass[]>([]), [sources, setSources] = useState<Source[]>([]), [business, setBusiness] = useState<BusinessSource[]>([]);
  const [className, setClassName] = useState(''), [selection, setSelection] = useState(''), [objects, setObjects] = useState<ObjectItem[]>([]), [objectName, setObjectName] = useState(''), [active, setActive] = useState<ActiveSource | null>(null);
  const [subjectColumn, setSubjectColumn] = useState(''), [template, setTemplate] = useState(''), [title, setTitle] = useState(''), [code, setCode] = useState(''), [columns, setColumns] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [suggestion, setSuggestion] = useState(''), [alignment, setAlignment] = useState<Alignment | null>(null);
  const cls = classes.find(item => item.name === className);
  useEffect(() => {
    if (!open || !ontology.model_id) return;
    setError('');
    Promise.all([api<SourceModel>(`/models/${encodeURIComponent(ontology.model_id)}`), api<{items: Source[]}>('/sources'), api<{items: BusinessSource[]}>('/business-sources')]).then(([model, catalog, external]) => api<{classes: ModelClass[]}>('/models/validate', {method: 'POST', body: JSON.stringify({source: model.source})}).then(report => { setClasses(report.classes); setSources(catalog.items); setBusiness(external.items.filter(item => item.domain_id === ontology.domain_id && item.enabled)); })).catch(e => setError(e instanceof Error ? e.message : '无法读取模型或数据源。'));
  }, [open, ontology.model_id, ontology.domain_id]);
  function resetSource() { setObjectName(''); setObjects([]); setActive(null); setSubjectColumn(''); setTemplate(''); setColumns({}); setSuggestion(''); setAlignment(null); }
  function chooseClass(next: string) { setClassName(next); setColumns({}); const item = classes.find(c => c.name === next); if (item) { setTitle(`${item.title} 映射`); setCode(`${item.name}_mapping`); } }
  async function chooseSource(next: string) {
    setSelection(next); resetSource(); if (!next) return;
    if (next.startsWith('sh:')) { const source = sources.find(item => item.name === next.slice(3)); if (source) setActive({kind: 'sh', sourceCode: source.name, label: `SH.${source.name}`, columns: source.columns, primaryKey: /未定义/.test(source.identity) ? [] : [source.identity]}); return; }
    const sourceId = next.slice(9); setBusy(true); setError('');
    try { const result = await api<{items: ObjectItem[]}>(`/business-sources/${encodeURIComponent(sourceId)}/discover`, {method: 'POST'}); setObjects(result.items); }
    catch (e) { setError(e instanceof Error ? e.message : '无法探查业务数据源。'); } finally { setBusy(false); }
  }
  async function chooseObject(next: string) {
    setObjectName(next); setActive(null); setSubjectColumn(''); setTemplate(''); setColumns({}); if (!next) return;
    const sourceId = selection.slice(9); setBusy(true); setError('');
    try { const metadata = await api<Metadata>(`/business-sources/${encodeURIComponent(sourceId)}/objects/${encodeURIComponent(next)}/metadata`); setActive({kind: 'business', sourceId, objectName: metadata.name, label: `${business.find(item => item.id === sourceId)?.title ?? '业务源'}.${metadata.name}`, columns: metadata.columns.map(item => item.name), primaryKey: metadata.primary_key ?? []}); }
    catch (e) { setError(e instanceof Error ? e.message : '无法读取表/视图字段。'); } finally { setBusy(false); }
  }
  function chooseSubject(next: string) { setSubjectColumn(next); const sourceName = active?.kind === 'sh' ? active.sourceCode.toLowerCase() : active?.objectName.toLowerCase(); setTemplate(`https://fastonto.example/entity/${sourceName}/{${next}}`); }
  function suggestFields() {
    if (!active || !cls) return;
    const normalize = (value: string) => value.toUpperCase().replace(/[^A-Z0-9]/g, '');
    const sourceByName = new Map(active.columns.map(column => [normalize(column), column]));
    const suggested = Object.fromEntries(scalarSlots.flatMap(slot => {
      const column = sourceByName.get(normalize(slot.name)) ?? sourceByName.get(normalize(slot.title));
      return column ? [[slot.name, column]] : [];
    }));
    setColumns(current => ({...suggested, ...current}));
    const identifier = cls.slots.find(slot => slot.identifier);
    const candidate = identifier && (sourceByName.get(normalize(identifier.name)) ?? sourceByName.get(normalize(identifier.title)))
      || active.columns.find(column => /(^|_)(ID|KEY|CODE)$/.test(column.toUpperCase()))
      || '';
    if (candidate && !subjectColumn) chooseSubject(candidate);
    setSuggestion(Object.keys(suggested).length ? `已按字段技术名或中文标题匹配 ${Object.keys(suggested).length} 个标量属性；请人工确认。` : '未找到同名字段；请手动选择映射。');
  }
  function inspectAlignment() {
    if (!active || !cls) return;
    const normalize = (value: string) => value.toUpperCase().replace(/[^A-Z0-9]/g, '');
    const sourceByName = new Map(active.columns.map(column => [normalize(column), column]));
    const matched = scalarSlots.flatMap(slot => {
      const column = sourceByName.get(normalize(slot.name)) ?? sourceByName.get(normalize(slot.title));
      return column ? [{property: slot.title, column}] : [];
    });
    const used = new Set(matched.map(item => item.column));
    const identifier = cls.slots.find(slot => slot.identifier);
    const identifierColumn = identifier ? (sourceByName.get(normalize(identifier.name)) ?? sourceByName.get(normalize(identifier.title)) ?? '') : '';
    const subject = active.primaryKey[0] ?? identifierColumn;
    setAlignment({matched, missing: scalarSlots.filter(slot => !matched.some(item => item.property === slot.title)).map(slot => slot.title), extra: active.columns.filter(column => !used.has(column) && column !== subject), subject, objectRelations: cls.slots.filter(slot => classes.some(candidate => candidate.name === slot.range)).map(slot => `${slot.title} → ${slot.range}`)});
  }
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
    {active && <><div className="alignment-actions"><button type="button" onClick={inspectAlignment}>校验模型与数据表</button>{active.primaryKey.length > 0 && <small>数据源主键：{active.primaryKey.join(', ')}</small>}</div>{alignment && <div className="alignment-report"><strong>对齐报告 · {active.label}</strong><p>匹配属性：{alignment.matched.length} 项；未匹配模型属性：{alignment.missing.length} 项；未纳入字段：{alignment.extra.length} 项。</p>{alignment.subject && <p>建议主体标识：<code>{alignment.subject}</code></p>}{alignment.missing.length > 0 && <p>待补充：{alignment.missing.join('、')}</p>}{alignment.objectRelations.length > 0 && <p>对象关系待审核：{alignment.objectRelations.join('；')}。首版仅保存关系意图，不自动执行 join。</p>}</div>}<label>主体标识字段<select required value={subjectColumn} onChange={e => chooseSubject(e.target.value)}><option value="">请选择</option>{active.columns.map(column => <option key={column}>{column}</option>)}</select></label><label>实例 IRI 模板<input required maxLength={1000} value={template} onChange={e => setTemplate(e.target.value)} placeholder="https://…/{ID}"/></label></>}
    {scalarSlots.length > 0 && active && <div className="mapping-properties"><div className="mapping-properties-heading"><strong>标量属性映射</strong><button type="button" onClick={suggestFields}>自动匹配字段</button></div>{suggestion && <small>{suggestion}</small>}{scalarSlots.map(slot => <label key={slot.name}>{slot.title}<select value={columns[slot.name] ?? ''} onChange={e => setColumns({...columns, [slot.name]: e.target.value})}><option value="">不映射</option>{active.columns.map(column => <option key={column}>{column}</option>)}</select></label>)}</div>}
    <label>映射名称<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)}/></label><label>技术标识<input required maxLength={80} value={code} onChange={e => setCode(e.target.value.replace(/[^A-Za-z0-9_]/g, '_'))}/></label>
    <button className="primary" disabled={busy || !className || !active || !subjectColumn || !Object.values(columns).some(Boolean)}>{busy ? '处理中…' : '保存映射草稿'}</button><small>自动匹配仅按当前模型属性与源字段的同名规则给出建议，需人工确认。外部源仅实时读取数据字典来校验字段；不读取或复制业务行，不执行 SQL、join 或对象关系映射。</small>
  </form>;
}
