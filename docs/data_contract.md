# Prepared half-hourly data contract

The training command expects one row per GB settlement period with a timezone-aware or UTC-parsable `timestamp` column.

## Required physical targets

- `demand_mw`
- `embedded_wind_mw`
- `embedded_solar_mw`
- `transmission_wind_mw`
- `nuclear_mw`
- `net_import_mw` — positive means net imports into GB
- `battery_net_mw` — positive means discharge to the grid; negative means charging
- `inertia_gvas`
- `price_gbp_mwh`

## Recommended operational columns

- `curtailed_wind_mw`
- `curtailed_solar_mw`
- `nuclear_available_mw`
- `nuclear_outage_mw`
- `nuclear_planned_outage_mw`
- `nuclear_unplanned_outage_mw`
- `interconnector_available_mw`
- separate flow/capacity columns for IFA, IFA2, BritNed, Nemo, NSL, Viking, ElecLink and Moyle/EWIC where available
- `battery_power_capacity_mw`
- `battery_energy_capacity_mwh`
- `battery_soc_mwh`
- `market_provided_inertia_gvas`
- `outturn_inertia_gvas`
- `largest_loss_mw`
- gas, carbon and technology-SRMC estimates

## Recommended weather columns

Use multi-location weighted and dispersion features rather than one London point:

- `temperature_c`
- `temperature_max_c`
- `temperature_min_c`
- `wind_speed_ms`
- `wind_gust_ms`
- `wind_speed_std_ms`
- `solar_radiation_wm2`
- `cloud_cover_percent`
- `precipitation_mm`

## Point-in-time rule

Every training feature must represent information that was genuinely available when the forecast would have been issued. Do not train a D-1 forecast on realised weather, final outage revisions or physical flows published after delivery unless the goal is explicitly an explanatory model rather than a forecast.

Recommended practice:

1. store `issue_time_utc` and `delivery_time_utc`;
2. preserve source revision timestamps;
3. use archived weather forecasts at the same lead time as live operation;
4. use only outage and capacity messages published before the issue time;
5. train and validate chronologically;
6. compare each target with a simple persistence or market baseline.

## Embedded demand clarification

Embedded generation is not demand. In GB it can reduce transmission-system demand, so maintain clear definitions for:

- underlying or total consumer demand where estimated;
- transmission-system demand;
- embedded wind and solar generation;
- demand net of embedded generation.

Never subtract embedded generation twice.

## Curtailment and modulation

Realised renewable and nuclear output are valid final targets, but operational causes should be represented separately where possible:

- potential renewable output;
- curtailed volume;
- available nuclear capacity;
- outage volume;
- modulation = available capacity minus realised output, subject to definition and data quality.

## Marginal-technology labels

A `marginal_technology` label may be included for probabilistic classification, but it must state how it was inferred. APXMIDP does not directly reveal one exact price-setting plant. BM acceptance labels should distinguish energy actions from constraints, inertia, voltage and other operational actions.
