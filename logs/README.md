# GB Platform Review Logs

This folder is the human-readable review layer. The append-only files under `live/` remain the raw source of truth.

## Current deployment gate

- **Mode:** `shadow_only`
- **Deployment ready:** `False`
- **Graded days:** 18 / 30
- **Model MAE:** 55.58 GBP/MWh
- **Persistence MAE:** 19.48 GBP/MWh
- **Improvement:** -185.30%
- **P10–P90 coverage:** 0.036

## Latest daily results

| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-08-21 | 85.18 | 8,065.13 | 9,170.75 | — | — | — | — |
| 2026-08-20 | 84.50 | 7,638.83 | 8,833.69 | — | — | — | — |
| 2026-08-19 | 84.15 | 11,192.54 | 12,840.41 | 73.81 | 17.14 | -330.57% | 0.000 |
| 2026-08-18 | 65.34 | 13,505.71 | 15,639.20 | 88.53 | 19.41 | -356.08% | 0.000 |
| 2026-08-17 | 85.36 | 3,784.90 | 4,941.98 | 77.36 | 22.61 | -242.13% | 0.000 |
| 2026-08-16 | 78.53 | 11,903.84 | 13,590.02 | 68.70 | 9.01 | -662.68% | 0.000 |
| 2026-08-15 | 66.82 | 14,180.82 | 16,008.57 | 74.16 | 12.97 | -471.81% | 0.000 |
| 2026-08-14 | 80.67 | 4,164.90 | 5,232.75 | 57.92 | 13.40 | -332.10% | 0.000 |
| 2026-08-13 | 90.75 | 2,564.53 | 3,628.58 | 51.78 | 11.82 | -338.01% | 0.000 |
| 2026-08-12 | 80.97 | 5,172.51 | 6,758.05 | 54.97 | 21.50 | -155.71% | 0.000 |
| 2026-08-11 | 83.93 | 4,071.85 | 5,153.45 | 49.22 | 16.33 | -201.44% | 0.000 |
| 2026-08-10 | 83.88 | 15,585.86 | 17,098.76 | 35.24 | 33.44 | -5.38% | 0.000 |
| 2026-08-09 | 66.93 | 15,981.97 | 18,008.08 | 37.28 | 15.90 | -134.43% | 0.125 |
| 2026-08-08 | 56.51 | 15,407.93 | 17,904.82 | 43.24 | 32.21 | -34.25% | 0.125 |

## Files

- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.
- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.
- [`grading_history.csv`](grading_history.csv): append-only grading history.
- [`latest_forecast.json`](latest_forecast.json): latest forecast review snapshot.
- [`latest_grading.json`](latest_grading.json): latest grading review snapshot.
- [`latest_deployment_gate.json`](latest_deployment_gate.json): latest deployment-gate state.
- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.

Registered forecast runs: **20**  
Registered grading runs: **19**
