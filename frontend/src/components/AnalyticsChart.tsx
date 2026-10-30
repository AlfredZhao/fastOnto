import { useMemo, useState } from 'react';
import { BarChart3, CircleDollarSign, LineChart, PieChart } from 'lucide-react';

type ChartResult = {
  metric: {code: string; title: string};
  parameters: {dimension: string | null; period: {label: string; start: string; end: string} | null};
  columns: string[];
  rows: (string | number | null)[][];
};
type ChartKind = 'auto' | 'bar' | 'line' | 'donut';
type Point = {label: string; value: number; raw: string | number | null};
const colors = ['#4f8cff', '#45c3a6', '#f6ad55', '#bb86fc', '#f1788b', '#62b6e8', '#9dc65a', '#d6a4ec'];

function number(value: string | number | null) { const valueAsNumber = typeof value === 'number' ? value : Number(value); return Number.isFinite(valueAsNumber) ? valueAsNumber : 0; }
function readable(value: number, metric: string) { return new Intl.NumberFormat('zh-CN', {maximumFractionDigits: 2}).format(value) + (metric === 'sales_amount' ? ' 元' : ''); }
function autoKind(result: ChartResult): ChartKind { return result.parameters.dimension === 'month' ? 'line' : result.parameters.dimension ? 'bar' : 'auto'; }

export default function AnalyticsChart({result}: {result: ChartResult}) {
  const [selected, setSelected] = useState<ChartKind>('auto');
  const points = useMemo<Point[]>(() => result.rows.map(row => ({label: result.parameters.dimension ? String(row[0] ?? '—') : result.metric.title, value: number(row[result.parameters.dimension ? 1 : 0]), raw: row[result.parameters.dimension ? 1 : 0]})), [result]);
  const kind = selected === 'auto' ? autoKind(result) : selected;
  const period = result.parameters.period?.label ?? '全部可见期间';
  if (!points.length) return null;
  return <section className="analytics-chart" aria-label={`${result.metric.title}图表`}>
    <div className="analytics-chart-heading"><div><strong>{result.metric.title}</strong><small>{period} · {result.parameters.dimension ? result.columns[0] : '总览'}</small></div><div className="chart-switch" role="group" aria-label="图表类型"><button className={selected === 'auto' ? 'active' : ''} onClick={() => setSelected('auto')}>自动</button>{result.parameters.dimension && <><button className={selected === 'bar' ? 'active' : ''} aria-label="柱形图" onClick={() => setSelected('bar')}><BarChart3 size={14}/></button><button className={selected === 'line' ? 'active' : ''} aria-label="折线图" onClick={() => setSelected('line')}><LineChart size={14}/></button><button className={selected === 'donut' ? 'active' : ''} aria-label="环图" onClick={() => setSelected('donut')}><PieChart size={14}/></button></>}</div></div>
    {kind === 'auto' ? <Kpi point={points[0]} metric={result.metric.code}/> : kind === 'bar' ? <Bars points={points} metric={result.metric.code}/> : kind === 'line' ? <Line points={points} metric={result.metric.code}/> : <Donut points={points} metric={result.metric.code}/>}
  </section>;
}

function Kpi({point, metric}: {point: Point; metric: string}) { return <div className="chart-kpi"><CircleDollarSign size={20}/><strong>{readable(point.value, metric)}</strong><span>{metric === 'sales_amount' ? '销售额（人民币）' : '销售数量'}</span></div>; }
function Bars({points, metric}: {points: Point[]; metric: string}) { const max = Math.max(...points.map(item => Math.abs(item.value)), 1); const height = Math.max(150, points.length * 36 + 22); return <svg className="chart-svg chart-bars" viewBox={`0 0 720 ${height}`} role="img" aria-label="柱形图">{points.map((item, index) => {const y = index * 36 + 8; const width = Math.max(2, Math.abs(item.value) / max * 430); return <g key={`${item.label}-${index}`}><title>{`${item.label}: ${readable(item.value, metric)}`}</title><text x="0" y={y + 16}>{item.label}</text><rect x="180" y={y} width={width} height="22" rx="4" fill="var(--accent)"/><text x={190 + width} y={y + 16}>{readable(item.value, metric)}</text></g>;})}</svg>; }
function Line({points, metric}: {points: Point[]; metric: string}) { const max = Math.max(...points.map(item => item.value), 1), min = Math.min(...points.map(item => item.value), 0), spread = Math.max(max - min, 1); const width = Math.max(620, points.length * 84); const coords = points.map((item, index) => ({x: 42 + index * ((width - 72) / Math.max(points.length - 1, 1)), y: 178 - ((item.value - min) / spread * 138), ...item})); return <div className="chart-scroll"><svg className="chart-svg chart-line" viewBox={`0 0 ${width} 220`} role="img" aria-label="折线图"><line x1="42" y1="180" x2={width - 20} y2="180"/><line x1="42" y1="25" x2="42" y2="180"/><polyline points={coords.map(item => `${item.x},${item.y}`).join(' ')} fill="none" stroke="var(--accent)" strokeWidth="3"/>{coords.map(item => <g key={item.label}><title>{`${item.label}: ${readable(item.value, metric)}`}</title><circle cx={item.x} cy={item.y} r="4" fill="var(--accent)"/><text x={item.x} y="204" textAnchor="middle">{item.label}</text></g>)}<text x="46" y="18">{readable(max, metric)}</text></svg></div>; }
function Donut({points, metric}: {points: Point[]; metric: string}) { const visible = points.slice(0, 8); const total = visible.reduce((sum, item) => sum + Math.max(0, item.value), 0); if (!total) return <div className="empty compact">没有可绘制的非负数值。</div>; let offset = 0; return <div className="chart-donut"><svg viewBox="0 0 180 180" role="img" aria-label="环图"><circle cx="90" cy="90" r="58" fill="none" stroke="var(--border)" strokeWidth="24"/>{visible.map((item, index) => {const share = item.value / total; const dash = `${share * 364.42} ${364.42 - share * 364.42}`; const value = <circle key={item.label} cx="90" cy="90" r="58" fill="none" stroke={colors[index]} strokeWidth="24" strokeDasharray={dash} strokeDashoffset={-offset} transform="rotate(-90 90 90)"/>; offset += share * 364.42; return value;})}<text x="90" y="87" textAnchor="middle">合计</text><text x="90" y="105" textAnchor="middle">{readable(total, metric)}</text></svg><ul>{visible.map((item, index) => <li key={item.label}><i style={{background: colors[index]}}/>{item.label}<span>{readable(item.value, metric)}</span></li>)}</ul></div>; }
