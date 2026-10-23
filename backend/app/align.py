"""Timestamp-alignment and bias-structure diagnostics.  Usage: python -m app.align [--data-dir DIR] [--cutoff 09:20]

Tests whether WINDFOR's startTime convention lines up with FUELHH's, and whether bias is additive or proportional.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from . import service

H = pd.Timedelta(minutes=30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(service.DATA_DIR))
    ap.add_argument("--cutoff", default="09:20")
    a = ap.parse_args()
    s = service.Store(Path(a.data_dir))
    p = s.panel(a.cutoff).dropna(subset=["forecast_mw"])
    act = s.act.drop_duplicates("start_time").set_index("start_time").actual_mw
    print(f"source={s.meta.get('source')} cutoff={a.cutoff}; forecast points: {len(p)}")

    def stats(label, act_vals):
        e = p.forecast_mw.to_numpy() - act_vals
        m = ~np.isnan(e)
        print(f"  {label:<46} n={m.sum():4d}  MAE={np.abs(e[m]).mean():7.0f}  bias={e[m].mean():+7.0f}  RMSE={np.sqrt((e[m]**2).mean()):7.0f}")
        return np.abs(e[m]).mean()

    print("\n[shift test] compare forecast at t with actual at t + lag (lag in half-hours; 0 = same startTime)")
    res = {}
    for lag in range(-4, 5):
        res[lag] = stats(f"actual at t{lag*30:+d} min", act.reindex(p.start_time + lag * H).to_numpy())
    best = min(res, key=res.get)
    print(f"  -> lowest MAE at lag {best*30:+d} min" + ("  (aligned)" if best == 0 else "  (CHECK timestamp convention!)"))

    print("\n[hour-average test] forecast may represent an hourly mean")
    a0, a30, am30 = (act.reindex(p.start_time + k * H).to_numpy() for k in (0, 1, -1))
    stats("mean(actual[t], actual[t+30])  (hour starting t)", (a0 + a30) / 2)
    stats("mean(actual[t-30], actual[t])  (hour ending t)", (am30 + a0) / 2)

    print("\n[bias structure] additive offset vs proportional scaling, by forecast tercile")
    v = p.dropna(subset=["actual_mw"]).copy()
    v["tercile"] = pd.qcut(v.forecast_mw, 3, labels=["low", "mid", "high"])
    g = v.groupby("tercile", observed=True).agg(n=("forecast_mw", "size"), mean_fc=("forecast_mw", "mean"),
                                                mean_act=("actual_mw", "mean"))
    g["bias_mw"] = g.mean_fc - g.mean_act
    g["ratio_fc/act"] = g.mean_fc / g.mean_act
    print(g.round(2).to_string())
    print("  Similar bias_mw across terciles => additive offset; similar ratio => proportional (fleet/scope) difference.")

    d = v.groupby("delivery_date").apply(lambda x: (x.forecast_mw - x.actual_mw).mean(), include_groups=False)
    print(f"\n[daily bias] days over-forecast: {(d > 0).sum()}/{len(d)}; daily bias min/median/max: {d.min():+.0f} / {d.median():+.0f} / {d.max():+.0f} MW")
    print("  Bias on nearly every day => systematic (scope/definition), not random forecast error.")


if __name__ == "__main__":
    main()