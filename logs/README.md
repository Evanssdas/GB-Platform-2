# GB Platform Review Logs

This folder is the human-readable review layer. The append-only files under `live/` remain the raw source of truth.

## Current deployment gate

- **Mode:** `shadow_only`
- **Deployment ready:** `False`
- **Graded days:** 27 / 30
- **Model MAE:** 56.53 GBP/MWh
- **Persistence MAE:** 21.29 GBP/MWh
- **Improvement:** -165.50%
- **P10–P90 coverage:** 0.034

## Latest daily results

| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-08-30 | 65.36 | 16,484.34 | 18,548.22 | — | — | — | — |
| 2026-08-29 | 71.56 | 18,786.78 | 20,728.85 | — | — | — | — |
| 2026-08-28 | 74.25 | 16,471.28 | 18,223.17 | 61.80 | 37.55 | -64.58% | 0.000 |
| 2026-08-27 | 72.81 | 16,982.24 | 18,988.22 | 91.40 | 25.15 | -263.34% | 0.000 |
| 2026-08-26 | 78.98 | 17,342.75 | 19,296.92 | 68.41 | 17.59 | -288.86% | 0.000 |
| 2026-08-25 | 76.39 | 24,733.19 | 27,192.04 | 57.79 | 14.45 | -299.80% | 0.000 |
| 2026-08-24 | 85.28 | 8,408.17 | 9,849.25 | 51.88 | 32.88 | -57.82% | 0.000 |
| 2026-08-23 | 83.03 | 11,244.50 | 12,724.01 | 45.35 | 20.86 | -117.43% | 0.062 |
| 2026-08-22 | 74.63 | 14,486.11 | 16,353.75 | 34.79 | 49.28 | 29.39% | 0.208 |
| 2026-08-21 | 85.18 | 8,065.13 | 9,170.75 | 51.82 | 10.46 | -395.64% | 0.000 |
| 2026-08-20 | 84.50 | 7,638.83 | 8,833.69 | 61.66 | 14.27 | -332.21% | 0.000 |
| 2026-08-19 | 84.15 | 11,192.54 | 12,840.41 | 73.81 | 17.14 | -330.57% | 0.000 |
| 2026-08-18 | 65.34 | 13,505.71 | 15,639.20 | 88.53 | 19.41 | -356.08% | 0.000 |
| 2026-08-17 | 85.36 | 3,784.90 | 4,941.98 | 77.36 | 22.61 | -242.13% | 0.000 |

## Files

- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.
- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.
- [`grading_history.csv`](grading_history.csv): append-only grading history.
- [`latest_forecast.json`](latest_forecast.json): latest forecast review snapshot.
- [`latest_grading.json`](latest_grading.json): latest grading review snapshot.
- [`latest_deployment_gate.json`](latest_deployment_gate.json): latest deployment-gate state.
- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.

Registered forecast runs: **29**  
Registered grading runs: **28**
