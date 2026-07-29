"""Source-specific parsing and schema validation.

The functions fail loudly when required fields are absent. Alias lists are used
only for known naming variations; silent positional parsing is deliberately
avoided.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from ..timebase import settlement_periods_for_day


def _records(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise TypeError("Expected a JSON object or array")
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
    """Map local GB settlement date and period to UTC, including 46/50-period days."""
    dates = pd.to_datetime(date, errors="coerce")
    periods = pd.to_numeric(period, errors="coerce")
    cache: dict[pd.Timestamp, pd.DatetimeIndex] = {}
    values: list[pd.Timestamp] = []
    for day, settlement_period in zip(dates, periods):
        if pd.isna(day) or pd.isna(settlement_period):
            values.append(pd.NaT)
            continue
        normalised = pd.Timestamp(day).normalize()
        if normalised not in cache:
            cache[normalised] = settlement_periods_for_day(normalised)
        index = cache[normalised]
        position = int(settlement_period) - 1
        if position < 0 or position >= len(index):
            values.append(pd.NaT)
        else:
            values.append(index[position].tz_convert("UTC"))
    return pd.Series(pd.DatetimeIndex(values), index=date.index)


def _timestamp_from_source_or_period(
    frame: pd.DataFrame,
    date_column: str,
    period_column: str,
) -> pd.Series:
    for candidate in ("startTime", "start_time", "timeFrom", "time_from"):
        if candidate in frame:
            parsed = pd.to_datetime(frame[candidate], utc=True, errors="coerce")
            if parsed.notna().any():
                return parsed
    return _settlement_timestamp(frame[date_column], frame[period_column])


def parse_elexon_mid(payload: Any) -> pd.DataFrame:
    frame = pd.DataFrame(_records(payload))
    date = _column(frame, ["settlementDate", "settlement_date"], "settlement date")
    period = _column(frame, ["settlementPeriod", "settlement_period"], "settlement period")
    price = _column(frame, ["price", "marketIndexPrice", "market_index_price"], "price")
    provider = _column(frame, ["dataProvider", "data_provider"], "data provider")
    volume = _column(frame, ["volume", "marketIndexVolume", "market_index_volume"], "volume")

    out = pd.DataFrame(
        {
            "timestamp": _timestamp_from_source_or_period(frame, date, period),
            "settlement_date": pd.to_datetime(frame[date]).dt.date,
            "settlement_period": pd.to_numeric(frame[period], errors="coerce"),
            "data_provider": frame[provider].astype(str),
            "price_gbp_mwh": pd.to_numeric(frame[price], errors="coerce"),
            "market_index_volume_mwh": pd.to_numeric(frame[volume], errors="coerce"),
        }
    )
    out = out.loc[out["data_provider"].eq("APXMIDP")]
    return out.dropna(subset=["timestamp", "price_gbp_mwh"]).sort_values("timestamp")


def parse_elexon_fuelhh(payload: Any) -> pd.DataFrame:
    frame = pd.DataFrame(_records(payload))
    date = _column(frame, ["settlementDate", "settlement_date"], "settlement date")
    period = _column(frame, ["settlementPeriod", "settlement_period"], "settlement period")
    fuel = _column(frame, ["fuelType", "fuel_type"], "fuel type")
    value = _column(frame, ["generation", "quantity", "value"], "generation")
    frame["timestamp"] = _timestamp_from_source_or_period(frame, date, period)
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


def parse_elexon_demand(payload: Any) -> pd.DataFrame:
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
            "timestamp": _timestamp_from_source_or_period(frame, date, period),
            "demand_mw": pd.to_numeric(frame[value], errors="coerce"),
        }
    ).dropna().sort_values("timestamp")


def parse_elexon_interconnectors(payload: Any) -> pd.DataFrame:
    frame = pd.DataFrame(_records(payload))
    date = _column(frame, ["settlementDate", "settlement_date"], "settlement date")
    period = _column(frame, ["settlementPeriod", "settlement_period"], "settlement period")
    name = _column(frame, ["interconnectorName", "interconnector_name"], "interconnector")
    value = _column(frame, ["generation", "value"], "interconnector generation")
    frame["timestamp"] = _timestamp_from_source_or_period(frame, date, period)
    frame["interconnector"] = frame[name].astype(str).str.lower()
    frame["flow_mw"] = pd.to_numeric(frame[value], errors="coerce")
    wide = frame.pivot_table(
        index="timestamp",
        columns="interconnector",
        values="flow_mw",
        aggfunc="sum",
    )
    wide.columns = [f"interconnector_{column}_mw" for column in wide.columns]
    wide["net_import_mw"] = wide.sum(axis=1, min_count=1)
    return wide.sort_index().reset_index()


def parse_neso_records(records: list[dict]) -> pd.DataFrame:
    """Return CKAN records while normalising common timestamp spellings."""
    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    rename: dict[str, str] = {}
    for column in frame.columns:
        normalised = str(column).strip().lower().replace(" ", "_")
        if normalised != column and normalised not in frame:
            rename[str(column)] = normalised
    frame = frame.rename(columns=rename)
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
