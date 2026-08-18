# GB day-ahead market report — 2026-08-19

**Model:** `core-12m-operational-v1`  
**Profile:** `core_without_battery`  
**Issue time:** `2026-08-18T12:15:54.487165+00:00`  
**Monte Carlo scenarios:** `1,000`  
**Settlement periods:** `48`

## Executive summary

- P50 price range: **£67.28–£110.08/MWh**; daily mean **£84.15/MWh**.
- Peak demand: **29,773 MW** at **2026-08-19 20:00 BST**.
- Peak residual demand after nuclear: **19,364 MW** at **2026-08-19 20:30 BST**.
- Scenario VaR for the illustrative 100 MWh position: **£11,192.54**.
- Expected Shortfall: **£12,840.41**.
- Maximum volume under the VaR limit: **89.35 MWh**.
- Conservative binding maximum under both VaR and Expected Shortfall: **77.88 MWh**.

> Position limits are illustrative paper-risk outputs, not autonomous trading authorisation or financial advice.

## Demand, wind, solar and nuclear

![System components](plots/01_system_components.png)

![Wind and solar breakdown](plots/03_wind_solar_breakdown.png)

### Daily energy summary

| metric | value | unit |
|---|---|---|
| Demand energy | 553,581.5 | MWh |
| Total wind energy | 164,203.2 | MWh |
| Solar energy | 57,235.5 | MWh |
| Nuclear energy | 90,942.5 | MWh |
| Net import energy | 86,526.7 | MWh |

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
| Scenario VaR | 11,192.54 | GBP |
| Expected Shortfall | 12,840.41 | GBP |
| Worst simulated loss | 15,348.94 | GBP |
| Best simulated profit | 4,258.03 | GBP |
| VaR budget utilisation | 111.93 | % |
| ES budget utilisation | 128.40 | % |
| Maximum volume by VaR | 89.35 | MWh |
| Maximum volume by Expected Shortfall | 77.88 | MWh |
| Binding maximum permissible volume | 77.88 | MWh |

![Risk position limits](plots/07_risk_position_limits.png)

## Detailed tables

- [Half-hourly system and price table](half_hourly_system_and_price_table.csv)
- [Daily system summary](daily_system_summary.csv)
- [VaR and position limits](var_and_position_limits.csv)
- [Machine-readable report](report.json)
