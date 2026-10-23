# UK wind forecast monitor

Web app for a day-ahead power buying desk: (1) the wind forecast that was actually available at decision
time, (2) quantified forecast error. Data: Elexon only — WINDFOR (forecasts) and FUELHH, fuelType WIND (actuals).

**AI disclosure:** this project was designed and written with the assistance of Claude (Anthropic).

**Deployed app:** _add link here after deploying_

## How it works
- Decision rule: for delivery day D, each half-hour uses the **latest WINDFOR row with publishTime <= cutoff**
  on D-1 (UK time). Cutoffs: 09:20 (EPEX hourly, default), 09:50 (N2EX), 15:30 (EPEX 30-min). Slots with no
  qualifying forecast are reported as missing, never filled.
- Error = forecast − actual (positive = over-forecast, i.e. wind below forecast).
- Metrics: bias, MAE, RMSE, P50/P90 absolute error, MAE ÷ mean actual, over-forecast share, error by forecast
  level / hour / lead time, and skill vs a 2-day persistence baseline (actual 48 h earlier — always known at cutoff).
- Uncertainty band: empirical P10–P90 of (actual − forecast) per forecast-level tercile, fitted on the **other
  days only** (leave-one-day-out). Its backtested coverage (target 80%) is shown, so the band is checked, not assumed.
- "Decisions in January 2026" = decision days 2026-01-01..31, delivery days 2026-01-02..2026-02-01
  (change with `--decision-from/--decision-to`).

## Files
```
backend/app/core.py       as-of selection + all metrics (pure pandas/numpy)
backend/app/service.py    snapshot loading, cached panels, API payloads
backend/app/main.py       FastAPI routes (/api/meta, /api/day, /api/metrics) + serves built UI
backend/app/ingest.py     Elexon download -> data/*.csv.gz (+ --probe, --synthetic)
backend/app/synthetic.py  fake data for tests/offline demo only (UI shows a warning banner)
backend/tests/            unit tests (stdlib unittest; also run under pytest)
frontend/                 minimal React (Vite) page, no chart library
data/                     snapshot written by ingest (SOURCE.json records the source)
Dockerfile, docker-compose.yml, heroku.yml
```

## Run
```bash
cd backend && pip install -r requirements.txt
python -m app.ingest --probe        # FIRST: confirms Elexon parameters/fields/horizon (needs internet)
python -m app.ingest                # writes ../data/ (real data)
python -m unittest discover -s tests
uvicorn app.main:app --reload       # API on :8000
cd ../frontend && npm install && npm run dev   # UI on :5173 (proxies /api)
```
Docker: `python -m app.ingest` first (so `data/` is populated), then `docker compose up --build` -> http://localhost:8000

## Status / known limits
- Not yet run against live Elexon: parameter names for the two stream endpoints are best-effort; use `--probe`.
- Metrics are in-sample over one month; the band is validated out-of-sample by day, but one month is a small sample.
- No capacity field is in scope, so errors are normalised by mean actual generation, not installed capacity.
- WINDFOR and FUELHH may cover different wind fleets; a persistent bias could reflect that, not forecast skill.
