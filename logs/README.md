# GB Platform Review Logs

This folder is the human-readable review layer. The append-only files under `live/` remain the raw source of truth.

## Current deployment gate

- **Mode:** `shadow_only`
- **Deployment ready:** `False`
- **Graded days:** 7 / 30
- **Model MAE:** 46.08 GBP/MWh
- **Persistence MAE:** 22.90 GBP/MWh
- **Improvement:** -101.18%
- **P10–P90 coverage:** 0.074

## Latest daily results

| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-08-10 | 83.88 | 15,585.86 | 17,098.76 | — | — | — | — |
| 2026-08-09 | 66.93 | 15,981.97 | 18,008.08 | — | — | — | — |
| 2026-08-08 | 56.51 | 15,407.93 | 17,904.82 | 43.24 | 32.21 | -34.25% | 0.125 |
| 2026-08-07 | 70.20 | 13,846.52 | 15,304.53 | 39.07 | 13.35 | -192.59% | 0.083 |
| 2026-08-06 | 59.51 | 15,979.38 | 18,170.12 | 55.10 | 35.56 | -54.96% | 0.021 |
| 2026-08-05 | 69.09 | 26,440.87 | 28,375.67 | 37.17 | 38.52 | 3.51% | 0.146 |
| 2026-08-04 | 70.83 | 15,821.87 | 17,843.04 | 49.23 | 8.13 | -505.51% | 0.000 |
| 2026-08-03 | 73.59 | 20,313.97 | 22,333.77 | 52.13 | 10.41 | -400.94% | 0.000 |
| 2026-08-02 | — | — | — | — | — | — | — |
| 2026-08-01 | 64.26 | 13,446.30 | 15,130.52 | 49.83 | 10.92 | -356.28% | 0.146 |

## Files

- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.
- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.
- [`grading_history.csv`](grading_history.csv): append-only grading history.
- [`latest_forecast.json`](latest_forecast.json): latest forecast review snapshot.
- [`latest_grading.json`](latest_grading.json): latest grading review snapshot.
- [`latest_deployment_gate.json`](latest_deployment_gate.json): latest deployment-gate state.
- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.

Registered forecast runs: **9**  
Registered grading runs: **8**
