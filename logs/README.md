# GB Platform Review Logs

This folder is the human-readable review layer. The append-only files under `live/` remain the raw source of truth.

## Current deployment gate

- **Mode:** `shadow_only`
- **Deployment ready:** `False`
- **Graded days:** 68 / 30
- **Model MAE:** 65.47 GBP/MWh
- **Persistence MAE:** 34.52 GBP/MWh
- **Improvement:** -89.63%
- **P10–P90 coverage:** 0.062

## Latest daily results

| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-10-10 | 24.32 | 4,860.34 | 6,535.18 | — | — | — | — |
| 2026-10-09 | 31.72 | 6,664.75 | 8,352.29 | 28.23 | 83.65 | 66.26% | 0.312 |
| 2026-10-08 | 65.37 | 9,992.68 | 12,218.59 | 74.33 | 26.69 | -178.52% | 0.042 |
| 2026-10-07 | 74.82 | 7,129.76 | 8,813.29 | 84.64 | 38.00 | -122.77% | 0.000 |
| 2026-10-06 | 99.61 | 6,596.15 | 8,151.85 | 90.89 | 71.55 | -27.03% | 0.000 |
| 2026-10-05 | 69.14 | 8,145.09 | 10,001.50 | 58.95 | 20.17 | -192.26% | 0.062 |
| 2026-10-04 | 76.28 | 16,689.70 | 19,097.87 | 55.51 | 40.08 | -38.49% | 0.083 |
| 2026-10-02 | 73.26 | 19,182.41 | 21,118.88 | 80.55 | 17.99 | -347.87% | 0.000 |
| 2026-10-01 | 81.01 | 9,962.13 | 11,287.00 | 70.87 | 33.22 | -113.36% | 0.000 |
| 2026-09-30 | 56.55 | 13,138.03 | 15,077.12 | 63.83 | 39.67 | -60.90% | 0.000 |
| 2026-09-29 | 69.03 | 14,177.44 | 16,245.39 | 72.26 | 26.26 | -175.16% | 0.000 |
| 2026-09-28 | 98.26 | 7,556.93 | 9,435.18 | 68.11 | 70.61 | 3.54% | 0.000 |
| 2026-09-27 | 50.90 | 14,665.21 | 16,665.52 | 52.08 | 39.03 | -33.44% | 0.167 |
| 2026-09-26 | 67.66 | 19,987.38 | 22,261.08 | 69.95 | 28.00 | -149.79% | 0.167 |

## Files

- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.
- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.
- [`grading_history.csv`](grading_history.csv): append-only grading history.
- [`latest_forecast.json`](latest_forecast.json): latest forecast review snapshot.
- [`latest_grading.json`](latest_grading.json): latest grading review snapshot.
- [`latest_deployment_gate.json`](latest_deployment_gate.json): latest deployment-gate state.
- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.

Registered forecast runs: **68**  
Registered grading runs: **69**
