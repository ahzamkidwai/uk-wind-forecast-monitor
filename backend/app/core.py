"""Pure, dependency-light logic: point-in-time forecast selection and error metrics.

Conventions
- All timestamps are tz-aware UTC internally; "delivery day" and cutoffs use Europe/London.
- error = forecast - actual (positive = over-forecast, i.e. wind came in below forecast).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LONDON = "Europe/London"
SLOT = pd.Timedelta(minutes=30)
CUTOFF_OPTIONS = {
    "09:20": "EPEX GB day-ahead (hourly) gate closure",
    "09:50": "N2EX day-ahead (hourly) gate closure",
    "15:30": "EPEX GB day-ahead (30-min) gate closure",
}


def day_bounds_utc(delivery_date) -> tuple[pd.Timestamp, pd.Timestamp]:
    d = pd.Timestamp(delivery_date).normalize().tz_localize(None)
    lo = d.tz_localize(LONDON).tz_convert("UTC")
    hi = (d + pd.Timedelta(days=1)).tz_localize(LONDON).tz_convert("UTC")
    return lo, hi


def cutoff_utc(delivery_date, hhmm: str) -> pd.Timestamp:
    """Decision cutoff: HH:MM London time on the day BEFORE delivery, as UTC."""
    h, m = (int(x) for x in hhmm.split(":"))
    d = pd.Timestamp(delivery_date).normalize().tz_localize(None) - pd.Timedelta(days=1)
    return (d + pd.Timedelta(hours=h, minutes=m)).tz_localize(LONDON).tz_convert("UTC")


def asof_forecast(fc: pd.DataFrame, delivery_date, hhmm: str) -> pd.DataFrame:
    """For every half-hour of the delivery day, the latest forecast with publish_time <= cutoff.

    fc columns: start_time, publish_time, forecast_mw (tz-aware UTC).
    Always returns the full set of slots (NaN where no qualifying forecast exists).
    """
    lo, hi = day_bounds_utc(delivery_date)
    cut = cutoff_utc(delivery_date, hhmm)
    slots = pd.DatetimeIndex(pd.date_range(lo, hi, freq=SLOT, inclusive="left"), name="start_time")
    sub = fc[(fc.start_time >= lo) & (fc.start_time < hi) & (fc.publish_time <= cut)]
    sub = (
        sub.sort_values(["start_time", "publish_time"])
        .drop_duplicates("start_time", keep="last")
        .set_index("start_time")[["publish_time", "forecast_mw"]]
    )
    out = sub.reindex(slots).reset_index()
    out["horizon_h"] = (out.start_time - out.publish_time).dt.total_seconds() / 3600
    out["cutoff"] = cut
    return out


def build_panel(fc: pd.DataFrame, act: pd.DataFrame, dates, hhmm: str) -> pd.DataFrame:
    """One row per (delivery date, half-hour) with forecast-as-of-cutoff, actual, error, baseline."""
    act_s = act.drop_duplicates("start_time", keep="last").set_index("start_time")["actual_mw"]
    parts = []
    for d in dates:
        day = asof_forecast(fc, d, hhmm)
        day["delivery_date"] = pd.Timestamp(d).strftime("%Y-%m-%d")
        parts.append(day)
    p = pd.concat(parts, ignore_index=True)
    p["actual_mw"] = act_s.reindex(p.start_time).to_numpy()
    # 2-day persistence: actual 48h earlier. Always known at any cutoff on D-1 (it lies in D-2).
    p["persistence_mw"] = act_s.reindex(p.start_time - pd.Timedelta(hours=48)).to_numpy()
    p["error_mw"] = p.forecast_mw - p.actual_mw
    p["on_grid"] = p.start_time.isin(pd.DatetimeIndex(fc.start_time.unique()))
    p["hour"] = p.start_time.dt.tz_convert(LONDON).dt.hour
    return p


def _m(err: pd.Series) -> dict:
    e = err.dropna()
    if e.empty:
        return dict(n=0, bias=None, mae=None, rmse=None)
    return dict(n=int(len(e)), bias=float(e.mean()), mae=float(e.abs().mean()),
                rmse=float(np.sqrt((e ** 2).mean())))


def fit_band(train: pd.DataFrame, lo_q=0.10, hi_q=0.90, min_n=20) -> dict:
    """Empirical residual (actual - forecast) quantiles per forecast-level tercile."""
    t = train.dropna(subset=["forecast_mw", "actual_mw"])
    resid_all = (t.actual_mw - t.forecast_mw)
    edges = np.quantile(t.forecast_mw, [1 / 3, 2 / 3]) if len(t) >= 3 else np.array([np.inf, np.inf])
    pooled = np.quantile(resid_all, [lo_q, hi_q]) if len(t) else np.array([0.0, 0.0])
    buckets = np.searchsorted(edges, t.forecast_mw.to_numpy(), side="right")
    q = []
    for b in range(3):
        r = resid_all.to_numpy()[buckets == b]
        q.append(tuple(np.quantile(r, [lo_q, hi_q])) if len(r) >= min_n else tuple(pooled))
    return dict(edges=edges, q=q, lo_q=lo_q, hi_q=hi_q)


def apply_band(model: dict, forecast: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    f = forecast.to_numpy(dtype=float)
    b = np.searchsorted(model["edges"], np.nan_to_num(f), side="right")
    lo_off = np.array([model["q"][i][0] for i in b])
    hi_off = np.array([model["q"][i][1] for i in b])
    lo = np.maximum(f + lo_off, 0.0)
    hi = f + hi_off
    lo[np.isnan(f)] = np.nan
    hi[np.isnan(f)] = np.nan
    return lo, hi


def add_band_loo(panel: pd.DataFrame, lo_q=0.10, hi_q=0.90) -> pd.DataFrame:
    """Out-of-sample band: each delivery day's band is fitted on all OTHER days."""
    p = panel.copy()
    p["band_lo"] = np.nan
    p["band_hi"] = np.nan
    for d, idx in p.groupby("delivery_date").groups.items():
        train = p[p.delivery_date != d]
        if train.dropna(subset=["forecast_mw", "actual_mw"]).empty:
            continue
        lo, hi = apply_band(fit_band(train, lo_q, hi_q), p.loc[idx, "forecast_mw"])
        p.loc[idx, "band_lo"] = lo
        p.loc[idx, "band_hi"] = hi
    return p


