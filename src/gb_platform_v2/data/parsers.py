"""Source-specific parsing and schema validation.

The functions fail loudly when required fields are absent. Alias lists are used
only for known naming variations; silent positional parsing is deliberately
avoided.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def _records(payload: dict) -> list[dict]:
    for key in ("data", "records", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict) and isinstance(value.get("records"), list):
            return value["records"]
    raise KeyError("Could not find a record list in source payload")


def _column(frame: pd.DataFrame, aliases: Iterable[str], label: str) -> str:
    lower = {str(column).lower(): str(column) for column in frame.columns}
    for alias in aliases:
        if alias.lower() in lower:
            return lower[alias.lower()]
    raise KeyError(f"Missing required {label}; tried aliases {list(aliases)}")


def _settlement_timestamp(date: pd.Series, period: pd.Series) -> pd.Series:
    day = pd.to_datetime(date, errors="coerce")
    sp = pd.to_numeric(period, errors="coerce")
    return (day + pd.to_timedelta((sp - 1) * 30, unit="m")).dt.tz_localize(
        "Europe/London",
        ambiguous="infer",
        nonexistent="shift_forward",
    ).dt.tz_convert("UTC")


def parse_elexon_mid(payload: dict) -> pd.DataFrame:
    frame = pd.DataFrame(_records(payload))
    date = _column(frame, ["settlementDate", "settlement_date"], "settlement date")
    period = _column(frame, ["settlementPeriod", "settlement_period"], "settlement period")
    price = _column(frame, ["price", "marketIndexPrice", "market_index_price"], "price")
    provider = _column(frame, ["dataProvider", "data_provider"], "data provider")
    volume = _column(frame, ["volume", "marketIndexVolume", "market_index_volume"], "volume")

    out = pd.DataFrame(
        {
            "timestamp": _settlement_timestamp(frame[date], frame[period]),
            "settlement_date": pd.to_datetime(frame[date]).dt.date,
            "settlement_period": pd.to_numeric(frame[period], errors="coerce"),
            "data_provider": frame[provider].astype(str),
            "price_gbp_mwh": pd.to_numeric(frame[price], errors="coerce"),
            "market_index_volume_mwh": pd.to_numeric(frame[volume], errors="coerce"),
        }
    )
    out = out.loc[out["data_provider"].eq("APXMIDP")]
    return out.dropna(subset=["timestamp", "price_gbp_mwh"]).sort_values("timestamp")


def parse_elexon_fuelhh(payload: dict) -> pd.DataFrame:
    frame = pd.DataFrame(_records(payload))
    date = _column(frame, ["settlementDate", "settlement_date"], "settlement date")
    period = _column(frame, ["settlementPeriod", "settlement_period"], "settlement period")
    fuel = _column(frame, ["fuelType", "fuel_type"], "fuel type")
    value = _column(frame, ["generation", "quantity", "value"], "generation")
    frame["timestamp"] = _settlement_timestamp(frame[date], frame[period])
    frame["fuel_type"] = frame[fuel].astype(str).str.upper()
    frame["generation_mw"] = pd.to_numeric(frame[value], errors="coerce")
    wide = frame.pivot_table(
        index="timestamp",
        columns="fuel_type",
        values="generation_mw",
        aggfunc="sum",
    )
    wide.columns = [f"fuel_{column.lower()}_mw" for column in wide.columns]
    return wide.sort_index().reset_index()


def parse_elexon_demand(payload: dict) -> pd.DataFrame:
    frame = pd.DataFrame(_records(payload))
    date = _column(frame, ["settlementDate", "settlement_date"], "settlement date")
    period = _column(frame, ["settlementPeriod", "settlement_period"], "settlement period")
    value = _column(
        frame,
        ["nationalDemand", "initialDemandOutturn", "demand", "value"],
        "demand",
    )
    return pd.DataFrame(
        {
            "timestamp": _settlement_timestamp(frame[date], frame[period]),
            "demand_mw": pd.to_numeric(frame[value], errors="coerce"),
        }
    ).dropna().sort_values("timestamp")


def parse_neso_records(records: list[dict]) -> pd.DataFrame:
    """Return CKAN records while normalising common timestamp spellings."""
    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    for column in frame.columns:
        normalised = str(column).strip().lower().replace(" ", "_")
        if normalised != column and normalised not in frame:
            frame = frame.rename(columns={column: normalised})
    for candidate in (
        "timestamp",
        "datetime",
        "forecast_datetime",
        "settlement_date",
        "date",
    ):
        if candidate in frame:
            frame[candidate] = pd.to_datetime(frame[candidate], errors="coerce", utc=True)
    return frame


def parse_open_meteo_hourly(payload: dict, site: str) -> pd.DataFrame:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or "time" not in hourly:
        raise KeyError("Open-Meteo payload is missing hourly.time")
    frame = pd.DataFrame(hourly)
    frame["timestamp"] = pd.to_datetime(frame.pop("time"), errors="coerce", utc=True)
    frame = frame.set_index("timestamp").sort_index()
    frame.columns = [f"{site}_{column}" for column in frame.columns]
    return frame.reset_index()
