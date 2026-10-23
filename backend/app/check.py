"""Sanity-check a data snapshot before trusting any metrics.  Usage: python -m app.check [--data-dir DIR]"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import core, service


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(service.DATA_DIR))
    a = ap.parse_args()
    s = service.Store(Path(a.data_dir))
    fc, act = s.fc, s.act
    print(f"source={s.meta.get('source')}  delivery {s.dates[0]}..{s.dates[-1]}")

    print("\n[actuals] rows", len(act), "| range", act.start_time.min(), "->", act.start_time.max())
    print("  duplicates:", int(act.start_time.duplicated().sum()),
          "| min/mean/max MW: %.0f / %.0f / %.0f" % (act.actual_mw.min(), act.actual_mw.mean(), act.actual_mw.max()))

    pubs = pd.Series(sorted(fc.publish_time.unique()))
    gaps = pubs.diff().dropna().value_counts().head(4)
    per_pub = fc.groupby("publish_time").size()
    h = (fc.start_time - fc.publish_time).dt.total_seconds() / 3600
    print("\n[forecast] rows", len(fc), "| distinct publish times", len(pubs))
    print("  publish cadence (gap: count):", {str(k): int(v) for k, v in gaps.items()})
    print("  targets per publish: min %d / median %d / max %d" % (per_pub.min(), per_pub.median(), per_pub.max()))
    print("  lead time h (start-publish): min %.1f / median %.1f / max %.1f" % (h.min(), h.median(), h.max()))
    print("  target spacing:", fc.drop_duplicates("start_time").start_time.sort_values().diff().dropna().value_counts().head(3).to_dict())
    print("  min/mean/max MW: %.0f / %.0f / %.0f" % (fc.forecast_mw.min(), fc.forecast_mw.mean(), fc.forecast_mw.max()))

    print("\n[coverage at each cutoff] slots with a usable forecast, of 48 per delivery day")
    for c in core.CUTOFF_OPTIONS:
        p = s.panel(c)
        per_day = p.groupby("delivery_date").forecast_mw.apply(lambda x: int(x.notna().sum()))
        exp_day = p.groupby("delivery_date").on_grid.sum()
        bad = per_day[per_day < exp_day]
        n_exp = int(exp_day.sum())
        print(f"  {c}: {int(per_day.sum())}/{n_exp} native-grid slots have a forecast ({100*per_day.sum()/n_exp:.1f}%), "
              f"of {len(p)} half-hours; days short: {len(bad)}")
        if len(bad):
            print("     e.g.", dict(list(bad.items())[:5]))
        u = p.dropna(subset=["horizon_h"])
        print(f"     lead used: {u.horizon_h.min():.1f}..{u.horizon_h.max():.1f} h; actual present: {int(p.actual_mw.notna().sum())}/{len(p)}")

    m = s.panel("09:20").dropna(subset=["forecast_mw", "actual_mw"])
    print("\n[scale sanity @09:20] mean forecast %.0f MW vs mean actual %.0f MW (ratio %.2f); corr %.3f"
          % (m.forecast_mw.mean(), m.actual_mw.mean(), m.forecast_mw.mean() / m.actual_mw.mean(),
             m.forecast_mw.corr(m.actual_mw)))
    print("  Ratio far from 1 or low correlation => unit/fleet mismatch or a join problem; investigate before use.")


if __name__ == "__main__":
    main()
