# GB Platform Review Logs

This folder is the easy-to-open review layer. The append-only files under `live/` remain the raw source of truth.

## Current deployment gate

- **Mode:** `shadow_only`
- **Deployment ready:** `false`
- **Graded days:** 0 / 30
- **Model MAE:** —
- **Persistence MAE:** —
- **Improvement:** —
- **P10–P90 coverage:** —

## Latest daily results

| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-08-01 | 64.26 | 13,446.30 | 15,130.52 | — | — | — | — |

## Files

- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.
- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.
- `grading_history.csv`: created automatically after the first matching grading run.
- `latest_forecast.json`: updated to the latest forecast snapshot.
- `latest_grading.json`: created after the first matching grading run.
- `latest_deployment_gate.json`: updated by daily grading.
- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.

Registered forecast runs: **1**  
Registered grading runs: **0**
