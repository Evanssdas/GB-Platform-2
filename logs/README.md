# GB Platform Review Logs

This folder is the human-readable review layer. The append-only files under `live/` remain the raw source of truth.

## Current deployment gate

- **Mode:** `shadow_only`
- **Deployment ready:** `False`
- **Graded days:** 14 / 30
- **Model MAE:** 48.99 GBP/MWh
- **Persistence MAE:** 20.23 GBP/MWh
- **Improvement:** -142.19%
- **P10–P90 coverage:** 0.046

## Latest daily results

| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-08-17 | 85.36 | 3,784.90 | 4,941.98 | — | — | — | — |
| 2026-08-16 | 78.53 | 11,903.84 | 13,590.02 | — | — | — | — |
| 2026-08-15 | 66.82 | 14,180.82 | 16,008.57 | 74.16 | 12.97 | -471.81% | 0.000 |
| 2026-08-14 | 80.67 | 4,164.90 | 5,232.75 | 57.92 | 13.40 | -332.10% | 0.000 |
| 2026-08-13 | 90.75 | 2,564.53 | 3,628.58 | 51.78 | 11.82 | -338.01% | 0.000 |
| 2026-08-12 | 80.97 | 5,172.51 | 6,758.05 | 54.97 | 21.50 | -155.71% | 0.000 |
| 2026-08-11 | 83.93 | 4,071.85 | 5,153.45 | 49.22 | 16.33 | -201.44% | 0.000 |
| 2026-08-10 | 83.88 | 15,585.86 | 17,098.76 | 35.24 | 33.44 | -5.38% | 0.000 |
| 2026-08-09 | 66.93 | 15,981.97 | 18,008.08 | 37.28 | 15.90 | -134.43% | 0.125 |
| 2026-08-08 | 56.51 | 15,407.93 | 17,904.82 | 43.24 | 32.21 | -34.25% | 0.125 |
| 2026-08-07 | 70.20 | 13,846.52 | 15,304.53 | 39.07 | 13.35 | -192.59% | 0.083 |
| 2026-08-06 | 59.51 | 15,979.38 | 18,170.12 | 55.10 | 35.56 | -54.96% | 0.021 |
| 2026-08-05 | 69.09 | 26,440.87 | 28,375.67 | 37.17 | 38.52 | 3.51% | 0.146 |
| 2026-08-04 | 70.83 | 15,821.87 | 17,843.04 | 49.23 | 8.13 | -505.51% | 0.000 |

## Files

- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.
- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.
- [`grading_history.csv`](grading_history.csv): append-only grading history.
- [`latest_forecast.json`](latest_forecast.json): latest forecast review snapshot.
- [`latest_grading.json`](latest_grading.json): latest grading review snapshot.
- [`latest_deployment_gate.json`](latest_deployment_gate.json): latest deployment-gate state.
- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.

Registered forecast runs: **16**  
Registered grading runs: **15**
