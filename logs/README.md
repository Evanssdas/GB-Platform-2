# GB Platform Review Logs

This folder is the human-readable review layer. The append-only files under `live/` remain the raw source of truth.

## Current deployment gate

- **Mode:** `shadow_only`
- **Deployment ready:** `False`
- **Graded days:** 54 / 30
- **Model MAE:** 65.05 GBP/MWh
- **Persistence MAE:** 33.28 GBP/MWh
- **Improvement:** -95.47%
- **P10–P90 coverage:** 0.062

## Latest daily results

| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-09-26 | 67.66 | 19,987.38 | 22,261.08 | — | — | — | — |
| 2026-09-25 | 85.18 | 13,950.27 | 15,449.50 | — | — | — | — |
| 2026-09-24 | 77.28 | 6,713.28 | 8,701.98 | 88.69 | 15.93 | -456.91% | 0.000 |
| 2026-09-23 | 81.45 | 12,500.72 | 14,461.46 | 70.59 | 13.51 | -422.66% | 0.000 |
| 2026-09-22 | 93.11 | 6,804.09 | 8,389.11 | 65.41 | 20.09 | -225.50% | 0.000 |
| 2026-09-21 | 92.54 | 3,090.31 | 4,623.01 | 74.52 | 119.94 | 37.87% | 0.000 |
| 2026-09-20 | 47.96 | 4,528.65 | 6,198.03 | 42.44 | 33.29 | -27.49% | 0.021 |
| 2026-09-19 | 25.21 | 6,120.14 | 7,781.21 | 15.03 | 64.33 | 76.64% | 0.562 |
| 2026-09-18 | 45.84 | 10,542.48 | 12,819.29 | 44.15 | 36.97 | -19.40% | 0.312 |
| 2026-09-17 | 39.60 | 9,667.48 | 12,056.66 | 61.87 | 56.52 | -9.47% | 0.229 |
| 2026-09-16 | 79.38 | 16,959.46 | 18,676.58 | 74.96 | 33.17 | -125.99% | 0.000 |
| 2026-09-15 | 63.86 | 17,008.34 | 19,407.69 | 86.88 | 37.22 | -133.41% | 0.125 |
| 2026-09-14 | 82.73 | 13,903.62 | 15,465.59 | 97.03 | 25.06 | -287.19% | 0.000 |
| 2026-09-13 | 76.59 | 17,672.12 | 19,710.96 | 118.89 | 96.99 | -22.57% | 0.000 |

## Files

- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.
- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.
- [`grading_history.csv`](grading_history.csv): append-only grading history.
- [`latest_forecast.json`](latest_forecast.json): latest forecast review snapshot.
- [`latest_grading.json`](latest_grading.json): latest grading review snapshot.
- [`latest_deployment_gate.json`](latest_deployment_gate.json): latest deployment-gate state.
- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.

Registered forecast runs: **55**  
Registered grading runs: **55**
