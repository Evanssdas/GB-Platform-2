"""Known NESO CKAN resources and parsers used by the GB platform."""

from __future__ import annotations

import pandas as pd

from ..timebase import settlement_periods_for_day

NESO_RESOURCES = {
    "embedded_current": "db6c038f-98af-4570-ab60-24d71ebd0ae5",
    "embedded_2026_h1": "d6375700-69c2-4c25-8bde-883a205d742e",
    "embedded_2025": "fc13df13-2dad-4a1c-b9e3-4569efba4955",
    "embedded_2024": "06abd00a-ef6b-488b-9b6d-5e08fdc0c890",
    "inertia_2026_27": "3ff8b466-5c16-4713-abfe-ad332298f15f",
    "inertia_2025_26": "936daa4f-fca4-4c6a-968a-884f3d77bafe",
    "inertia_2024_25": "7a12d0bd-448d-42a9-b333-4a32761dbad4",
    "inertia_2023_24": "5bd6ec4d-a2df-4c94-9b27-fdf8cf04d7dd",
    "historic_demand_2025": "b2bde559-3455-4021-b179-dfe60c0337b0",
    "inertia_cost": "6295f4ed-b43d-4a80-8ca9-c27c9fa16517",
}


def _normalise_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.columns = [
        str(column).strip().lower().replace(" ", "_").replace("-", "_")
        for column in out.columns
    ]
    return out


def _settlement_timestamp(date: pd.Series, period: pd.Series) -> pd.Series:
    values: list[pd.Timestamp] = []
    for day, sp in zip(
        pd.to_datetime(date, errors="coerce"),
        pd.to_numeric(period, errors="coerce"),
    ):
        if pd.isna(day) or pd.isna(sp):
            values.append(pd.NaT)
            continue
        periods = settlement_periods_for_day(pd.Timestamp(day).normalize())
        position = int(sp) - 1
        values.append(
            periods[position].tz_convert("UTC") if 0 <= position < len(periods) else pd.NaT
        )
    return pd.Series(pd.DatetimeIndex(values), index=date.index)


def parse_embedded_forecasts(records: list[dict]) -> pd.DataFrame:
    frame = _normalise_columns(pd.DataFrame(records))
    required = {
        "settlement_date",
        "settlement_period",
        "embedded_wind_forecast",
        "embedded_solar_forecast",
        "forecast_datetime",
    }
    missing = required - set(frame)
    if missing:
        raise KeyError(f"Embedded forecast resource is missing columns: {sorted(missing)}")
    out = pd.DataFrame(
        {
            "timestamp": _settlement_timestamp(
                frame["settlement_date"], frame["settlement_period"]
            ),
            "settlement_date": pd.to_datetime(
                frame["settlement_date"], errors="coerce"
            ).dt.date,
            "settlement_period": pd.to_numeric(
                frame["settlement_period"], errors="coerce"
            ),
            "embedded_wind_mw": pd.to_numeric(
                frame["embedded_wind_forecast"], errors="coerce"
            ),
            "embedded_solar_mw": pd.to_numeric(
                frame["embedded_solar_forecast"], errors="coerce"
            ),
            "published_at_utc": pd.to_datetime(
                frame["forecast_datetime"], errors="coerce", utc=True
            ),
        }
    )
    for source, target in (
        ("embedded_wind_capacity", "embedded_wind_capacity_mw"),
        ("embedded_solar_capacity", "embedded_solar_capacity_mw"),
    ):
        if source in frame:
            out[target] = pd.to_numeric(frame[source], errors="coerce")
    return out.dropna(subset=["timestamp", "published_at_utc"]).sort_values(
        ["timestamp", "published_at_utc"]
    )


def parse_inertia(records: list[dict]) -> pd.DataFrame:
    frame = _normalise_columns(pd.DataFrame(records))
    aliases = {
        "settlement_date": ["settlement_date"],
        "settlement_period": ["settlement_period"],
        "outturn_inertia_gvas": ["outturn_inertia", "outturn_inertia_gva_s"],
        "market_provided_inertia_gvas": [
            "market_provided_inertia",
            "market_provided_inertia_gva_s",
        ],
    }
    selected: dict[str, str] = {}
    for target, candidates in aliases.items():
        source = next((candidate for candidate in candidates if candidate in frame), None)
        if source is None:
            raise KeyError(f"Inertia resource is missing a column for {target}")
        selected[target] = source
    out = pd.DataFrame(
        {
            "timestamp": _settlement_timestamp(
                frame[selected["settlement_date"]],
                frame[selected["settlement_period"]],
            ),
            "settlement_date": pd.to_datetime(
                frame[selected["settlement_date"]], errors="coerce"
            ).dt.date,
            "settlement_period": pd.to_numeric(
                frame[selected["settlement_period"]], errors="coerce"
            ),
            "outturn_inertia_gvas": pd.to_numeric(
                frame[selected["outturn_inertia_gvas"]], errors="coerce"
            ),
            "market_provided_inertia_gvas": pd.to_numeric(
                frame[selected["market_provided_inertia_gvas"]], errors="coerce"
            ),
        }
    )
    out["inertia_intervention_gap_gvas"] = (
        out["outturn_inertia_gvas"] - out["market_provided_inertia_gvas"]
    )
    return out.dropna(subset=["timestamp"]).sort_values("timestamp")
