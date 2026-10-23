# Wind Intelligence — Frontend

A responsive React dashboard for comparing UK wind generation forecasts available at a purchasing decision cutoff with subsequently observed generation.

## Features

- Delivery-day and decision-cutoff filters.
- Forecast-vs-actual chart with selectable series and hover tooltips.
- Summary KPIs: MAE, RMSE, bias and matched half-hourly periods.
- Sortable forecast-level, hourly, daily and lead-time tables.
- Data-quality panel, visible data-gap/source warnings, retry handling and CSV export.
- Responsive layout for desktop and mobile.

## Requirements

- Node.js 18 or later
- A compatible backend implementing the endpoints listed below

## Install and run

```bash
npm install
cp .env.example .env
npm run dev
```

Vite prints the local development URL. The UI expects the backend on the same origin by default. If the API is hosted elsewhere, set `VITE_API_BASE_URL` in `.env` and configure CORS on the backend.

Build for production:

```bash
npm run build
npm run preview
```

## Backend API contract expected by this UI

- `GET /api/meta` returns `{ "dates": ["2026-01-01"], "default_cutoff": "09:20", "cutoffs": { "09:20": "Decision description" }, "source": "elexon", "data_gaps": [] }`.
- `GET /api/day?date=YYYY-MM-DD&cutoff=HH:MM` returns `{ "rows": [{ "start_time": "2026-01-15T00:00:00Z", "publish_time": "2026-01-14T09:00:00Z", "forecast_mw": 4000, "actual_mw": 4200, "error_mw": -200, "band_lo": 3500, "band_hi": 4500 }], "summary": { "mae": 200, "rmse": 200, "bias": -200, "n_valid": 48, "n_expected": 48 } }`.
- `GET /api/metrics?cutoff=HH:MM` returns `{ "summary": { "mae": 200, "rmse": 250, "bias": -20, "p90_abs": 400, "nmae_pct": 5, "over_forecast_pct": 45, "n_valid": 1480, "n_expected": 1488, "baseline": { "skill": 0.1 }, "band": { "coverage_pct": 80 } }, "by_level": [], "by_hour": [], "by_horizon": [], "daily": [] }`.

The numeric examples above are API-shape examples only, not actual Elexon observations. Ensure API fields use the same names, units and semantics. `source` should be `elexon` only when the dataset's provenance has been verified.

## Important analytical requirements

1. Choose the latest `WINDFOR` forecast publication with `publishTime` at or before the documented decision cutoff for each delivery period.
2. Match selected forecasts and `FUELHH` actuals by delivery-period start time, not by publication time.
3. Keep timestamps timezone-aware; store/compare in UTC and display the appropriate UK local time. Confirm DST handling.
4. Do not fill missing forecasts or actuals with zero. Return coverage counts and report matched sample size with every metric.
5. Fit uncertainty bands and baselines without leakage from the delivery day being evaluated.
6. Treat the dashboard as decision support, not a complete procurement recommendation: demand, prices, balancing costs and other generation sources are not included.

## Packages added

- `recharts`: responsive interactive charts and tooltips.
- `lucide-react`: consistent icons.

React and Vite remain the app foundation. Google Fonts are imported in CSS as a progressive visual enhancement; the system font stack remains a fallback.
