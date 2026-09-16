# GB day-ahead market report — 2026-09-17

**Model:** `core-12m-operational-v1`  
**Profile:** `core_without_battery`  
**Issue time:** `2026-09-16T15:35:04.163588+00:00`  
**Monte Carlo scenarios:** `1,000`  
**Settlement periods:** `48`

## Executive summary

- P50 price range: **£4.74–£82.94/MWh**; daily mean **£39.60/MWh**.
- Peak demand: **29,443 MW** at **2026-09-17 19:30 BST**.
- Peak residual demand after nuclear: **8,638 MW** at **2026-09-17 20:00 BST**.
- Scenario VaR for the illustrative 100 MWh position: **£9,667.48**.
- Expected Shortfall: **£12,056.66**.
- Maximum volume under the VaR limit: **103.44 MWh**.
- Conservative binding maximum under both VaR and Expected Shortfall: **82.94 MWh**.

> Position limits are illustrative paper-risk outputs, not autonomous trading authorisation or financial advice.

## Demand, wind, solar and nuclear

![System components](plots/01_system_components.png)

![Wind and solar breakdown](plots/03_wind_solar_breakdown.png)

### Daily energy summary

| metric | value | unit |
|---|---|---|
| Demand energy | 578,521.0 | MWh |
| Total wind energy | 414,396.4 | MWh |
| Solar energy | 51,406.4 | MWh |
| Nuclear energy | 72,651.5 | MWh |
| Net import energy | 21,842.5 | MWh |

### Component forecast sources

| component | source |
|---|---|
| demand_mw | fallback_d7 |
| embedded_solar_mw | model |
| embedded_wind_mw | model |
| inertia_gvas | model |
| net_import_mw | model |
| nuclear_mw | fallback_d7 |
| transmission_wind_mw | model |

## Residual demand and system balance

![Residual demand](plots/02_residual_demand.png)

Definitions:

- `residual_before_nuclear_mw = demand_mw - total_wind_mw - embedded_solar_mw`
- `residual_after_nuclear_mw = residual_before_nuclear_mw - nuclear_mw`
- `net_system_short_mw = residual_after_nuclear_mw - net_import_mw`

![Net imports and inertia](plots/04_net_imports_and_inertia.png)

## Probabilistic price forecast

![Price fan](plots/05_price_fan.png)

![Negative-price probability](plots/06_negative_price_probability.png)

## VaR, Expected Shortfall and maximum permissible volume

The position limit uses the explicitly labelled paper assumptions below. Risk is scaled linearly from the Monte Carlo result for the reference position.

| metric | value | unit |
|---|---|---|
| Paper capital | 500,000.00 | GBP |
| Daily VaR appetite | 2.00 | % capital |
| Daily risk budget | 10,000.00 | GBP |
| Confidence level | 95.00 | % |
| Reference position | 100.00 | MWh |
| Scenario VaR | 9,667.48 | GBP |
| Expected Shortfall | 12,056.66 | GBP |
| Worst simulated loss | 16,836.97 | GBP |
| Best simulated profit | 17,475.81 | GBP |
| VaR budget utilisation | 96.67 | % |
| ES budget utilisation | 120.57 | % |
| Maximum volume by VaR | 103.44 | MWh |
| Maximum volume by Expected Shortfall | 82.94 | MWh |
| Binding maximum permissible volume | 82.94 | MWh |

![Risk position limits](plots/07_risk_position_limits.png)

## Detailed tables

- [Half-hourly system and price table](half_hourly_system_and_price_table.csv)
- [Daily system summary](daily_system_summary.csv)
- [VaR and position limits](var_and_position_limits.csv)
- [Machine-readable report](report.json)
