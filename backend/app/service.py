"""Data access + API payloads (framework-independent so it can be tested without FastAPI)."""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import core

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if (math.isnan(o) or math.isinf(o)) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, pd.Timestamp):
        return None if pd.isna(o) else o.isoformat()
    if o is pd.NaT:
        return None
    return o


class Store:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.meta = json.loads((data_dir / "SOURCE.json").read_text())
        self.fc = pd.read_csv(data_dir / "wind_forecast.csv.gz", parse_dates=["start_time", "publish_time"])
        self.act = pd.read_csv(data_dir / "wind_actual.csv.gz", parse_dates=["start_time"])
        for df, cols in ((self.fc, ["start_time", "publish_time"]), (self.act, ["start_time"])):
            for c in cols:
                df[c] = pd.to_datetime(df[c], utc=True)
        self.dates = list(pd.date_range(self.meta["delivery_from"], self.meta["delivery_to"]).strftime("%Y-%m-%d"))
        self._panels: dict[str, pd.DataFrame] = {}

    def panel(self, cutoff: str) -> pd.DataFrame:
        if cutoff not in self._panels:
            p = core.build_panel(self.fc, self.act, self.dates, cutoff)
            self._panels[cutoff] = core.add_band_loo(p)
        return self._panels[cutoff]

    # ---- payloads ----
    def get_meta(self) -> dict:
        p = self.panel("09:20")
        per_day = p.groupby("delivery_date").agg(
            forecast_slots=("forecast_mw", lambda s: int(s.notna().sum())),
            expected_forecast_slots=("on_grid", "sum"),
            actual_slots=("actual_mw", lambda s: int(s.notna().sum())))
        gaps = per_day[(per_day.forecast_slots < per_day.expected_forecast_slots) | (per_day.actual_slots < 48)]
        return clean(dict(
            source=self.meta.get("source"), written_at=self.meta.get("written_at"),
            dates=self.dates, cutoffs=core.CUTOFF_OPTIONS, default_cutoff="09:20",
            data_gaps=[dict(date=d, **r) for d, r in gaps.to_dict("index").items()],
            notes=["error = forecast - actual; positive = over-forecast (wind below forecast).",
                   "Forecast used = latest WINDFOR publish at or before the cutoff on the day before delivery.",
                   "Band = empirical P10-P90 of (actual - forecast) by forecast level, fitted on the OTHER days."]))

    def get_day(self, date: str, cutoff: str) -> dict:
        p = self.panel(cutoff)
        d = p[p.delivery_date == date]
        rows = [dict(start_time=r.start_time, forecast_mw=r.forecast_mw, actual_mw=r.actual_mw,
                     error_mw=r.error_mw, band_lo=r.band_lo, band_hi=r.band_hi,
                     publish_time=r.publish_time, horizon_h=r.horizon_h)
                for r in d.itertuples()]
        return clean(dict(date=date, cutoff=cutoff, cutoff_utc=d.cutoff.iloc[0] if len(d) else None,
                          summary=core.summarise(d), rows=rows))

    def get_metrics(self, cutoff: str, date_from: str | None, date_to: str | None) -> dict:
        p = self.panel(cutoff)
        if date_from:
            p = p[p.delivery_date >= date_from]
        if date_to:
            p = p[p.delivery_date <= date_to]
        daily = [dict(date=d, **{k: s[k] for k in ("n_valid", "bias", "mae", "rmse")},
                      band_coverage_pct=(s["band"] or {}).get("coverage_pct"))
                 for d, g in p.groupby("delivery_date") for s in [core.summarise(g)]]
        return clean(dict(cutoff=cutoff, date_from=date_from, date_to=date_to,
                          summary=core.summarise(p), by_hour=core.by_hour(p),
                          by_level=core.by_level(p), by_horizon=core.by_horizon(p), daily=daily))


@lru_cache(maxsize=1)
def store() -> Store:
    return Store()
