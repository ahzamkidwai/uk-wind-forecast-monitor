"""Synthetic wind data for tests and offline demos ONLY. Never presented as real data:
the loader records the source in data/SOURCE.txt and the UI shows a banner."""
from __future__ import annotations

import numpy as np
import pandas as pd


def generate(start="2025-12-29", end="2026-02-03", seed=7, capacity=16000.0,
             base_sigma=900.0, growth_per_h=45.0, bias=-150.0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, end, freq="30min", tz="UTC", inclusive="left")
    n = len(idx)
    x = np.zeros(n)
    for i in range(1, n):  # slow AR(1) -> multi-day weather-like swings
        x[i] = 0.995 * x[i - 1] + rng.normal(0, 0.08)
    actual = np.clip(capacity * (0.4 + 0.3 * x / (x.std() + 1e-9)), 100, capacity)
    act = pd.DataFrame({"start_time": idx, "actual_mw": actual})
    a = pd.Series(actual, index=idx)

    pubs = pd.date_range(idx[0] + pd.Timedelta(hours=1), idx[-1], freq="1h", tz="UTC")
    rows = []
    for p in pubs:
        h = np.arange(0, 97) * 0.5 + 0.5  # horizons 0.5h..48.5h in 30-min steps
        tg = p + pd.to_timedelta(h, unit="h")
        tg = tg[(tg >= idx[0]) & (tg <= idx[-1])]
        if len(tg) == 0:
            continue
        hh = (tg - p).total_seconds() / 3600
        err = rng.normal(bias, base_sigma + growth_per_h * hh * 10 / 10)
        f = np.clip(a.reindex(tg).to_numpy() + err, 0, capacity)
        rows.append(pd.DataFrame({"start_time": tg, "publish_time": p, "forecast_mw": f}))
    fc = pd.concat(rows, ignore_index=True)
    return fc, act
