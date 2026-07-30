# Real-data implementation runbook

This branch replaces the synthetic-only training path with auditable collection,
point-in-time reconstruction, leakage-safe stacking and immutable live grading.

## 1. Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

## 2. Collect Elexon core history

```bash
gb-v2 collect-elexon \
  --start 2024-01-01 \
  --end 2024-03-31 \
  --output data/parsed/elexon
```

This creates half-hourly APXMIDP, demand, fuel-type generation and interconnector
outturn files. Inspect the fuel columns before entering the exact wind and nuclear
column names in `config/data_mapping.yaml`.

## 3. Collect embedded forecasts and inertia

```bash
gb-v2 collect-neso-preset \
  --name embedded_2025 \
  --output data/parsed/neso/embedded_2025.parquet

gb-v2 collect-neso-preset \
  --name embedded_2026_h1 \
  --output data/parsed/neso/embedded_2026_h1.parquet

gb-v2 collect-neso-preset \
  --name inertia_2026_27 \
  --output data/parsed/neso/inertia_2026_27.parquet
```

The embedded parser preserves `published_at_utc` so the dataset builder can select
only the latest revision available at the D-1 issue time.

## 4. Collect point-in-time weather

```bash
gb-v2 collect-weather --group demand --start 2024-01-01 --end 2024-03-31 \
  --output data/parsed/weather/demand.parquet

gb-v2 collect-weather --group wind --start 2024-01-01 --end 2024-03-31 \
  --output data/parsed/weather/wind.parquet

gb-v2 collect-weather --group solar --start 2024-01-01 --end 2024-03-31 \
  --output data/parsed/weather/solar.parquet
```

The default variables use Open-Meteo `_previous_day1` fields, representing a
fixed 24-hour lead rather than realised weather.

## 5. Build storage output from reviewed BM units

```bash
gb-v2 collect-elexon-units \
  --start 2024-01-01 \
  --end 2024-03-31 \
  --output data/parsed/elexon
```

Copy `config/bm_unit_mapping.example.csv`, replace every placeholder with a
reviewed BM unit and assign `battery` or `pumped_storage`. Run the Python helper:

```python
from gb_platform_v2.storage_mapping import build_storage_series

build_storage_series(
    "data/parsed/elexon/elexon_unit_generation.parquet",
    "config/bm_unit_mapping.csv",
    "data/parsed/elexon/elexon_storage.parquet",
)
```

No unit is classified as storage automatically from its name.

## 6. Assemble the half-hourly table

Copy the mapping template:

```bash
copy config\data_mapping.example.yaml config\data_mapping.yaml
```

Set the exact FUELHH wind and nuclear columns, then run:

```bash
gb-v2 build-dataset \
  --mapping config/data_mapping.yaml \
  --output data/processed/gb_half_hourly.parquet
```

The builder stops if required targets are missing. It does not replace missing
imports, batteries or inertia with zero.

## 7. Train chronologically

```bash
gb-v2 train \
  --input data/processed/gb_half_hourly.parquet \
  --models models/live \
  --holdout-rows 4320 \
  --time-series-splits 5
```

Component forecasts used by the price model are expanding-window out-of-fold
predictions. Monte Carlo error rows are also out-of-fold errors, not in-sample
residuals.

## 8. Live forecast and immutable grading

```bash
gb-v2 live-forecast \
  --input data/live/tomorrow_features.parquet \
  --models models/live \
  --output outputs/live \
  --forecasts live/forecasts.csv \
  --model-version 2026-08-v1 \
  --issue-time-utc 2026-08-01T12:00:00Z
```

Append actual APXMIDP values:

```bash
gb-v2 collect-actuals \
  --start 2026-08-02 \
  --end 2026-08-03 \
  --actuals live/actuals.csv \
  --revision initial
```

Grade without changing the original forecasts:

```bash
gb-v2 grade \
  --forecasts live/forecasts.csv \
  --actuals live/actuals.csv \
  --scores live/scores.csv
```

## Still gated

- ENTSO-E collection is disabled until `ENTSOE_TOKEN` is available.
- JAO products remain disabled until each exact publication path and schema is
  entered in `config/jao_publications.yaml`.
- Curtailment and nuclear modulation require defensible operational labels; they
  are not fabricated from realised output alone.
- Historical inertia coverage must be extended with the appropriate yearly NESO
  resources before training across several years.
