# UK Wind Forecast Monitor

A web app for an energy utility's **UK day-ahead power buying desk**. It answers two questions using Elexon data only:

1. **What wind forecast was actually available when the day-ahead decision had to be made?**
2. **How accurate are those forecasts, quantitatively, so the desk can allow for the error?**

> **AI disclosure:** this project was designed and written with the assistance of an AI tool (Claude, by Anthropic). All code was reviewed, run and verified by the author using the checks described under [Verification](#6-verification).

| | |
|---|---|
| **Deployed app** | _add link_ |
| **Demo video (unlisted YouTube)** | _add link_ |

---

## 1. Problem and scope

The client buys electricity in the GB day-ahead market for next-day delivery. Wind output is weather-dependent, so the buying team needs wind forecasts to work out how much power must still be bought from other sources (e.g. thermal plants).

Scope fixed by the brief:
- **Actuals:** Elexon `FUELHH`, `fuelType = WIND` (`startTime`, `generation`), half-hourly, national.
- **Forecasts:** Elexon `WINDFOR` (`startTime`, `publishTime`, `generation`).
- **Period:** purchase decisions made in **January 2026**.
- No other data (no demand, prices, weather).

### Interpretation (stated explicitly)
| Question | Decision |
|---|---|
| Which days? | Decision day = 1–31 Jan 2026, so **delivery days = 2 Jan – 1 Feb 2026** (31 days × 48 half-hours). Configurable: `python -m app.ingest --decision-from/--decision-to`. |
| When is the decision made? | Gate closures on the day before delivery, UK time: **09:20** (EPEX hourly, default), **09:50** (N2EX hourly), **15:30** (EPEX 30-min). Selectable in the UI. |
| Time zone | All data is UTC internally; cutoffs are defined in Europe/London (January = GMT, so no DST effects, but handled correctly). |

## 2. How it works

### 2.1 "Latest forecast available at decision time"
`WINDFOR` contains many forecasts for the same `startTime`, each with a different `publishTime`. Taking the newest one per target would leak information that did not exist at decision time. Instead, for delivery day D and cutoff `c` (HH:MM UK time on D-1):

```
forecast(t) = generation of the WINDFOR row for target t with the greatest publishTime <= c
```
A forecast published exactly at the cutoff is included; one a minute later is not. Slots with no qualifying forecast are shown as **missing — never filled or interpolated**. The UI shows the publish time and lead time used.

### 2.2 Accuracy metrics (error = forecast − actual)
Positive error = **over-forecast** (wind came in below forecast), the direction that leaves the buyer short of power.

| Metric | Meaning |
|---|---|
| Bias | mean error (MW) |
| MAE / RMSE | mean absolute / root-mean-square error (MW) |
| P50 / P90 absolute error | typical and "bad-day" error size (MW) |
| MAE ÷ mean actual | scale-free error. Installed capacity is not in the allowed data, so mean actual generation is used instead |
| Over-forecast share | % of half-hours where forecast > actual |
| Skill vs persistence | `1 − MAE(forecast)/MAE(persistence)`. Persistence = actual 48 h earlier (always known at any D-1 cutoff). Positive = forecast beats a trivial baseline |
| Breakdowns | by forecast level (low/mid/high terciles), hour of day, forecast lead time (6 h bins), and per day |

MAPE is deliberately not used: it is unstable when generation is near zero.

### 2.3 Uncertainty band (for decision-making)
For each half-hour, the band is `forecast + [P10, P90]` of past residuals (actual − forecast), computed separately per forecast-level tercile. **Each day's band is fitted on the other days only** (leave-one-day-out), so the reported coverage is a genuine out-of-sample check against the 80% target.

## 3. Architecture

```
Elexon API (WINDFOR, FUELHH)
      │  app/ingest.py   (retries, chunked, normalise, snapshot)
      ▼
data/wind_forecast.csv.gz, wind_actual.csv.gz, SOURCE.json
      │  app/service.py  (load once, cache panel per cutoff)
      ▼
app/core.py  pure functions: as-of selection, metrics, band
      │
      ▼
FastAPI  /api/meta  /api/day  /api/metrics   (+ serves built React UI)
      ▼
React (Vite) single page: day chart, KPIs, breakdown tables
```

**Design choice – snapshot, not live proxy.** The data is a fixed historical month. Ingesting once and serving a committed snapshot removes runtime dependence on Elexon (rate limits, latency, outages), makes results reproducible, and keeps the deployed app fast. `SOURCE.json` records the source and time of ingestion.

## 4. Files

```
backend/app/core.py        as-of selection, metrics, uncertainty band (pure pandas/numpy)
backend/app/service.py     snapshot loading, per-cutoff cache, API payloads
backend/app/main.py        FastAPI routes; serves frontend/dist when present
backend/app/ingest.py      Elexon download -> data/ (--probe, --synthetic, date options)
backend/app/check.py       data sanity report (cadence, lead times, coverage, scale)
backend/app/verify.py      independent correctness checks + README results table
backend/app/synthetic.py   fake data for tests/offline demos only (UI shows a warning banner)
backend/tests/             unit tests (stdlib unittest; also run under pytest)
frontend/                  minimal React + Vite UI (no chart library)
data/                      committed snapshot used by the app and Docker image
Dockerfile, docker-compose.yml, heroku.yml
```

### API
| Endpoint | Purpose |
|---|---|
| `GET /api/meta` | dates, cutoff options, data source, data gaps |
| `GET /api/day?date=YYYY-MM-DD&cutoff=09:20` | 48 rows: forecast, actual, error, band, publish time, lead time + day summary |
| `GET /api/metrics?cutoff=09:20&date_from=&date_to=` | overall summary and breakdowns |
| `GET /api/health` | liveness |

Interactive docs: `/docs`.

## 5. Run locally

Prerequisites: Python 3.11+, Node 20+, (optional) Docker.

```bash
# Backend
cd backend
pip install -r requirements.txt
python -m app.ingest --probe      # optional: shows live API fields and lead times
python -m app.ingest              # writes ../data (already committed; re-run to refresh)
uvicorn app.main:app --reload     # http://localhost:8000  (API docs at /docs)

# Frontend (dev server, proxies /api to :8000)
cd ../frontend
npm install
npm run dev                       # http://localhost:5173
```
Windows PowerShell works the same; run each command on its own line.

**Docker (UI + API on one port):**
```bash
docker compose up --build         # http://localhost:8000
```

## 6. Verification

```bash
cd backend
python -m unittest discover -s tests   # unit tests: leakage, cutoff inclusivity, metric maths, band, service
python -m app.check                    # data profile: publish cadence, lead times, coverage per cutoff, scale
python -m app.verify --markdown        # brute-force cross-checks on the real snapshot + results table
```
`app.verify` re-derives sampled forecasts with independent brute-force code and asserts: 48 slots/day, **no forecast published after its cutoff**, as-of selection and actual joins match brute force, metrics match an independent numpy calculation, persistence = actual 48 h earlier, band coverage near 80%, and a later cutoff never uses an older forecast. It exits non-zero on any failure.

## 7. Results (January 2026)

_Paste the table printed by `python -m app.verify --markdown` here, then write 2–3 sentences of interpretation (is there a bias? which cutoff is best? when are errors largest?). Do not hand-type numbers._

## 8. Deployment

**Heroku (container stack):**
```bash
heroku create <app-name>
heroku stack:set container
git push heroku main              # builds from heroku.yml / Dockerfile
heroku open
```
The container reads `$PORT`; the `data/` snapshot is baked into the image. (Check Heroku's current plan/pricing before relying on it.)

**Vercel:** the React build can be hosted as static output with the API as a Python function; this repo does not include Vercel configuration. If deploying there, test the deployed URL end to end.

## 9. Limitations and risks
- One month of data: error statistics (especially tails) are noisy and may not generalise to other seasons. Metrics are in-sample; only the band is validated out-of-sample.
- Slots lacking a forecast at the chosen cutoff are reported, not filled.
- `FUELHH` and `WINDFOR` may not cover exactly the same wind fleet; a persistent bias could reflect that rather than forecast skill.
- No installed-capacity data in scope, so errors are normalised by mean actual generation.
- The band is empirical, not a probabilistic forecast; it does not condition on weather regime.

## 10. Development practices
Pure logic separated from I/O (`core.py` has no framework imports); typed, validated API inputs; deterministic snapshot; unit tests for the correctness-critical rule (no look-ahead); independent verification script; Docker for reproducible runs.