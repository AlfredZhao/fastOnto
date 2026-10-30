import { useEffect, useMemo, useRef, useState, type PointerEvent } from 'react';
import { ListPlus, Move, Network, RotateCcw } from 'lucide-react';
import type { Report } from '../api';

type Point = {x: number; y: number};

function layoutKey(sha256: string) { return `fastonto.ontology-layout.v1.${sha256}`; }
function loadLayout(sha256: string, names: string[]): Record<string, Point> {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(layoutKey(sha256)) ?? '{}');
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    return Object.fromEntries(names.flatMap(name => {
      const point = (value as Record<string, unknown>)[name];
      return point && typeof point === 'object' && typeof (point as Point).x === 'number' && typeof (point as Point).y === 'number'
        ? [[name, {x: Math.max(8, (point as Point).x), y: Math.max(8, (point as Point).y)}]] : [];
    }));
  } catch { return {}; }
}

export default function OntologyCanvas({report}: {report: Report}) {
  const [positions, setPositions] = useState<Record<string, Point>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [notice, setNotice] = useState('');
  const drag = useRef<{name: string; dx: number; dy: number} | null>(null);
  const positionsRef = useRef<Record<string, Point>>({});
  const canvas = useRef<HTMLDivElement>(null);
  const layout = useMemo(() => Object.fromEntries(report.classes.map((item, index) => [item.name, {
    x: 28 + (index % 3) * 250, y: 42 + Math.floor(index / 3) * 205,
  }])), [report]);
  useEffect(() => {
    const saved = loadLayout(report.sha256, report.classes.map(item => item.name));
    positionsRef.current = saved; setPositions(saved);
    setExpanded({}); setNotice('');
  }, [report.sha256, report.classes]);
  const point = (name: string) => positions[name] ?? layout[name];
  function start(event: PointerEvent<HTMLButtonElement>, name: string) {
    const bounds = canvas.current?.getBoundingClientRect();
    if (!bounds) return;
    const current = point(name);
    drag.current = {name, dx: event.clientX - bounds.left - current.x, dy: event.clientY - bounds.top - current.y};
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function move(event: PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    const bounds = canvas.current?.getBoundingClientRect();
    if (!bounds) return;
    const next = {x: Math.max(8, event.clientX - bounds.left - drag.current.dx), y: Math.max(8, event.clientY - bounds.top - drag.current.dy)};
    setPositions(previous => {
      const saved = {...previous, [drag.current!.name]: next};
      positionsRef.current = saved;
      return saved;
    });
  }
  function end() {
    if (!drag.current) return;
    drag.current = null;
    try { localStorage.setItem(layoutKey(report.sha256), JSON.stringify(positionsRef.current)); setNotice('布局已自动保存到此浏览器。'); }
    catch { setNotice('浏览器未允许保存布局；本次会话内仍可继续调整。'); }
  }
  function reset() {
    try { localStorage.removeItem(layoutKey(report.sha256)); } catch {}
    positionsRef.current = {}; setPositions({}); setNotice('已恢复默认布局。');
  }
  return <section className="panel ontology-canvas-panel" aria-label="本体关系图">
    <div className="panel-title"><Network size={16}/><h2>本体关系图</h2><span className="caption">拖拽后自动保存到当前浏览器；模型定义仍以 LinkML 源码为准</span><button className="canvas-reset" type="button" onClick={reset}><RotateCcw size={13}/>恢复默认</button></div>
    {notice && <div className="canvas-notice" role="status">{notice}</div>}
    <div ref={canvas} className="ontology-canvas" onPointerMove={move} onPointerUp={end} onPointerCancel={end}>
      <svg aria-hidden="true" className="ontology-edges" viewBox="0 0 900 520" preserveAspectRatio="none">
        {report.relationships.map((relation, index) => {
          const source = point(relation.source), target = point(relation.target);
          if (!source || !target) return null;
          return <line key={`${relation.source}-${relation.target}-${index}`} x1={source.x + 105} y1={source.y + 72} x2={target.x + 105} y2={target.y + 72}/>;
        })}
      </svg>
      {report.relationships.map((relation, index) => {
        const source = point(relation.source), target = point(relation.target);
        if (!source || !target) return null;
        return <span className="ontology-edge-label" key={`${relation.label}-${index}`} style={{left: (source.x + target.x) / 2 + 105, top: (source.y + target.y) / 2 + 72}}>{relation.label}</span>;
      })}
      {report.classes.map(item => {
        const position = point(item.name);
        return <article className="ontology-node" key={item.name} style={{left: position.x, top: position.y}}>
          <header><strong>{item.title}</strong><code>{item.name}</code><button type="button" aria-label={`拖拽 ${item.title}`} onPointerDown={event => start(event, item.name)}><Move size={14}/></button></header>
          <ul>{item.slots.slice(0, expanded[item.name] ? undefined : 4).map(slot => <li key={slot.name}><span>{slot.title}</span><code>{slot.range}</code></li>)}</ul>
          {item.slots.length > 4 && <button className="node-expand" type="button" onClick={() => setExpanded(current => ({...current, [item.name]: !current[item.name]}))}><ListPlus size={12}/>{expanded[item.name] ? '收起属性' : `展开其余 ${item.slots.length - 4} 个属性`}</button>}
        </article>;
      })}
      {!report.relationships.length && <p className="ontology-canvas-empty">当前模型没有对象关系；可先在 LinkML 中定义类之间的属性关系。</p>}
    </div>
  </section>;
}
