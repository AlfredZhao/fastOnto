import { useEffect, useRef, useState } from 'react';
import { api, download, type Report, type Saved } from './api';

export function useWorkspace() {
  const [source, setSource] = useState('');
  const [savedSource, setSavedSource] = useState('');
  const [record, setRecord] = useState<Saved | null>(null);
  const [models, setModels] = useState<Saved[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [reportSource, setReportSource] = useState('');
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [importDirty, setImportDirty] = useState(false);
  const generation = useRef(0);
  const busyRef = useRef(false);
  const dirty = source !== savedSource;
  const refreshModels = () => api<{items: Saved[]}>('/models').then(r => setModels(Array.isArray(r.items) ? r.items : [])).catch(() => setModels([]));

  useEffect(() => {
    const controller = new AbortController();
    api<{source: string}>('/models/template', { signal: controller.signal }).then(r => {
      if (controller.signal.aborted) return;
      if (typeof r.source !== 'string') throw new Error('模板响应结构不正确。');
      setSource(r.source);
    }).catch(e => { if (!controller.signal.aborted) setError(String(e.message)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    void refreshModels();
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty || importDirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [dirty, importDirty]);

  function replaceDraft(nextSource: string) {
    if (busyRef.current || loading) return false;
    ++generation.current;
    setSource(nextSource); setSavedSource(''); setRecord(null);
    setReport(null); setReportSource(''); setError('');
    setMessage('已创建独立草稿；保存版本将建立新模型，不修改原模型。');
    return true;
  }

  async function action(kind: 'validate' | 'save' | 'export' | 'saveAs', format: 'jsonschema' | 'owl' | 'shacl' = 'jsonschema') {
    if (busyRef.current || !source) return;
    busyRef.current = true;
    const requestId = ++generation.current, snapshot = source, oldRecord = record;
    setBusy(kind); setError(''); setMessage('');
    try {
      if (kind === 'validate') {
        const result = await api<Report>('/models/validate', { method: 'POST', body: JSON.stringify({source: snapshot}) });
        if (!Array.isArray(result.classes) || !Array.isArray(result.relationships) || !Array.isArray(result.warnings)) throw new Error('校验响应结构不正确。');
        if (requestId === generation.current) { setReport(result); setReportSource(snapshot); setMessage('该快照已通过模型结构校验。'); }
      } else if (kind === 'save' || kind === 'saveAs') {
        const result = await api<Saved>('/models', { method: 'POST', body: JSON.stringify({source: snapshot, id: kind === 'saveAs' ? null : oldRecord?.id ?? null, expected_revision: kind === 'saveAs' ? 0 : oldRecord?.revision ?? 0}) });
        if (requestId === generation.current) { setRecord(result); setSavedSource(snapshot); setMessage(`${kind === 'saveAs' ? '已另存为独立模型。' : ''}快照已保存为版本 ${result.revision}；之后的编辑仍是未保存草稿。`); void refreshModels(); }
      } else {
        const result = await api<{content: string}>(`/models/export/${format}`, { method: 'POST', body: JSON.stringify({source: snapshot}) });
        if (requestId === generation.current) download(result.content, format === 'jsonschema' ? 'schema.json' : `${format}.ttl`, format === 'jsonschema' ? 'application/json' : 'text/turtle;charset=utf-8');
      }
    } catch (e) { if (requestId === generation.current) setError(e instanceof Error ? e.message : '操作失败，请重试。'); }
    finally { if (requestId === generation.current) { setBusy(''); busyRef.current = false; } }
  }

  async function openModel(id: string) {
    if (busyRef.current) return;
    busyRef.current = true;
    const requestId = ++generation.current;
    setBusy('load'); setError('');
    try {
      const result = await api<Saved & {source: string}>(`/models/${encodeURIComponent(id)}`);
      if (requestId === generation.current) {
        setSource(result.source); setSavedSource(result.source); setRecord(result);
        setReport(null); setReportSource(''); setMessage('已载入保存版本。');
      }
    } catch (e) { if (requestId === generation.current) setError(e instanceof Error ? e.message : '读取失败'); }
    finally { if (requestId === generation.current) { setBusy(''); busyRef.current = false; } }
  }
  return { source, setSource, dirty, record, models, report, reportStale: reportSource !== source,
    busy, message, error, loading, action, openModel, replaceDraft, importDirty, setImportDirty };
}
export type Workspace = ReturnType<typeof useWorkspace>;
