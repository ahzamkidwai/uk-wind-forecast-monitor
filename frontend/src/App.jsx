import { useEffect, useState } from "react";

const f0 = (x) => (x == null ? "–" : Math.round(x).toLocaleString("en-GB"));
const f1 = (x) => (x == null ? "–" : x.toFixed(1));
const get = (u) => fetch(u).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${u}: ${r.status}`))));

function Chart({ rows }) {
  const W = 800, H = 280, m = { l: 52, r: 8, t: 8, b: 22 };
  const vals = rows.flatMap((r) => [r.forecast_mw, r.actual_mw, r.band_lo, r.band_hi]).filter((v) => v != null);
  if (!vals.length) return <p>No data for this day.</p>;
  const ymax = Math.max(...vals) * 1.05, n = rows.length;
  const x = (i) => m.l + (i / (n - 1)) * (W - m.l - m.r);
  const y = (v) => H - m.b - (v / ymax) * (H - m.t - m.b);
  const line = (k) => {
    let d = "", pen = false;
    rows.forEach((r, i) => { const v = r[k]; if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${x(i)},${y(v)}`; pen = true; });
    return d;
  };
  const bandRows = rows.map((r, i) => ({ i, lo: r.band_lo, hi: r.band_hi })).filter((b) => b.lo != null);
  const band = bandRows.length
    ? "M" + bandRows.map((b) => `${x(b.i)},${y(b.hi)}`).join("L") + "L" + [...bandRows].reverse().map((b) => `${x(b.i)},${y(b.lo)}`).join("L") + "Z" : "";
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * ymax);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Forecast, actual and error band for the delivery day">
      {ticks.map((t) => <g key={t}><line x1={m.l} x2={W - m.r} y1={y(t)} y2={y(t)} stroke="#eee" /><text x={m.l - 4} y={y(t) + 4} fontSize="10" textAnchor="end">{f0(t)}</text></g>)}
      {[0, 6, 12, 18, 23].map((h) => <text key={h} x={x(h * 2)} y={H - 6} fontSize="10" textAnchor="middle">{String(h).padStart(2, "0")}:00</text>)}
      <path d={band} fill="#9ec5fe" opacity="0.45" />
      <path d={line("forecast_mw")} fill="none" stroke="#0b5ed7" strokeWidth="2" />
      <path d={line("actual_mw")} fill="none" stroke="#d63384" strokeWidth="2" />
      <text x={m.l + 6} y={m.t + 12} fontSize="11"><tspan fill="#0b5ed7">■ forecast (as of cutoff)</tspan>  <tspan fill="#d63384">■ actual</tspan>  <tspan fill="#6ea8fe">■ P10–P90 band</tspan></text>
    </svg>
  );
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [date, setDate] = useState("");
  const [cutoff, setCutoff] = useState("09:20");
  const [day, setDay] = useState(null);
  const [mx, setMx] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => { get("/api/meta").then((m) => { setMeta(m); setDate(m.dates[0]); setCutoff(m.default_cutoff); }).catch((e) => setErr(e.message)); }, []);
  useEffect(() => {
    if (!date) return;
    setErr("");
    Promise.all([get(`/api/day?date=${date}&cutoff=${cutoff}`), get(`/api/metrics?cutoff=${cutoff}`)])
      .then(([d, m]) => { setDay(d); setMx(m); }).catch((e) => setErr(e.message));
  }, [date, cutoff]);

  if (err) return <main><div className="warn">Could not load data: {err}</div></main>;
  if (!meta || !day || !mx) return <main>Loading…</main>;
  const s = mx.summary, ds = day.summary, b = s.band, bl = s.baseline;
  const last = day.rows.find((r) => r.publish_time);

  return (
    <main>
      <h1>UK wind generation: day-ahead forecast vs actual</h1>
      <div className="note">Elexon WINDFOR vs FUELHH (WIND). Delivery days {meta.dates[0]} to {meta.dates.at(-1)}.</div>
      {meta.source !== "elexon" && <div className="warn"><b>Synthetic demo data</b> – not real Elexon data. Run the ingest step to load the real dataset.</div>}
      {meta.data_gaps.length > 0 && <div className="warn">Data gaps on {meta.data_gaps.length} day(s): {meta.data_gaps.map((g) => `${g.date} (${g.forecast_slots}/48 forecast, ${g.actual_slots}/48 actual)`).join("; ")}</div>}

      <div className="bar">
        <label>Delivery day<select value={date} onChange={(e) => setDate(e.target.value)}>{meta.dates.map((d) => <option key={d}>{d}</option>)}</select></label>
        <label>Decision cutoff (UK time, day before)<select value={cutoff} onChange={(e) => setCutoff(e.target.value)}>{Object.entries(meta.cutoffs).map(([k, v]) => <option key={k} value={k}>{k} – {v}</option>)}</select></label>
      </div>

      <h2>Forecast available at the decision, {date}</h2>
      <Chart rows={day.rows} />
      <div className="note">Forecast = latest WINDFOR publish at or before {cutoff} on the previous day. Band = P10–P90 of past errors at similar forecast levels, fitted without this day.</div>
      <div className="kpi" style={{ marginTop: 8 }}>
        <div><span>Day MAE (MW)</span><b>{f0(ds.mae)}</b></div>
        <div><span>Day bias (MW, + = over-forecast)</span><b>{f0(ds.bias)}</b></div>
        <div><span>Slots with forecast and actual</span><b>{ds.n_valid}/{ds.n_expected}</b></div>
        <div><span>Forecast issued (UTC)</span><b style={{ fontSize: 14 }}>{last ? last.publish_time.slice(0, 16).replace("T", " ") : "–"}</b></div>
      </div>

      <h2>Forecast accuracy, all delivery days (cutoff {cutoff})</h2>
      <div className="kpi">
        <div><span>MAE (MW)</span><b>{f0(s.mae)}</b></div>
        <div><span>RMSE (MW)</span><b>{f0(s.rmse)}</b></div>
        <div><span>Bias (MW)</span><b>{f0(s.bias)}</b></div>
        <div><span>90% of errors within (MW)</span><b>{f0(s.p90_abs)}</b></div>
        <div><span>MAE / mean actual</span><b>{f1(s.nmae_pct)}%</b></div>
        <div><span>Over-forecast share</span><b>{f1(s.over_forecast_pct)}%</b></div>
        <div><span>Skill vs 2-day persistence</span><b>{bl ? f1(100 * bl.skill) + "%" : "–"}</b></div>
        <div><span>Band coverage (target 80%)</span><b>{b ? f1(b.coverage_pct) + "%" : "–"}</b></div>
      </div>
      <div className="note">Compared on {s.n_valid} of {s.n_expected} half-hours. Skill = 1 − MAE(forecast)/MAE(persistence); persistence uses the actual 48 h earlier, which is known at any cutoff. Errors are in-sample for one month.</div>

      <h2>Error by forecast level</h2>
      <table><thead><tr><th>Level</th><th>Forecast range (MW)</th><th>n</th><th>Bias</th><th>MAE</th><th>RMSE</th></tr></thead>
        <tbody>{mx.by_level.map((r) => <tr key={r.level}><td>{r.level}</td><td>{f0(r.forecast_from)}–{f0(r.forecast_to)}</td><td>{r.n}</td><td>{f0(r.bias)}</td><td>{f0(r.mae)}</td><td>{f0(r.rmse)}</td></tr>)}</tbody></table>

      <h2>Error by hour of day (UK)</h2>
      <table><thead><tr><th>Hour</th><th>n</th><th>Bias</th><th>MAE</th><th>RMSE</th></tr></thead>
        <tbody>{mx.by_hour.map((r) => <tr key={r.hour}><td>{String(r.hour).padStart(2, "0")}:00</td><td>{r.n}</td><td>{f0(r.bias)}</td><td>{f0(r.mae)}</td><td>{f0(r.rmse)}</td></tr>)}</tbody></table>

      <h2>Error by forecast lead time</h2>
      <table><thead><tr><th>Lead (h)</th><th>n</th><th>Bias</th><th>MAE</th><th>RMSE</th></tr></thead>
        <tbody>{mx.by_horizon.map((r) => <tr key={r.horizon_from_h}><td>{r.horizon_from_h}–{r.horizon_to_h}</td><td>{r.n}</td><td>{f0(r.bias)}</td><td>{f0(r.mae)}</td><td>{f0(r.rmse)}</td></tr>)}</tbody></table>

      <h2>Daily</h2>
      <table><thead><tr><th>Day</th><th>MAE</th><th>Bias</th><th>Band cover %</th></tr></thead>
        <tbody>{mx.daily.map((r) => <tr key={r.date}><td>{r.date}</td><td>{f0(r.mae)}</td><td>{f0(r.bias)}</td><td>{f1(r.band_coverage_pct)}</td></tr>)}</tbody></table>
    </main>
  );
}
