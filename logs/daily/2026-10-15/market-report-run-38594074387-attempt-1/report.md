# GB day-ahead market report — 2026-10-15

**Model:** `core-12m-operational-v1`  
**Profile:** `core_without_battery`  
**Issue time:** `2026-10-14T15:58:55.892461+00:00`  
**Monte Carlo scenarios:** `1,000`  
**Settlement periods:** `48`

## Executive summary

- P50 price range: **£21.14–£103.13/MWh**; daily mean **£60.11/MWh**.
- Peak demand: **34,097 MW** at **2026-10-15 19:00 BST**.
- Peak residual demand after nuclear: **15,319 MW** at **2026-10-15 18:30 BST**.
- Scenario VaR for the illustrative 100 MWh position: **£11,035.26**.
- Expected Shortfall: **£12,639.11**.
- Maximum volume under the VaR limit: **90.62 MWh**.
- Conservative binding maximum under both VaR and Expected Shortfall: **79.12 MWh**.

> Position limits are illustrative paper-risk outputs, not autonomous trading authorisation or financial advice.

## Demand, wind, solar and nuclear

![System components](plots/01_system_components.png)

![Wind and solar breakdown](plots/03_wind_solar_breakdown.png)

### Daily energy summary

| metric | value | unit |
|---|---|---|
| Demand energy | 624,050.5 | MWh |
| Total wind energy | 384,987.0 | MWh |
| Solar energy | 30,152.3 | MWh |
| Nuclear energy | 96,196.5 | MWh |
| Net import energy | 67,151.2 | MWh |

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
| Scenario VaR | 11,035.26 | GBP |
| Expected Shortfall | 12,639.11 | GBP |
| Worst simulated loss | 16,410.49 | GBP |
| Best simulated profit | 9,614.67 | GBP |
| VaR budget utilisation | 110.35 | % |
| ES budget utilisation | 126.39 | % |
| Maximum volume by VaR | 90.62 | MWh |
| Maximum volume by Expected Shortfall | 79.12 | MWh |
| Binding maximum permissible volume | 79.12 | MWh |

![Risk position limits](plots/07_risk_position_limits.png)

## Detailed tables

- [Half-hourly system and price table](half_hourly_system_and_price_table.csv)
- [Daily system summary](daily_system_summary.csv)
- [VaR and position limits](var_and_position_limits.csv)
- [Machine-readable report](report.json)
