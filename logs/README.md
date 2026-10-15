# GB Platform Review Logs

This folder is the human-readable review layer. The append-only files under `live/` remain the raw source of truth.

## Current deployment gate

- **Mode:** `shadow_only`
- **Deployment ready:** `False`
- **Graded days:** 73 / 30
- **Model MAE:** 66.16 GBP/MWh
- **Persistence MAE:** 43.53 GBP/MWh
- **Improvement:** -51.97%
- **P10–P90 coverage:** 0.060

## Latest daily results

| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-10-15 | 60.11 | 11,035.26 | 12,639.11 | — | — | — | — |
| 2026-10-14 | 65.36 | 12,531.61 | 14,269.79 | 107.35 | 32.28 | -232.54% | 0.000 |
| 2026-10-13 | 55.05 | 14,573.94 | 16,615.24 | 70.13 | 34.83 | -101.36% | 0.000 |
| 2026-10-12 | 74.65 | 10,541.42 | 12,604.02 | 79.85 | 82.82 | 3.58% | 0.000 |
| 2026-10-11 | 80.31 | 12,433.82 | 14,285.30 | 78.49 | 101.49 | 22.66% | 0.000 |
| 2026-10-10 | 24.32 | 4,860.34 | 6,535.18 | 56.93 | 75.16 | 24.26% | 0.146 |
| 2026-10-09 | 31.72 | 6,664.75 | 8,352.29 | 28.23 | 102.15 | 72.37% | 0.312 |
| 2026-10-08 | 65.37 | 9,992.68 | 12,218.59 | 74.33 | 51.37 | -44.71% | 0.042 |
| 2026-10-07 | 74.82 | 7,129.76 | 8,813.29 | 84.64 | 51.38 | -64.75% | 0.000 |
| 2026-10-06 | 99.61 | 6,596.15 | 8,151.85 | 90.89 | 73.82 | -23.12% | 0.000 |
| 2026-10-05 | 69.14 | 8,145.09 | 10,001.50 | 58.95 | 43.89 | -34.32% | 0.062 |
| 2026-10-04 | 76.28 | 16,689.70 | 19,097.87 | 55.51 | 39.86 | -39.27% | 0.083 |
| 2026-10-02 | 73.26 | 19,182.41 | 21,118.88 | 80.55 | 37.55 | -114.51% | 0.000 |
| 2026-10-01 | 81.01 | 9,962.13 | 11,287.00 | 70.87 | 19.13 | -270.52% | 0.000 |

## Files

- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.
- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.
- [`grading_history.csv`](grading_history.csv): append-only grading history.
- [`latest_forecast.json`](latest_forecast.json): latest forecast review snapshot.
- [`latest_grading.json`](latest_grading.json): latest grading review snapshot.
- [`latest_deployment_gate.json`](latest_deployment_gate.json): latest deployment-gate state.
- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.

Registered forecast runs: **73**  
Registered grading runs: **74**
