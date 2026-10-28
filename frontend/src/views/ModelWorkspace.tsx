import { useEffect, useRef, useState } from 'react';
import { CheckCheck, Download, FileCode2, GitBranch, Save, Shapes } from 'lucide-react';
import { download } from '../api';
import type { Workspace } from '../useWorkspace';
import Dialog from '../components/Dialog';
import ModelCreator from '../components/ModelCreator';

export default function ModelWorkspace({work, active = true}: {work: Workspace; active?: boolean}) {
  const currentWork = useRef(work);
  currentWork.current = work;
  const [selected, setSelected] = useState('');
  const [pending, setPending] = useState<{kind: 'load' | 'draft'; value: string} | null>(null);
  const [creator, setCreator] = useState<'template' | 'import' | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const [tab, setTab] = useState<'fields' | 'relations'>('fields');
  const cls = work.report?.classes.find(c => c.name === selected) ?? work.report?.classes[0];
  useEffect(() => {work.setImportDirty(creator !== null);}, [creator, work.setImportDirty]);
  useEffect(() => { if (work.report && !work.report.classes.some(c => c.name === selected)) setSelected(work.report.classes[0]?.name ?? ''); }, [work.report, selected]);
  function applyDraft(source: string) {
    const latest = currentWork.current;
    if (latest.dirty || latest.busy) setPending({kind: 'draft', value: source});
    else if (latest.replaceDraft(source)) setCreator(null);
  }
  return <section className="page" aria-label="模型工作台">
    <div className="page-heading"><div><div className="eyebrow">MODEL STUDIO / 01</div><h1>从业务语言，到可验证的模型</h1><p>LinkML 是模型主源。理解结构、校验约束，不改动任何业务数据。</p></div><span className="tag">建模基础版</span></div>
    <div className="toolbar panel"><div className="status-inline"><span className={`dot ${work.dirty ? 'warning' : ''}`}/><strong>{work.record ? `版本 ${work.record.revision}` : '独立草稿'}</strong><span>{work.dirty ? '有未保存内容' : '已保存'}</span></div>
      <div className="actions">
        <button disabled={!!work.busy || work.loading || !!creator} onClick={() => setCreator('template')}>新建模型</button>
        <button disabled={!!work.busy || work.loading || !!creator} onClick={() => setCreator('import')}>导入文件</button>
        <button disabled={!!work.busy || !work.source} onClick={() => void work.action('validate')}><CheckCheck size={16}/>{work.busy === 'validate' ? '校验中…' : '校验模型'}</button>
        <button disabled={!!work.busy || !work.source} onClick={() => download(work.source, 'model.yaml')}><Download size={16}/>YAML</button>
        <button disabled={!!work.busy || !work.source} onClick={() => void work.action('export')}>JSON Schema</button>
        <button disabled={!!work.busy || !work.source} onClick={() => void work.action('export', 'owl')}>OWL</button>
        <button disabled={!!work.busy || !work.source} onClick={() => void work.action('export', 'shacl')}>SHACL</button>
        <button disabled={!!work.busy || !work.source} onClick={() => void work.action('saveAs')}>{work.busy === 'saveAs' ? '另存中…' : '另存为新模型'}</button>
        <button className="primary" disabled={!!work.busy || !work.source} onClick={() => void work.action('save')}><Save size={16}/>{work.busy === 'save' ? '保存中…' : '保存版本'}</button>
      </div>
    </div>
    {work.error && <div role="alert" className="notice error">{work.error}</div>}
    {work.message && <div role="status" className="notice">{work.message}</div>}
    {creator && <ModelCreator mode={creator} disabled={!!work.busy || work.loading} onReady={applyDraft} onCancel={() => setConfirmClose(true)}/>}
    <div className="workspace">
      <aside className="panel resource-tree"><div className="panel-title"><Shapes size={16}/><h2>模型资源</h2><span className="count">{work.report?.classes.length ?? '—'}</span></div>
        <label className="field-label" htmlFor="saved-model">已保存的模型</label>
        <select id="saved-model" value={work.record?.id ?? ''} disabled={!!work.busy || !!creator} onChange={e => { if (!e.target.value) return; if (work.dirty) setPending({kind: 'load', value: e.target.value}); else void work.openModel(e.target.value); }}>
          <option value="" disabled>当前草稿</option>{work.models.map(m => <option key={m.id} value={m.id}>{m.title} · v{m.revision}</option>)}
        </select>
        <p className="caption">资源树展示最近一次校验快照。</p>
        <nav aria-label="模型中的类">{work.report?.classes.map(c => <button key={c.name} className={`tree-item ${cls?.name === c.name ? 'selected' : ''}`} onClick={() => setSelected(c.name)}><Shapes size={15}/><span>{c.title}<small>{c.name}</small></span><span className="count">{c.slots.length}</span></button>)}</nav>
        {!work.report && <div className="empty compact">点击“校验模型”生成类与关系视图。</div>}
        <div className="boundary"><span className="dot"/>业务源只读<br/><small>SH → 虚拟语义映射<br/>不复制业务实例</small></div>
      </aside>
      <section className="panel editor-panel"><div className="panel-title"><FileCode2 size={16}/><h2>LinkML 源码</h2><span className="caption">YAML · UTF-8</span></div>
        <label className="sr-only" htmlFor="model-source">LinkML 模型源码</label>
        <textarea id="model-source" className="code-editor" value={work.source} onChange={e => work.setSource(e.target.value)} disabled={work.loading || work.busy === 'load'} spellCheck={false} placeholder={work.loading ? '正在加载示例…' : '粘贴 LinkML YAML 开始建模'} />
        <div className="editor-footer"><span>{new TextEncoder().encode(work.source).length.toLocaleString()} / 65,536 字节</span><span>草稿仅保存在当前页面内存</span></div>
      </section>
      <aside className="panel inspector"><div className="panel-title"><GitBranch size={16}/><h2>模型检查器</h2></div>
        {work.report && work.reportStale && <div className="notice warning" role="status">草稿已变化，下方结果来自旧快照，请重新校验。</div>}
        {cls ? <><div className="class-heading"><span className="eyebrow">CLASS</span><h3>{cls.title}</h3><code className="uri">{cls.uri}</code><p>{cls.description}</p></div>
          <div className="tabs" role="tablist" aria-label="检查器视图"><button role="tab" aria-selected={tab === 'fields'} onClick={() => setTab('fields')}>属性 · {cls.slots.length}</button><button role="tab" aria-selected={tab === 'relations'} onClick={() => setTab('relations')}>关系</button></div>
          {tab === 'fields' ? <div role="tabpanel" className="field-list">{cls.slots.map(f => <article key={f.name} className="field-card"><div><strong>{f.title}</strong><span className="tag">{f.range}</span></div><code>{f.name}</code><div className="field-flags">{f.required && <span>必填</span>}{f.multivalued && <span>多值</span>}{f.identifier && <span>标识</span>}</div></article>)}</div> : <div role="tabpanel" className="field-list">{work.report?.relationships.filter(r => r.source === cls.name || r.target === cls.name).map((r, i) => <div className="relation" key={i}><code>{r.source}</code><span>— {r.label} →</span><code>{r.target}</code></div>)}<p className="caption">这是模型关系列表，不是业务实例图。</p></div>}
        </> : <div className="empty"><GitBranch size={30}/><h3>让结构清晰可见</h3><p>校验后查看类、属性和关系。校验失败不会清空你的源码。</p></div>}
      </aside>
    </div>
    <div className="notice subtle">{work.report?.warnings.join(' ') ?? '首版支持类、属性、枚举与单继承。仅允许内置 linkml:types；不执行远程导入或生成代码。'}</div>
    <Dialog open={!!pending && active} title={pending?.kind === 'draft' ? '创建独立草稿？' : '打开另一个模型？'} onCancel={() => setPending(null)} confirmDisabled={!!work.busy || work.loading} onConfirm={() => {
      if (!pending) return;
      if (pending.kind === 'load') void work.openModel(pending.value);
      else if (work.replaceDraft(pending.value)) setCreator(null);
      setPending(null);
    }}/>
    <Dialog open={confirmClose && active} title="关闭创建向导？" message="向导中的候选修改将被丢弃；原工作台草稿保持不变。" confirmLabel="丢弃候选并关闭" onCancel={() => setConfirmClose(false)} onConfirm={() => {setCreator(null); setPending(null); setConfirmClose(false);}}/>
  </section>;
}
