# GB Platform Review Logs

This folder is the human-readable review layer. The append-only files under `live/` remain the raw source of truth.

## Current deployment gate

No deployment-gate snapshot has been registered yet.

## Latest daily results

| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-08-03 | 73.59 | 20,313.97 | 22,333.77 | — | — | — | — |
| 2026-08-01 | 64.26 | 13,446.30 | 15,130.52 | — | — | — | — |

## Files

- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.
- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.
- [`grading_history.csv`](grading_history.csv): append-only grading history.
- [`latest_forecast.json`](latest_forecast.json): latest forecast review snapshot.
- [`latest_grading.json`](latest_grading.json): latest grading review snapshot.
- [`latest_deployment_gate.json`](latest_deployment_gate.json): latest deployment-gate state.
- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.

Registered forecast runs: **2**  
Registered grading runs: **0**