def summarise(p: pd.DataFrame) -> dict:
    """Accuracy summary for a panel that already has band columns."""
    # expected = len(p)
    expected = int(p["on_grid"].sum()) if "on_grid" in p else len(p)
    v = p.dropna(subset=["forecast_mw", "actual_mw"])
    out = dict(n_expected=expected, n_valid=len(v),
               coverage_pct=100 * len(v) / expected if expected else None)
    out.update(_m(v.error_mw))
    ae = v.error_mw.abs()
    out["p50_abs"] = float(ae.quantile(0.5)) if len(v) else None
    out["p90_abs"] = float(ae.quantile(0.9)) if len(v) else None
    out["mean_actual"] = float(v.actual_mw.mean()) if len(v) else None
    out["nmae_pct"] = 100 * out["mae"] / out["mean_actual"] if len(v) and out["mean_actual"] else None
    c = v.dropna(subset=["persistence_mw"])
    if len(c):
        mae_f = float((c.forecast_mw - c.actual_mw).abs().mean())
        mae_p = float((c.persistence_mw - c.actual_mw).abs().mean())
        out["baseline"] = dict(n=len(c), mae_forecast=mae_f, mae_persistence=mae_p,
                               skill=1 - mae_f / mae_p if mae_p else None)
    else:
        out["baseline"] = None
    out["over_forecast_pct"] = float(100 * (v.error_mw > 0).mean()) if len(v) else None
    b = v.dropna(subset=["band_lo", "band_hi"])
    if len(b):
        inside = (b.actual_mw >= b.band_lo) & (b.actual_mw <= b.band_hi)
        out["band"] = dict(n=len(b), coverage_pct=float(100 * inside.mean()),
                           mean_width=float((b.band_hi - b.band_lo).mean()),
                           below_pct=float(100 * (b.actual_mw < b.band_lo).mean()),
                           above_pct=float(100 * (b.actual_mw > b.band_hi).mean()))
    else:
        out["band"] = None
    return out


def by_hour(p: pd.DataFrame) -> list[dict]:
    v = p.dropna(subset=["forecast_mw", "actual_mw"])
    return [dict(hour=int(h), **_m(g.error_mw)) for h, g in v.groupby("hour")]


def by_level(p: pd.DataFrame) -> list[dict]:
    v = p.dropna(subset=["forecast_mw", "actual_mw"])
    if len(v) < 3:
        return []
    edges = np.quantile(v.forecast_mw, [1 / 3, 2 / 3])
    b = np.searchsorted(edges, v.forecast_mw.to_numpy(), side="right")
    names = ["low", "mid", "high"]
    lo = [float(v.forecast_mw.min()), float(edges[0]), float(edges[1])]
    hi = [float(edges[0]), float(edges[1]), float(v.forecast_mw.max())]
    return [dict(level=names[i], forecast_from=lo[i], forecast_to=hi[i], **_m(v.error_mw[b == i]))
            for i in range(3)]


def by_horizon(p: pd.DataFrame) -> list[dict]:
    v = p.dropna(subset=["forecast_mw", "actual_mw", "horizon_h"])
    if v.empty:
        return []
    bins = (v.horizon_h // 6 * 6).astype(int)
    return [dict(horizon_from_h=int(h), horizon_to_h=int(h) + 6, **_m(g.error_mw))
            for h, g in v.groupby(bins)]
