# GB Platform Review Logs

This folder is the human-readable review layer. The append-only files under `live/` remain the raw source of truth.

## Current deployment gate

- **Mode:** `shadow_only`
- **Deployment ready:** `False`
- **Graded days:** 33 / 30
- **Model MAE:** 59.12 GBP/MWh
- **Persistence MAE:** 23.97 GBP/MWh
- **Improvement:** -146.67%
- **P10–P90 coverage:** 0.041

## Latest daily results

| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-09-05 | 41.04 | 6,274.16 | 8,000.79 | — | — | — | — |
| 2026-09-04 | 35.31 | 12,027.53 | 13,767.19 | — | — | — | — |
| 2026-09-03 | — | — | — | 69.91 | 47.36 | -47.62% | 0.104 |
| 2026-09-02 | 86.59 | 13,755.34 | 15,116.28 | 80.21 | 49.03 | -63.61% | 0.000 |
| 2026-09-01 | 66.47 | 16,166.49 | 18,168.46 | 54.98 | 18.97 | -189.90% | 0.229 |
| 2026-08-31 | 63.43 | 15,029.18 | 17,090.56 | 68.87 | 31.60 | -117.96% | 0.042 |
| 2026-08-30 | 65.36 | 16,484.34 | 18,548.22 | 92.17 | 30.79 | -199.36% | 0.000 |
| 2026-08-29 | 71.56 | 18,786.78 | 20,728.85 | 56.09 | 35.79 | -56.72% | 0.062 |
| 2026-08-28 | 74.25 | 16,471.28 | 18,223.17 | 61.80 | 37.55 | -64.58% | 0.000 |
| 2026-08-27 | 72.81 | 16,982.24 | 18,988.22 | 91.40 | 25.15 | -263.34% | 0.000 |
| 2026-08-26 | 78.98 | 17,342.75 | 19,296.92 | 68.41 | 17.59 | -288.86% | 0.000 |
| 2026-08-25 | 76.39 | 24,733.19 | 27,192.04 | 57.79 | 14.45 | -299.80% | 0.000 |
| 2026-08-24 | 85.28 | 8,408.17 | 9,849.25 | 51.88 | 32.88 | -57.82% | 0.000 |
| 2026-08-23 | 83.03 | 11,244.50 | 12,724.01 | 45.35 | 20.86 | -117.43% | 0.062 |

## Files

- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.
- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.
- [`grading_history.csv`](grading_history.csv): append-only grading history.
- [`latest_forecast.json`](latest_forecast.json): latest forecast review snapshot.
- [`latest_grading.json`](latest_grading.json): latest grading review snapshot.
- [`latest_deployment_gate.json`](latest_deployment_gate.json): latest deployment-gate state.
- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.

Registered forecast runs: **34**  
Registered grading runs: **34**
