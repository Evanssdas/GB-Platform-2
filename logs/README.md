# GB Platform Review Logs

This folder is the human-readable review layer. The append-only files under `live/` remain the raw source of truth.

## Current deployment gate

- **Mode:** `shadow_only`
- **Deployment ready:** `False`
- **Graded days:** 44 / 30
- **Model MAE:** 65.65 GBP/MWh
- **Persistence MAE:** 31.00 GBP/MWh
- **Improvement:** -111.79%
- **P10–P90 coverage:** 0.048

## Latest daily results

| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-09-16 | 79.38 | 16,959.46 | 18,676.58 | — | — | — | — |
| 2026-09-15 | 63.86 | 17,008.34 | 19,407.69 | — | — | — | — |
| 2026-09-14 | 82.73 | 13,903.62 | 15,465.59 | 97.03 | 25.06 | -287.19% | 0.000 |
| 2026-09-13 | 76.59 | 17,672.12 | 19,710.96 | 118.89 | 96.99 | -22.57% | 0.000 |
| 2026-09-12 | 31.62 | 9,696.70 | 12,113.42 | 74.06 | 84.90 | 12.77% | 0.042 |
| 2026-09-11 | 67.59 | 15,778.57 | 18,008.88 | 102.14 | 38.56 | -164.88% | 0.000 |
| 2026-09-10 | 62.13 | 16,055.17 | 18,021.68 | 82.53 | 41.25 | -100.10% | 0.000 |
| 2026-09-09 | 66.13 | 8,741.20 | 10,663.53 | 94.06 | 30.76 | -205.82% | 0.000 |
| 2026-09-08 | 36.32 | 9,994.05 | 12,333.79 | 108.32 | 19.89 | -444.54% | 0.000 |
| 2026-09-07 | 40.60 | 11,764.97 | 13,837.98 | 97.62 | 61.34 | -59.14% | 0.000 |
| 2026-09-06 | 40.37 | 11,752.85 | 13,826.21 | 64.45 | 40.60 | -58.75% | 0.167 |
| 2026-09-05 | 41.04 | 6,274.16 | 8,000.79 | 40.79 | 86.06 | 52.60% | 0.375 |
| 2026-09-04 | 35.31 | 12,027.53 | 13,767.19 | 51.71 | 41.03 | -26.03% | 0.188 |
| 2026-09-03 | — | — | — | 69.91 | 47.36 | -47.62% | 0.104 |

## Files

- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.
- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.
- [`grading_history.csv`](grading_history.csv): append-only grading history.
- [`latest_forecast.json`](latest_forecast.json): latest forecast review snapshot.
- [`latest_grading.json`](latest_grading.json): latest grading review snapshot.
- [`latest_deployment_gate.json`](latest_deployment_gate.json): latest deployment-gate state.
- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.

Registered forecast runs: **45**  
Registered grading runs: **45**
