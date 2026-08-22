# GB daily forecast history

Each dated folder preserves the 30-minute forecast table, plots, model metadata and grading status for that GB delivery day.

| Delivery day | Forecast report | Grading | Model MAE | Persistence MAE | Improvement | P10–P90 coverage |
|---|---|---|---:|---:|---:|---:|
| 2026-08-22 | [2026-08-22](2026-08-22/README.md) | Pending | — | — | — | — |
| 2026-08-21 | [2026-08-21](2026-08-21/README.md) | Graded (48 periods) | 51.82 | 10.46 | -395.64% | 0.000 |
| 2026-08-20 | [2026-08-20](2026-08-20/README.md) | Graded (48 periods) | 61.66 | 14.27 | -332.21% | 0.000 |
| 2026-08-19 | [2026-08-19](2026-08-19/README.md) | Graded (48 periods) | 73.81 | 17.14 | -330.57% | 0.000 |
| 2026-08-18 | [2026-08-18](2026-08-18/README.md) | Graded (48 periods) | 88.53 | 19.41 | -356.08% | 0.000 |
| 2026-08-17 | [2026-08-17](2026-08-17/README.md) | Graded (48 periods) | 77.36 | 22.61 | -242.13% | 0.000 |
| 2026-08-16 | [2026-08-16](2026-08-16/README.md) | Graded (48 periods) | 68.70 | 9.01 | -662.68% | 0.000 |
| 2026-08-15 | [2026-08-15](2026-08-15/README.md) | Graded (48 periods) | 74.16 | 12.97 | -471.81% | 0.000 |
| 2026-08-14 | [2026-08-14](2026-08-14/README.md) | Graded (48 periods) | 57.92 | 13.40 | -332.10% | 0.000 |
| 2026-08-13 | [2026-08-13](2026-08-13/README.md) | Graded (48 periods) | 51.78 | 11.82 | -338.01% | 0.000 |
| 2026-08-12 | [2026-08-12](2026-08-12/README.md) | Graded (48 periods) | 54.97 | 21.50 | -155.71% | 0.000 |
| 2026-08-11 | [2026-08-11](2026-08-11/README.md) | Graded (48 periods) | 49.22 | 16.33 | -201.44% | 0.000 |
| 2026-08-10 | [2026-08-10](2026-08-10/README.md) | Graded (48 periods) | 35.24 | 33.44 | -5.38% | 0.000 |
| 2026-08-09 | [2026-08-09](2026-08-09/README.md) | Graded (48 periods) | 37.28 | 15.90 | -134.43% | 0.125 |
| 2026-08-08 | [2026-08-08](2026-08-08/README.md) | Graded (48 periods) | 43.24 | 32.21 | -34.25% | 0.125 |
| 2026-08-07 | [2026-08-07](2026-08-07/README.md) | Graded (48 periods) | 39.07 | 13.35 | -192.59% | 0.083 |
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
