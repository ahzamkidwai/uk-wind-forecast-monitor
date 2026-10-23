"""Independent correctness checks on the real snapshot.  Usage: python -m app.verify [--markdown]

Re-derives sampled results with brute-force code that shares nothing with core.py, and asserts invariants.
Exit code 1 if any check fails.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import core, service

FAILS = []


def check(name: str, ok: bool, detail: str = ""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(service.DATA_DIR))
    ap.add_argument("--markdown", action="store_true", help="print a results table for the README")
    ap.add_argument("--samples", type=int, default=400)
    a = ap.parse_args()
    s = service.Store(Path(a.data_dir))
    rng = np.random.default_rng(0)
    print(f"source={s.meta.get('source')}  delivery {s.dates[0]}..{s.dates[-1]}\n")
    if s.meta.get("source") != "elexon":
        print("WARNING: not real Elexon data\n")

    act_map = dict(zip(s.act.start_time, s.act.actual_mw))
    rows_out = []
    panels = {}
    for c in core.CUTOFF_OPTIONS:
        p = s.panel(c)
        panels[c] = p
        print(f"--- cutoff {c} ---")
        check("48 slots per delivery day, no duplicates",
              len(p) == 48 * len(s.dates) and not p.duplicated(["delivery_date", "start_time"]).any())
        used = p.dropna(subset=["publish_time"])
        check("no forecast published after cutoff (no leakage)", bool((used.publish_time <= used.cutoff).all()))
        check("cutoff is D-1 for every row (hh:mm UK)",
              bool((p.cutoff.dt.tz_convert(core.LONDON).dt.strftime("%H:%M") == c).all()))

        # Brute-force oracle for as-of selection
        bad = 0
        for i in rng.choice(len(p), size=min(a.samples, len(p)), replace=False):
            r = p.iloc[i]
            cand = s.fc[(s.fc.start_time == r.start_time) & (s.fc.publish_time <= r.cutoff)]
            exp = np.nan if cand.empty else cand.sort_values("publish_time").iloc[-1].forecast_mw
            got = r.forecast_mw
            if not ((np.isnan(exp) and np.isnan(got)) or np.isclose(exp, got)):
                bad += 1
        check(f"as-of selection matches brute force on {min(a.samples, len(p))} random slots", bad == 0, f"mismatches={bad}")

        # Actual join oracle
        bad = sum(1 for r in p.sample(min(a.samples, len(p)), random_state=1).itertuples()
                  if not ((pd.isna(r.actual_mw) and r.start_time not in act_map) or
                          (r.start_time in act_map and np.isclose(act_map[r.start_time], r.actual_mw))))
        check("actuals joined correctly (sampled)", bad == 0, f"mismatches={bad}")

        v = p.dropna(subset=["forecast_mw", "actual_mw"])
        e = v.forecast_mw.to_numpy() - v.actual_mw.to_numpy()
        sm = core.summarise(p)
        check("MAE / RMSE / bias match independent numpy",
              np.isclose(sm["mae"], np.abs(e).mean()) and np.isclose(sm["rmse"], np.sqrt((e ** 2).mean()))
              and np.isclose(sm["bias"], e.mean()))
        check("forecast is not a copy of the actual (error > 0)", float(np.abs(e).mean()) > 1.0, f"MAE={np.abs(e).mean():.1f}")
        pers = v.dropna(subset=["persistence_mw"])
        ok = all(np.isclose(act_map.get(r.start_time - pd.Timedelta(hours=48), np.nan), r.persistence_mw)
                 for r in pers.sample(min(200, len(pers)), random_state=2).itertuples())
        check("persistence baseline = actual 48h earlier", ok)
        bc = (sm["band"] or {}).get("coverage_pct")
        check("band coverage near nominal 80% (65-92%)", bc is not None and 65 <= bc <= 92, f"{bc:.1f}%" if bc else "n/a")
        check("forecast coverage 100% of slots", sm["coverage_pct"] == 100.0, f"{sm['coverage_pct']:.1f}%")
        rows_out.append((c, sm))
        print()

    # Fresher cutoff must use forecasts at least as new, slot by slot
    a_, b_ = panels["09:20"], panels["15:30"]
    m = a_.publish_time.notna() & b_.publish_time.notna()
    check("15:30 cutoff uses publish times >= 09:20 cutoff for every slot", bool((b_.publish_time[m] >= a_.publish_time[m]).all()))

    if a.markdown:
        print("\n| Cutoff (UK, D-1) | MAE (MW) | RMSE (MW) | Bias (MW) | P90 abs err (MW) | MAE / mean actual | Skill vs persistence | P10-P90 band coverage | Slots with forecast |")
        print("|---|---|---|---|---|---|---|---|---|")
        for c, sm in rows_out:
            bl = sm["baseline"]
            print(f"| {c} | {sm['mae']:.0f} | {sm['rmse']:.0f} | {sm['bias']:+.0f} | {sm['p90_abs']:.0f} | {sm['nmae_pct']:.1f}% | "
                  f"{100*bl['skill']:.1f}% | {sm['band']['coverage_pct']:.1f}% | {sm['coverage_pct']:.0f}% |")
    print("\nALL CHECKS PASSED" if not FAILS else f"\n{len(FAILS)} CHECK(S) FAILED: {FAILS}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()