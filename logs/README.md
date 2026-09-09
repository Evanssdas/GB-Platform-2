# GB Platform Review Logs

This folder is the human-readable review layer. The append-only files under `live/` remain the raw source of truth.

## Current deployment gate

- **Mode:** `shadow_only`
- **Deployment ready:** `False`
- **Graded days:** 38 / 30
- **Model MAE:** 60.93 GBP/MWh
- **Persistence MAE:** 27.45 GBP/MWh
- **Improvement:** -121.99%
- **P10–P90 coverage:** 0.055

## Latest daily results

| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-09-09 | 66.13 | 8,741.20 | 10,663.53 | — | — | — | — |
| 2026-09-08 | 36.32 | 9,994.05 | 12,333.79 | 108.32 | 19.89 | -444.54% | 0.000 |
| 2026-09-07 | 40.60 | 11,764.97 | 13,837.98 | 97.62 | 61.34 | -59.14% | 0.000 |
| 2026-09-06 | 40.37 | 11,752.85 | 13,826.21 | 64.45 | 40.60 | -58.75% | 0.167 |
| 2026-09-05 | 41.04 | 6,274.16 | 8,000.79 | 40.79 | 86.06 | 52.60% | 0.375 |
| 2026-09-04 | 35.31 | 12,027.53 | 13,767.19 | 51.71 | 41.03 | -26.03% | 0.188 |
| 2026-09-03 | — | — | — | 69.91 | 47.36 | -47.62% | 0.104 |
| 2026-09-02 | 86.59 | 13,755.34 | 15,116.28 | 80.21 | 49.03 | -63.61% | 0.000 |
| 2026-09-01 | 66.47 | 16,166.49 | 18,168.46 | 54.98 | 18.97 | -189.90% | 0.229 |
| 2026-08-31 | 63.43 | 15,029.18 | 17,090.56 | 68.87 | 31.60 | -117.96% | 0.042 |
| 2026-08-30 | 65.36 | 16,484.34 | 18,548.22 | 92.17 | 30.79 | -199.36% | 0.000 |
| 2026-08-29 | 71.56 | 18,786.78 | 20,728.85 | 56.09 | 35.79 | -56.72% | 0.062 |
| 2026-08-28 | 74.25 | 16,471.28 | 18,223.17 | 61.80 | 37.55 | -64.58% | 0.000 |
| 2026-08-27 | 72.81 | 16,982.24 | 18,988.22 | 91.40 | 25.15 | -263.34% | 0.000 |

## Files

- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.
- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.
- [`grading_history.csv`](grading_history.csv): append-only grading history.
- [`latest_forecast.json`](latest_forecast.json): latest forecast review snapshot.
- [`latest_grading.json`](latest_grading.json): latest grading review snapshot.
- [`latest_deployment_gate.json`](latest_deployment_gate.json): latest deployment-gate state.
- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.

Registered forecast runs: **38**  
Registered grading runs: **39**
