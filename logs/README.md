# GB Platform Review Logs

This folder is the human-readable review layer. The append-only files under `live/` remain the raw source of truth.

## Current deployment gate

- **Mode:** `shadow_only`
- **Deployment ready:** `False`
- **Graded days:** 48 / 30
- **Model MAE:** 65.76 GBP/MWh
- **Persistence MAE:** 31.85 GBP/MWh
- **Improvement:** -106.50%
- **P10–P90 coverage:** 0.058

## Latest daily results

| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-09-19 | 25.21 | 6,120.14 | 7,781.21 | — | — | — | — |
| 2026-09-18 | 45.84 | 10,542.48 | 12,819.29 | 44.15 | 36.97 | -19.40% | 0.312 |
| 2026-09-17 | 39.60 | 9,667.48 | 12,056.66 | 61.87 | 56.52 | -9.47% | 0.229 |
| 2026-09-16 | 79.38 | 16,959.46 | 18,676.58 | 74.96 | 33.17 | -125.99% | 0.000 |
| 2026-09-15 | 63.86 | 17,008.34 | 19,407.69 | 86.88 | 37.22 | -133.41% | 0.125 |
| 2026-09-14 | 82.73 | 13,903.62 | 15,465.59 | 97.03 | 25.06 | -287.19% | 0.000 |
| 2026-09-13 | 76.59 | 17,672.12 | 19,710.96 | 118.89 | 96.99 | -22.57% | 0.000 |
| 2026-09-12 | 31.62 | 9,696.70 | 12,113.42 | 74.06 | 84.90 | 12.77% | 0.042 |
| 2026-09-11 | 67.59 | 15,778.57 | 18,008.88 | 102.14 | 38.56 | -164.88% | 0.000 |
| 2026-09-10 | 62.13 | 16,055.17 | 18,021.68 | 82.53 | 41.25 | -100.10% | 0.000 |
| 2026-09-09 | 66.13 | 8,741.20 | 10,663.53 | 94.06 | 30.76 | -205.82% | 0.000 |
| 2026-09-08 | 36.32 | 9,994.05 | 12,333.79 | 108.32 | 19.89 | -444.54% | 0.000 |
| 2026-09-07 | 40.60 | 11,764.97 | 13,837.98 | 97.62 | 61.34 | -59.14% | 0.000 |
| 2026-09-06 | 40.37 | 11,752.85 | 13,826.21 | 64.45 | 40.60 | -58.75% | 0.167 |

## Files

- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.
- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.
- [`grading_history.csv`](grading_history.csv): append-only grading history.
- [`latest_forecast.json`](latest_forecast.json): latest forecast review snapshot.
- [`latest_grading.json`](latest_grading.json): latest grading review snapshot.
- [`latest_deployment_gate.json`](latest_deployment_gate.json): latest deployment-gate state.
- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.

Registered forecast runs: **48**  
Registered grading runs: **49**
