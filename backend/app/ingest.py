"""Fetch Elexon WINDFOR (forecasts) and FUELHH (WIND actuals) and write a compact snapshot.

Usage (needs internet):
  python -m app.ingest --probe                 # 1-day sanity check of both endpoints, prints schema
  python -m app.ingest                         # decisions made 2026-01-01..2026-01-31
  python -m app.ingest --synthetic             # offline demo/test data (clearly flagged in the UI)

"Purchase decisions in January 2026" is interpreted as decision day D-1 in January, i.e. delivery days
2026-01-02 .. 2026-02-01. Change with --decision-from/--decision-to.
"""
from __future__ import annotations

import argparse, json, time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE = "https://data.elexon.co.uk/bmrs/api/v1"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _get(path: str, params: dict, retries=4):
    import requests
    last = None
    for i in range(retries):
        try:
            r = requests.get(f"{BASE}{path}", params=params, timeout=90, headers={"Accept": "application/json"})
            if r.status_code == 429 or r.status_code >= 500:
                raise RuntimeError(f"HTTP {r.status_code}")
            r.raise_for_status()
            j = r.json()
            return j["data"] if isinstance(j, dict) and "data" in j else j
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"GET {path} {params} failed: {last}")


def _iso(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%MZ")


def normalise_windfor(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["start_time", "publish_time", "forecast_mw"])
    return pd.DataFrame({
        "start_time": pd.to_datetime(df["startTime"], utc=True),
        "publish_time": pd.to_datetime(df["publishTime"], utc=True),
        "forecast_mw": pd.to_numeric(df["generation"], errors="coerce"),
    })


def normalise_fuelhh(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["start_time", "actual_mw"])
    if "fuelType" in df:
        df = df[df["fuelType"].astype(str).str.upper() == "WIND"]
    if "publishTime" in df:  # keep the latest revision per target if any
        df = df.sort_values("publishTime")
    out = pd.DataFrame({"start_time": pd.to_datetime(df["startTime"], utc=True),
                        "actual_mw": pd.to_numeric(df["generation"], errors="coerce")})
    return out.drop_duplicates("start_time", keep="last")


def fetch_windfor(pub_from: pd.Timestamp, pub_to: pd.Timestamp, step_days=3) -> pd.DataFrame:
    parts, t = [], pub_from
    while t < pub_to:
        u = min(t + pd.Timedelta(days=step_days), pub_to)
        rows = _get("/datasets/WINDFOR/stream",
                    {"publishDateTimeFrom": _iso(t), "publishDateTimeTo": _iso(u), "format": "json"})
        parts.append(normalise_windfor(rows))
        print(f"WINDFOR {_iso(t)} -> {_iso(u)}: {len(rows)} rows")
        t = u
    return pd.concat(parts, ignore_index=True) if parts else normalise_windfor([])


def fetch_fuelhh_wind(d_from: pd.Timestamp, d_to: pd.Timestamp, step_days=10) -> pd.DataFrame:
    parts, t = [], d_from
    while t < d_to:
        u = min(t + pd.Timedelta(days=step_days), d_to)
        try:
            rows = _get("/datasets/FUELHH/stream",
                        {"settlementDateFrom": t.strftime("%Y-%m-%d"),
                         "settlementDateTo": (u - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                         "fuelType": "WIND", "format": "json"})
        except RuntimeError:
            rows = _get("/datasets/FUELHH/stream",
                        {"publishDateTimeFrom": _iso(t), "publishDateTimeTo": _iso(u), "format": "json"})
        parts.append(normalise_fuelhh(rows))
        print(f"FUELHH {t.date()} -> {u.date()}: {len(rows)} rows")
        t = u
    return pd.concat(parts, ignore_index=True) if parts else normalise_fuelhh([])


def write_snapshot(fc: pd.DataFrame, act: pd.DataFrame, meta: dict, out: Path = DATA_DIR):
    out.mkdir(parents=True, exist_ok=True)
    fc = fc.dropna().drop_duplicates(["start_time", "publish_time"], keep="last")
    act = act.dropna().drop_duplicates("start_time", keep="last")
    fc.sort_values(["start_time", "publish_time"]).to_csv(out / "wind_forecast.csv.gz", index=False)
    act.sort_values("start_time").to_csv(out / "wind_actual.csv.gz", index=False)
    meta = {**meta, "written_at": datetime.now(timezone.utc).isoformat(),
            "n_forecast_rows": int(len(fc)), "n_actual_rows": int(len(act))}
    (out / "SOURCE.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--decision-from", default="2026-01-01")
    ap.add_argument("--decision-to", default="2026-01-31")
    ap.add_argument("--max-horizon-h", type=float, default=72, help="drop forecasts published > N h before target")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--out", default=str(DATA_DIR))
    a = ap.parse_args()

    d0 = pd.Timestamp(a.decision_from) + pd.Timedelta(days=1)   # first delivery day
    d1 = pd.Timestamp(a.decision_to) + pd.Timedelta(days=1)     # last delivery day
    meta = dict(delivery_from=d0.strftime("%Y-%m-%d"), delivery_to=d1.strftime("%Y-%m-%d"),
                max_horizon_h=a.max_horizon_h)

    if a.synthetic:
        from .synthetic import generate
        fc, act = generate()
        write_snapshot(fc, act, {**meta, "source": "synthetic"}, Path(a.out))
        return

    if a.probe:
        t0 = pd.Timestamp("2026-01-05", tz="UTC")
        w = _get("/datasets/WINDFOR/stream", {"publishDateTimeFrom": _iso(t0), "publishDateTimeTo": _iso(t0 + pd.Timedelta(days=1)), "format": "json"})
        f = _get("/datasets/FUELHH/stream", {"settlementDateFrom": "2026-01-05", "settlementDateTo": "2026-01-05", "fuelType": "WIND", "format": "json"})
        for name, rows in (("WINDFOR", w), ("FUELHH", f)):
            print(name, "rows:", len(rows), "| fields:", sorted(rows[0].keys()) if rows else None)
            print("  sample:", rows[:2])
        nw = normalise_windfor(w)
        if len(nw):
            h = (nw.start_time - nw.publish_time).dt.total_seconds() / 3600
            print(f"WINDFOR horizon range (h): {h.min():.1f} .. {h.max():.1f}; distinct publish times: {nw.publish_time.nunique()}")
        return

    utc = lambda t: t.tz_localize("UTC")
    # Forecasts published from 3 days before the first delivery day to the end of the last delivery day.
    fc = fetch_windfor(utc(d0 - pd.Timedelta(days=3)), utc(d1 + pd.Timedelta(days=1)))
    # Actuals: from 2 days before the first delivery day (persistence baseline) to the end of the last one.
    act = fetch_fuelhh_wind(d0 - pd.Timedelta(days=2), d1 + pd.Timedelta(days=1))
    if fc.empty or act.empty:
        raise SystemExit("No data returned; run --probe and check parameters.")
    h = (fc.start_time - fc.publish_time).dt.total_seconds() / 3600
    fc = fc[(h > 0) & (h <= a.max_horizon_h)]
    write_snapshot(fc, act, {**meta, "source": "elexon", "base_url": BASE}, Path(a.out))


if __name__ == "__main__":
    main()
