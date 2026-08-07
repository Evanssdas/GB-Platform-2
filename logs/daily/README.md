# GB daily forecast history

Each dated folder preserves the 30-minute forecast table, plots, model metadata and grading status for that GB delivery day.

| Delivery day | Forecast report | Grading | Model MAE | Persistence MAE | Improvement | P10–P90 coverage |
|---|---|---|---:|---:|---:|---:|
| 2026-08-07 | [2026-08-07](2026-08-07/README.md) | Pending | — | — | — | — |
| 2026-08-06 | [2026-08-06](2026-08-06/README.md) | Graded (48 periods) | 55.10 | 35.56 | -54.96% | 0.021 |
| 2026-08-05 | [2026-08-05](2026-08-05/README.md) | Graded (48 periods) | 37.17 | 38.52 | 3.51% | 0.146 |
| 2026-08-04 | [2026-08-04](2026-08-04/README.md) | Graded (48 periods) | 49.23 | 8.13 | -505.51% | 0.000 |
| 2026-08-03 | 2026-08-03 | Graded (48 periods) | 52.13 | 10.41 | -400.94% | 0.000 |
| 2026-08-02 | 2026-08-02 | Pending | — | — | — | — |
| 2026-08-01 | 2026-08-01 | Graded (48 periods) | 49.83 | 10.92 | -356.28% | 0.146 |

## Permanent source files

- [`../daily_summary.csv`](../daily_summary.csv): one row per delivery day.
- [`../../live/forecasts.csv`](../../live/forecasts.csv): immutable half-hourly forecast log.
- [`../../live/actuals.csv`](../../live/actuals.csv): collected market actuals.
- [`../../live/scores.csv`](../../live/scores.csv): reproducible half-hourly grading records.
