import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertTriangle, CalendarDays, CheckCircle2, ChevronDown, Download,
  Gauge, Info, RefreshCw, Wind, Zap,
} from 'lucide-react';
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceArea, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';
console.log("API BASE : ", API_BASE)
const fmt = (v, digits = 0) => v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const signed = (v) => v == null || !Number.isFinite(Number(v)) ? '—' : `${v > 0 ? '+' : ''}${fmt(v)}`;

async function get(path, signal) {
  const response = await fetch(`${API_BASE}${path}`, { signal, headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}`);
  return response.json();
}

function StatCard({ icon: Icon, label, value, unit, note, tone = '' }) {
  return <article className="stat-card"><div className="stat-top"><span>{label}</span><span className={`stat-icon ${tone}`}><Icon size={17} /></span></div><div className="stat-value">{value} <small>{unit}</small></div><p>{note}</p></article>;
}

function Panel({ title, subtitle, action, children, className = '' }) {
  return <section className={`panel ${className}`}><div className="panel-head"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>{children}</section>;
}

function EmptyState({ title, detail, onRetry }) {
  return <div className="empty-state"><AlertTriangle size={22} /><strong>{title}</strong><p>{detail}</p>{onRetry && <button className="btn secondary" onClick={onRetry}><RefreshCw size={14} /> Retry</button>}</div>;
}

function ForecastChart({ rows }) {
  const [visible, setVisible] = useState({ forecast_mw: true, actual_mw: true, band: true });
  const chartRows = useMemo(() => rows.map((r) => ({ ...r, label: r.start_time ? new Date(r.start_time).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/London' }) : r.slot })), [rows]);
  if (!chartRows.length) return <EmptyState title="No intervals for this day" detail="Choose another delivery day or check the ingestion job." />;
  const toggle = (key) => setVisible((old) => ({ ...old, [key]: !old[key] }));
  return <>
    <div className="chart-legend-controls">
      <button className={visible.forecast_mw ? 'legend-toggle selected forecast' : 'legend-toggle'} onClick={() => toggle('forecast_mw')}><span /> Forecast at cutoff</button>
      <button className={visible.actual_mw ? 'legend-toggle selected actual' : 'legend-toggle'} onClick={() => toggle('actual_mw')}><span /> Actual generation</button>
      {chartRows.some((r) => r.band_lo != null && r.band_hi != null) && <button className={visible.band ? 'legend-toggle selected band' : 'legend-toggle'} onClick={() => toggle('band')}><span /> Error range</button>}
    </div>
    <div className="chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartRows} margin={{ top: 10, right: 12, left: 0, bottom: 2 }}>
      <CartesianGrid strokeDasharray="3 4" vertical={false} stroke="var(--grid)" />
      <XAxis dataKey="label" minTickGap={32} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
      <YAxis width={58} tickFormatter={(v) => fmt(v)} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
      <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, color: 'var(--text)' }} formatter={(v, name) => [`${fmt(v)} MW`, name]} labelStyle={{ color: 'var(--muted)' }} />
      {visible.band && chartRows.some((r) => r.band_lo != null && r.band_hi != null) && chartRows.map((r, i) => r.band_lo != null && r.band_hi != null ? <ReferenceArea key={`band-${i}`} x1={r.label} x2={chartRows[i + 1]?.label ?? r.label} y1={r.band_lo} y2={r.band_hi} fill="#8db9e8" fillOpacity={0.18} strokeOpacity={0} /> : null)}
      {visible.forecast_mw && <Line type="monotone" dataKey="forecast_mw" name="Forecast at cutoff" stroke="#347fc3" strokeWidth={2.4} dot={false} connectNulls={false} activeDot={{ r: 4 }} />}
      {visible.actual_mw && <Line type="monotone" dataKey="actual_mw" name="Actual generation" stroke="#d4518b" strokeWidth={2.4} dot={false} connectNulls={false} activeDot={{ r: 4 }} />}
    </LineChart></ResponsiveContainer></div>
    <p className="chart-note">Times are displayed in UK local time. Confirm the backend has normalized timestamps and applies the agreed decision cutoff before selecting the forecast vintage.</p>
  </>;
}

function DataTable({ columns, rows, emptyText = 'No data available.' }) {
  const [sort, setSort] = useState({ key: columns[0]?.key, asc: true });
  const sorted = useMemo(() => [...rows].sort((a, b) => {
    const av = a[sort.key], bv = b[sort.key];
    if (av == null) return 1; if (bv == null) return -1;
    const result = typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv));
    return sort.asc ? result : -result;
  }), [rows, sort]);
  if (!rows.length) return <p className="table-empty">{emptyText}</p>;
  return <div className="table-scroll"><table><thead><tr>{columns.map((c) => <th key={c.key}><button onClick={() => setSort((s) => ({ key: c.key, asc: s.key === c.key ? !s.asc : true }))}>{c.label}{sort.key === c.key ? (sort.asc ? ' ↑' : ' ↓') : ''}</button></th>)}</tr></thead><tbody>{sorted.map((r, i) => <tr key={r.id ?? r.date ?? r.hour ?? r.level ?? r.horizon_from_h ?? i}>{columns.map((c) => <td key={c.key}>{c.render ? c.render(r[c.key], r) : (r[c.key] ?? '—')}</td>)}</tr>)}</tbody></table></div>;
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [date, setDate] = useState('');
  const [cutoff, setCutoff] = useState('');
  const [day, setDay] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('overview');
  const [range, setRange] = useState('month');

  const loadMeta = useCallback(async (signal) => {
    const m = await get('/api/meta', signal);
    setMeta(m);
    setDate((current) => current || m.dates?.[0] || '');
    setCutoff((current) => current || m.default_cutoff || Object.keys(m.cutoffs || {})[0] || '');
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadMeta(controller.signal).catch((e) => { if (e.name !== 'AbortError') setError(e.message); }).finally(() => setLoading(false));
    return () => controller.abort();
  }, [loadMeta]);

  const refresh = useCallback(async () => {
    if (!date || !cutoff) return;
    const controller = new AbortController();
    setLoading(true); setError('');
    try {
      const [d, m] = await Promise.all([
        get(`/api/day?date=${encodeURIComponent(date)}&cutoff=${encodeURIComponent(cutoff)}`, controller.signal),
        get(`/api/metrics?cutoff=${encodeURIComponent(cutoff)}`, controller.signal),
      ]);
      if (!Array.isArray(d.rows) || !d.summary || !m.summary) throw new Error('The API response is missing required fields (rows/summary).');
      setDay(d); setMetrics(m);
    } catch (e) { if (e.name !== 'AbortError') setError(e.message); }
    finally { setLoading(false); }
    return () => controller.abort();
  }, [date, cutoff]);

  useEffect(() => { refresh(); }, [refresh]);

  const exportCsv = () => {
    if (!day?.rows?.length) return;
    const cols = ['start_time', 'publish_time', 'forecast_mw', 'actual_mw', 'error_mw', 'band_lo', 'band_hi'];
    const quote = (v) => `"${String(v ?? '').replaceAll('"', '""')}"`;
    const csv = [cols.join(','), ...day.rows.map((r) => cols.map((c) => quote(r[c])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    const a = document.createElement('a'); a.href = url; a.download = `wind-forecast-${date}-cutoff-${cutoff}.csv`; a.click(); URL.revokeObjectURL(url);
  };

  if (loading && !meta) return <main className="page"><div className="loading-screen"><div className="brand-mark"><Wind /></div><h1>Wind Intelligence</h1><p>Loading forecast data…</p></div></main>;
  if (error && !meta) return <main className="page"><EmptyState title="Could not load dashboard configuration" detail={error} onRetry={() => window.location.reload()} /></main>;
  if (!meta) return null;

  const s = metrics?.summary ?? {}, ds = day?.summary ?? {}, band = s.band, baseline = s.baseline;
  const sourceIsReal = meta.source === 'elexon';
  const latestPublish = day?.rows?.filter((r) => r.publish_time).map((r) => r.publish_time).sort().at(-1);
  const columns = [
    { key: 'level', label: 'Forecast level' }, { key: 'n', label: 'Periods' },
    { key: 'bias', label: 'Bias (MW)', render: (v) => signed(v) },
    { key: 'mae', label: 'MAE (MW)', render: (v) => fmt(v) },
    { key: 'rmse', label: 'RMSE (MW)', render: (v) => fmt(v) },
  ];
  const hourColumns = [{ key: 'hour', label: 'Hour (UK)', render: (v) => `${String(v).padStart(2, '0')}:00` }, { key: 'n', label: 'Periods' }, { key: 'bias', label: 'Bias', render: (v) => signed(v) }, { key: 'mae', label: 'MAE', render: (v) => fmt(v) }, { key: 'rmse', label: 'RMSE', render: (v) => fmt(v) }];
  const horizonColumns = [{ key: 'horizon_from_h', label: 'Lead time (h)', render: (v, r) => `${v}–${r.horizon_to_h}` }, { key: 'n', label: 'Periods' }, { key: 'bias', label: 'Bias', render: (v) => signed(v) }, { key: 'mae', label: 'MAE', render: (v) => fmt(v) }, { key: 'rmse', label: 'RMSE', render: (v) => fmt(v) }];
  const dailyColumns = [{ key: 'date', label: 'Delivery day' }, { key: 'mae', label: 'MAE (MW)', render: (v) => fmt(v) }, { key: 'bias', label: 'Bias (MW)', render: (v) => signed(v) }, { key: 'band_coverage_pct', label: 'Band coverage', render: (v) => v == null ? '—' : `${fmt(v, 1)}%` }];

  return <main className="page">
    <header className="topbar"><div className="brand"><div className="brand-mark"><Wind size={21} /></div><div><strong>Wind Intelligence</strong><span>Forecast performance & decision support</span></div></div><div className="top-status"><span className={`status-dot ${sourceIsReal ? 'live' : ''}`} />{sourceIsReal ? 'Elexon source' : 'Demo / non-Elexon source'}<span className="status-divider" />GB · Half-hourly</div></header>
    <div className="content">
      <div className="page-heading"><div><div className="eyebrow">Market analytics / wind generation</div><h1>Forecast performance monitor</h1><p>Understand what was available at decision time—and how it compared with delivered generation.</p></div><div className="heading-actions"><button className="btn secondary" onClick={refresh} disabled={loading}><RefreshCw size={15} className={loading ? 'spin' : ''} /> Refresh</button><button className="btn primary" onClick={exportCsv} disabled={!day?.rows?.length}><Download size={15} /> Export CSV</button></div></div>
      {!sourceIsReal && <div className="notice warning"><AlertTriangle size={17} /><div><strong>Demo or non-Elexon dataset</strong><span>This dashboard does not prove that the values came from Elexon. Run ingestion and verify source metadata before interpreting results.</span></div></div>}
      {meta.data_gaps?.length > 0 && <div className="notice warning"><AlertTriangle size={17} /><div><strong>Data gaps detected</strong><span>{meta.data_gaps.length} delivery day(s) contain missing forecast or actual intervals. Missing periods are not treated as zero.</span></div></div>}
      {error && <div className="notice error"><AlertTriangle size={17} /><div><strong>Some data could not be loaded</strong><span>{error}</span></div><button className="btn secondary" onClick={refresh}>Try again</button></div>}
      <section className="filters"><div className="filter-title"><CalendarDays size={17} /><strong>Analysis settings</strong></div><label className="field"><span>Delivery day</span><select value={date} onChange={(e) => setDate(e.target.value)}>{(meta.dates ?? []).map((d) => <option key={d} value={d}>{d}</option>)}</select></label><label className="field"><span>Decision cutoff · UK time</span><select value={cutoff} onChange={(e) => setCutoff(e.target.value)}>{Object.entries(meta.cutoffs ?? {}).map(([k, v]) => <option key={k} value={k}>{k} — {v}</option>)}</select></label><label className="field"><span>Summary range</span><select value={range} onChange={(e) => setRange(e.target.value)}><option value="month">All available days</option><option value="day">Selected day only</option></select></label><div className="filter-context"><Info size={15} /><span>Use a cutoff that reflects the actual purchasing decision—not a convenient publication time.</span></div></section>
      <nav className="tabs" aria-label="Dashboard sections">{[['overview', 'Overview'], ['errors', 'Error analysis'], ['quality', 'Data quality']].map(([key, label]) => <button key={key} className={tab === key ? 'tab active' : 'tab'} onClick={() => setTab(key)}>{label}</button>)}</nav>
      {loading && day && <div className="loading-strip"><span className="spinner" /> Updating data…</div>}
      {tab === 'overview' && <>
        <div className="stats-grid"><StatCard icon={Gauge} label="Mean absolute error" value={fmt(range === 'day' ? ds.mae : s.mae)} unit="MW" note="Average absolute forecast miss" tone="blue" /><StatCard icon={Activity} label="Forecast bias" value={signed(range === 'day' ? ds.bias : s.bias)} unit="MW" note="Positive means over-forecast" tone="pink" /><StatCard icon={Zap} label="Root mean squared error" value={fmt(range === 'day' ? ds.rmse : s.rmse)} unit="MW" note="Penalises larger errors more heavily" tone="amber" /><StatCard icon={CheckCircle2} label="Matched half-hours" value={`${fmt(range === 'day' ? ds.n_valid : s.n_valid)} / ${fmt(range === 'day' ? ds.n_expected : s.n_expected)}`} unit="" note="Forecast and actual both present" tone="green" /></div>
        <Panel title="Forecast vs actual generation" subtitle={`${date || 'Selected day'} · half-hourly values · MW`} action={<span className="pill">Vintage-aware comparison</span>} className="chart-panel">{day ? <ForecastChart rows={day.rows} /> : <EmptyState title="Daily data unavailable" detail="The API did not return the selected delivery day." onRetry={refresh} />}</Panel>
        <div className="two-col"><Panel title="Error by forecast level" subtitle="Find forecast ranges where errors are larger"><DataTable columns={columns} rows={metrics?.by_level ?? []} /></Panel><Panel title="Error by hour of day" subtitle="Times shown in UK local time"><DataTable columns={hourColumns} rows={metrics?.by_hour ?? []} /></Panel></div>
        <Panel title="Daily accuracy trend" subtitle="Compare error and systematic over/under-forecasting by delivery day"><DataTable columns={dailyColumns} rows={metrics?.daily ?? []} /></Panel>
      </>}
      {tab === 'errors' && <><div className="stats-grid compact"><StatCard icon={Gauge} label="90th percentile absolute error" value={fmt(s.p90_abs)} unit="MW" note="90% of absolute errors are at or below this value" /><StatCard icon={Activity} label="Over-forecast share" value={s.over_forecast_pct == null ? '—' : `${fmt(s.over_forecast_pct, 1)}%`} unit="" note="Share of matched periods with positive error" /><StatCard icon={Zap} label="Skill vs 2-day persistence" value={baseline?.skill == null ? '—' : `${fmt(100 * baseline.skill, 1)}%`} unit="" note="Positive means lower MAE than baseline" /><StatCard icon={CheckCircle2} label="Error-band coverage" value={band?.coverage_pct == null ? '—' : `${fmt(band.coverage_pct, 1)}%`} unit="" note="Target depends on the band definition" /></div><Panel title="Error by forecast lead time" subtitle="Verify that lead time is computed from delivery start and selected publication time"><DataTable columns={horizonColumns} rows={metrics?.by_horizon ?? []} /></Panel><Panel title="How to interpret the metrics"><div className="metric-explainer"><div><strong>MAE</strong><p>Average absolute error in MW. Easy to explain and compare.</p></div><div><strong>RMSE</strong><p>Weights large misses more heavily than MAE.</p></div><div><strong>Bias</strong><p>Mean forecast minus actual. Positive indicates over-forecasting.</p></div><div><strong>Skill score</strong><p>1 − MAE(forecast) / MAE(baseline). A negative score means the baseline did better.</p></div></div><p className="footnote">Avoid using MAPE as the primary metric if actual wind generation can be near zero. One month of data is a limited evaluation sample; use a separate validation period before making strong claims.</p></Panel></>}
      {tab === 'quality' && <><Panel title="Data coverage" subtitle="Expected periods and matched observations"><div className="quality-grid"><div><span>Delivery days in dataset</span><strong>{meta.dates?.length ?? '—'}</strong></div><div><span>Selected-day valid slots</span><strong>{fmt(ds.n_valid)} / {fmt(ds.n_expected)}</strong></div><div><span>Latest publication shown</span><strong>{latestPublish ? new Date(latestPublish).toLocaleString('en-GB', { timeZone: 'UTC', dateStyle: 'medium', timeStyle: 'short' }) + ' UTC' : '—'}</strong></div><div><span>Source flag</span><strong>{sourceIsReal ? 'Elexon' : 'Demo / other'}</strong></div></div></Panel><Panel title="Production-readiness checklist" subtitle="Confirm these before using results for procurement"><ul className="check-list"><li>Historical WINDFOR publication vintages are preserved and available for each cutoff.</li><li>Forecast selection is based on publish time ≤ decision cutoff, not the latest forecast currently available.</li><li>Forecast and actual rows are joined by delivery-period start time in a consistent timezone.</li><li>Missing intervals and duplicate source records are handled explicitly and audibly.</li><li>Forecast error bands are fitted without using the delivery day being evaluated.</li><li>Source URL, retrieval timestamp, units, timezone and transformation version are recorded.</li></ul></Panel></>}
      <footer className="footer"><span>Wind Intelligence · Decision-support prototype</span><span>Not a procurement recommendation · Verify source data before use</span></footer>
    </div>
  </main>;
}
