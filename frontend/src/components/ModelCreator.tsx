import { useEffect, useRef, useState } from 'react';
import { api } from '../api';

type CandidateField = {name: string; title: string; range: string; required: boolean; multivalued: boolean; description: string; evidence: string};
type CandidateClass = {name: string; title: string; evidence: string; fields: CandidateField[]};
type Inspection = {kind: 'yaml'; source: string} | {kind: 'document'; filename: string; classes: CandidateClass[]; warnings: string[]};
type LLMModel = {id: string; title: string; model_name: string; enabled: boolean; is_default: boolean};
const types = ['string', 'integer', 'decimal', 'float', 'double', 'boolean', 'date', 'datetime', 'uriorcurie'];

export default function ModelCreator({mode, disabled, onReady, onCancel}: {mode: 'template' | 'import'; disabled: boolean; onReady: (source: string) => void; onCancel: () => void}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [classes, setClasses] = useState<CandidateClass[]>([]);
  const [name, setName] = useState('imported_model'), [title, setTitle] = useState('文档建模草稿');
  const [namespace, setNamespace] = useState('https://example.org/ontology/');
  const [confirmed, setConfirmed] = useState(false);
  const [llms, setLlms] = useState<LLMModel[]>([]), [llmChoice, setLlmChoice] = useState(''), [llmLoaded, setLlmLoaded] = useState(false);
  const active = useRef<AbortController | null>(null), sequence = useRef(0);
  useEffect(() => () => {++sequence.current; active.current?.abort();}, []);
  useEffect(() => {
    if (mode !== 'import') return;
    void api<{items: LLMModel[]}>('/llm-models').then(result => {setLlms(result.items.filter(item => item.enabled)); setLlmChoice(result.items.find(item => item.enabled && item.is_default)?.id ?? '');}).catch(e => setError(e instanceof Error ? e.message : '无法读取 LLM 配置。')).finally(() => setLlmLoaded(true));
  }, [mode]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (inspection) {event.preventDefault(); event.returnValue = '';} };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [inspection]);

  async function run<T>(task: (signal: AbortSignal) => Promise<T>, success: (value: T) => void) {
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    const id = ++sequence.current;
    setBusy(true); setError('');
    try {const value = await task(controller.signal); if (id === sequence.current) success(value);}
    catch (e) {if (id === sequence.current && !controller.signal.aborted) setError(e instanceof Error ? e.message : '操作失败。');}
    finally {if (id === sequence.current) setBusy(false);}
  }
  function loadTemplate(value: string) {
    void run(signal => api<{source: string}>(`/models/template?name=${value}`, {signal}), result => onReady(result.source));
  }
  function upload(file?: File) {
    if (!file) return;
    setInspection(null); setClasses([]); setConfirmed(false);
    void run(async signal => {
      if (file.size === 0 || file.size > 2 * 1024 * 1024) throw new Error('文件为空或超过 2 MiB。');
      if (!/\.(xlsx|docx|md|txt|ya?ml)$/i.test(file.name)) throw new Error('仅支持 XLSX、DOCX、Markdown、TXT 和 YAML；旧版 XLS/DOC 请先转换。');
      if (!/\.ya?ml$/i.test(file.name) && (!llmLoaded || !llmChoice)) throw new Error('请先在 LLM 配置页新增并设定一个默认模型，或在此处选择可用模型。');
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = '';
      for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
      return api<Inspection>('/models/import', {method: 'POST', signal, body: JSON.stringify({filename: file.name, content_base64: btoa(binary), llm_id: /\.ya?ml$/i.test(file.name) ? undefined : llmChoice})});
    }, result => {
      if (result.kind !== 'yaml' && result.kind !== 'document') throw new Error('无法识别文件解析结果。');
      setInspection(result);
      if (result.kind === 'document') {setClasses(result.classes); setTitle(file.name.replace(/\.[^.]+$/, '').slice(0, 200));}
    });
  }
  function changeClasses(next: CandidateClass[]) {setClasses(next); setConfirmed(false);}
  function changeClass(index: number, patch: Partial<CandidateClass>) {changeClasses(classes.map((c, i) => i === index ? {...c, ...patch} : c));}
  function changeField(ci: number, fi: number, patch: Partial<CandidateField>) {changeClass(ci, {fields: classes[ci].fields.map((f, i) => i === fi ? {...f, ...patch} : f)});}
  function generate() {
    void run(signal => api<{source: string}>('/models/draft', {method: 'POST', signal, body: JSON.stringify({name, title, namespace, classes})}), result => onReady(result.source));
  }
  return <section className="panel model-creator" aria-label="创建模型向导">
    <div className="panel-title"><h2>{mode === 'template' ? '新建独立模型' : '从文件创建模型'}</h2><button className="icon-button" onClick={onCancel}>关闭向导</button></div>
    <div className="creator-content">
      <p>只创建模型草稿，不保存上传原文件、不导入业务记录、不修改 SH。文档会在本平台内存中预处理，并发送给你选择的 LLM 生成 LinkML 候选；请在生成前人工审核。</p>
      {error && <div role="alert" className="notice error">{error}</div>}
      {busy && <div role="status" className="notice">正在处理，请稍候… 原模型不会被自动覆盖。</div>}
      <fieldset disabled={busy || disabled}>
        {mode === 'template' ? <div className="actions template-options">
          <button onClick={() => loadTemplate('blank')}>空白模型骨架</button>
          <button onClick={() => loadTemplate('sales')}>销售示例</button>
          <button onClick={() => loadTemplate('standards')}>标准与发布机构</button>
        </div> : <>
          <label className="creator-label">文档分析 LLM<select value={llmChoice} disabled={!llmLoaded || !llms.length} onChange={event => setLlmChoice(event.target.value)}><option value="">请选择 LLM…</option>{llms.map(item => <option value={item.id} key={item.id}>{item.title} · {item.model_name}{item.is_default ? '（默认）' : ''}</option>)}</select></label>
          {!llmLoaded ? <p className="caption">正在读取 LLM 配置…</p> : !llms.length ? <div className="notice warning">尚无可用 LLM。请先进入“LLM 配置”新增 HTTPS 模型并设为默认模型。</div> : <p className="caption">默认选择平台默认 LLM。上传 XLSX、DOCX、Markdown 或 TXT 后，文档内容/本地提取结构会发送至所选 LLM 用于生成候选。</p>}
          <label className="creator-label">上传模型或业务文档<input type="file" accept=".xlsx,.docx,.md,.txt,.yaml,.yml" onChange={event => {upload(event.target.files?.[0]); event.target.value = '';}}/></label>
          <p className="caption">最大 2 MiB。支持 XLSX / DOCX / UTF-8 Markdown、TXT、LinkML YAML；YAML 模型仍限 64 KiB。旧版 XLS / DOC 请转换。重新选择文件会清除本向导中的候选修改。</p>
          {inspection?.kind === 'yaml' && <>
            <div role="status" className="notice">YAML 已通过结构校验；导入会创建独立草稿，不修改已有模型。</div>
            <pre className="import-preview" aria-label="YAML 导入预览">{inspection.source}</pre>
            <button className="primary" onClick={() => onReady(inspection.source)}>导入为独立草稿</button>
          </>}
          {inspection?.kind === 'document' && <>
            <h3>审核候选模型</h3>
            <p>文件：{inspection.filename} · {classes.length} 个候选类。LLM 输出仅作为候选；请审核类、属性、关系、标识和约束。</p>
            <ul className="import-warnings">{inspection.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>
            <div className="creator-grid">
              <label className="creator-label">模型技术标识<input value={name} maxLength={80} onChange={e => {setName(e.target.value); setConfirmed(false);}}/></label>
              <label className="creator-label">模型中文名称<input value={title} maxLength={200} onChange={e => {setTitle(e.target.value); setConfirmed(false);}}/></label>
              <label className="creator-label namespace-field">命名空间 IRI<input value={namespace} maxLength={1000} onChange={e => {setNamespace(e.target.value); setConfirmed(false);}}/></label>
            </div>
            <p className="caption">技术标识使用 ASCII 字母、数字和下划线，不以数字开头。example.org 仅为占位命名空间，正式使用前请更换。</p>
            {!classes.length && <div className="empty compact">没有候选类。可手动添加类和属性，或将文件整理为数据字典后重试。</div>}
            {classes.map((cls, ci) => <article className="candidate-class" key={ci} aria-label={`候选类 ${ci + 1}`}>
              <div className="creator-grid">
                <label className="creator-label">类技术标识<input value={cls.name} maxLength={80} onChange={e => changeClass(ci, {name: e.target.value})}/></label>
                <label className="creator-label">类名称<input value={cls.title} maxLength={200} onChange={e => changeClass(ci, {title: e.target.value})}/></label>
              </div>
              <p className="caption evidence">来源：{cls.evidence || '手工新增'}</p>
              <button onClick={() => changeClasses(classes.filter((_, i) => i !== ci))}>删除此类</button>
              {cls.fields.map((field, fi) => <div className="candidate-field" key={fi} aria-label={`属性 ${fi + 1}`}>
                <div className="creator-grid">
                  <label className="creator-label">属性技术标识<input value={field.name} maxLength={80} onChange={e => changeField(ci, fi, {name: e.target.value})}/></label>
                  <label className="creator-label">属性名称<input value={field.title} maxLength={200} onChange={e => changeField(ci, fi, {title: e.target.value})}/></label>
                  <label className="creator-label">类型或目标类<select value={field.range} onChange={e => changeField(ci, fi, {range: e.target.value})}>
                    <optgroup label="数据类型">{types.map(t => <option key={t}>{t}</option>)}</optgroup>
                    <optgroup label="对象关系目标">{classes.filter(c => c.name).map((c, i) => <option key={i} value={c.name}>{c.title} ({c.name})</option>)}</optgroup>
                    {!types.includes(field.range) && !classes.some(c => c.name === field.range) && <option value={field.range}>失效引用：{field.range}</option>}
                  </select></label>
                  <label className="creator-label">属性说明<input value={field.description} maxLength={1000} onChange={e => changeField(ci, fi, {description: e.target.value})}/></label>
                </div>
                <div className="actions">
                  <label><input type="checkbox" checked={field.required} onChange={e => changeField(ci, fi, {required: e.target.checked})}/> 必填</label>
                  <label><input type="checkbox" checked={field.multivalued} onChange={e => changeField(ci, fi, {multivalued: e.target.checked})}/> 多值</label>
                  <button onClick={() => changeClass(ci, {fields: cls.fields.filter((_, i) => i !== fi)})}>删除属性</button>
                </div>
                <p className="caption evidence">来源：{field.evidence || '手工新增'}</p>
              </div>)}
              <button disabled={cls.fields.length >= 100 || classes.reduce((sum, c) => sum + c.fields.length, 0) >= 120} onClick={() => {
                let n = cls.fields.length + 1; while (cls.fields.some(f => f.name === `field${n}`)) n++;
                changeClass(ci, {fields: [...cls.fields, {name: `field${n}`, title: '新属性', range: 'string', required: false, multivalued: false, description: '', evidence: ''}]});
              }}>添加属性／关系</button>
            </article>)}
            <button disabled={classes.length >= 30} onClick={() => {
              let n = classes.length + 1; while (classes.some(c => c.name === `Entity${n}`)) n++;
              changeClasses([...classes, {name: `Entity${n}`, title: '新实体', evidence: '', fields: []}]);
            }}>添加类</button>
            <label className="review-confirm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/> 我已审核候选类、属性及关系；生成结果仍需业务验证</label>
            <button className="primary" disabled={!confirmed || !classes.length} onClick={generate}>生成并打开独立草稿</button>
          </>}
        </>}
      </fieldset>
    </div>
  </section>;
}
