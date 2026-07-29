# GB Power Market Platform V2

A half-hourly, probabilistic GB electricity-market research platform.

This repository is a major architectural upgrade from a daily peak-price prototype. It provides a tested framework for:

- 30-minute modelling with daylight-saving-aware 46/48/50 settlement-period days;
- signed price modelling with a scaled `arcsinh` target, including negative prices;
- demand, embedded wind, embedded solar, transmission wind, nuclear, storage, imports and inertia models;
- renewable-curtailment probability plus conditional curtailed volume;
- nuclear availability and modulation features;
- interconnector flow and capacity inputs from GB and European sources;
- battery power, energy and state-of-charge features;
- correlated Monte Carlo scenarios and P10/P50/P90 price paths;
- daily minimum, maximum and negative-price probabilities;
- legacy parametric VaR, historical-simulation VaR, scenario VaR and expected shortfall;
- a probabilistic marginal-technology model;
- an inertia model and frequency-security screening proxy;
- plots, daily JSON reports, tests and GitHub Actions.

## Status — read this first

The **software framework is implemented and testable**. The repository includes a reproducible synthetic-data demonstration so the complete pipeline can run without credentials.

It is **not yet a trained live trading model**. Real deployment requires:

1. historical point-in-time backfills from the selected sources;
2. API credentials where required;
3. source-specific schema validation;
4. chronological training and out-of-sample evaluation;
5. live forecast logging and grading over a meaningful period.

No synthetic result should be described as market performance.

## Model architecture

```text
weather + calendar + historical state
                 |
                 v
 demand / wind / solar / nuclear / imports / storage / inertia
                 |
                 v
     residual demand and system-tightness features
                 |
                 v
       signed half-hourly arcsinh price model
                 |
                 v
 correlated component-error or weather-ensemble scenarios
                 |
                 v
 P10 / P50 / P90 paths, negative-price probability,
 daily minimum/maximum, scenario VaR and expected shortfall
```

Operational side models:

```text
renewable potential -> curtailment classifier -> conditional volume regressor
system state        -> marginal-technology probability classifier
synchronous state   -> inertia regression -> low-inertia intervention signal
```

## Data sources represented

- **Elexon Insights/BMRS** — Market Index Data, FUELHH, demand, generation availability, REMIT, physical notifications and Balancing Mechanism data.
- **NESO Data Portal** — embedded generation, system inertia, constraints and other system datasets through CKAN.
- **Open-Meteo** — point forecasts, archived forecast runs and ensemble members.
- **ENTSO-E Transparency Platform** — outages, generation, load, day-ahead prices and cross-border physical flows, subject to token and product availability.
- **JAO Publication Tool** — border-capacity and market-coupling publications. Endpoint schemas are kept explicit because JAO products are not one universal table.

Official references:

- Elexon API: https://bmrs.elexon.co.uk/api-documentation/introduction
- NESO Data Portal: https://www.neso.energy/data-portal
- Open-Meteo: https://open-meteo.com/en/docs
- ENTSO-E Transparency Platform: https://transparency.entsoe.eu/
- JAO: https://www.jao.eu/

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Run the complete synthetic demonstration:

```bash
gb-v2 demo \
  --days 220 \
  --scenarios 1000 \
  --models models/demo \
  --output outputs/demo
```

The demonstration creates:

```text
outputs/demo/half_hourly_price_forecast.csv
outputs/demo/half_hourly_system_forecast.csv
outputs/demo/price_fan_chart.png
outputs/demo/daily_report.json
```

Train on a prepared real table:

```bash
gb-v2 train \
  --input data/processed/gb_half_hourly.parquet \
  --models models/live \
  --holdout-rows 4320
```

The prepared table contract is documented in `docs/data_contract.md`.

## Repository structure

```text
config/example.yaml                    settings and source endpoints
src/gb_platform_v2/data/              source clients
src/gb_platform_v2/timebase.py         DST-safe 30-minute time handling
src/gb_platform_v2/features.py         cyclical, weather and balance features
src/gb_platform_v2/transforms.py       signed arcsinh transform
src/gb_platform_v2/models.py           regressors, curtailment and marginal models
src/gb_platform_v2/system.py           battery and inertia/frequency screening
src/gb_platform_v2/scenarios.py        correlated Monte Carlo engine
src/gb_platform_v2/risk.py             parametric, historical and scenario risk
src/gb_platform_v2/reporting.py        daily summaries and fan charts
src/gb_platform_v2/pipeline.py         training and forecast orchestration
src/gb_platform_v2/synthetic.py        reproducible demo data only
tests/                                 unit and end-to-end tests
.github/workflows/                     CI and manual demo workflow
```

## Inertia and 50 Hz

The platform can model NESO market-provided or outturn inertia in GVA·s and estimate low-inertia risk. The included frequency output is intentionally called a **screening proxy**. A proper frequency-security assessment needs credible-loss assumptions, dynamic response timing, damping, reserve delivery, network conditions and NESO operating criteria. The code does not claim to certify that system frequency will remain at 50 Hz.

## Marginal plant limitation

The platform estimates probabilities for marginal **technologies**, such as CCGT, imports, batteries or scarcity plant. It does not claim to identify the exact plant setting APXMIDP. APXMIDP is a market-index price, and Balancing Mechanism actions can also be accepted for constraints, voltage, inertia and other reasons rather than pure national merit order.

## Monte Carlo design

The first implemented method bootstraps complete historical component-error rows. This preserves dependence between demand, wind, solar, nuclear, imports and inertia errors better than sampling each error independently.

A stronger live version can replace or supplement this with:

- Open-Meteo ensemble members;
- unit-level outage and return-to-service scenarios;
- interconnector-capacity scenarios;
- battery availability and state-of-charge scenarios;
- curtailment-event scenarios.

## Risk outputs

The platform keeps the earlier simple VaR concept but fixes the negative-price weakness by using absolute £/MWh changes rather than percentage returns. It also provides:

- historical-simulation VaR;
- scenario VaR from Monte Carlo P&L;
- expected shortfall;
- worst simulated loss.

All risk outputs are illustrative until calibrated to a real portfolio, contract shape and limits.

## Interview-safe description

> “V2 is a half-hourly probabilistic research platform rather than a daily peak-only model. It separates physical components, supports negative prices through arcsinh, includes embedded renewables, curtailment, nuclear availability, storage, interconnectors and inertia, and then propagates correlated uncertainty through the price model. The repository framework is implemented and tested; real market performance still depends on completing point-in-time backfills, training and live grading.”
