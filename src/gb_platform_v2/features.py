"""Feature engineering for half-hourly GB electricity models."""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_cyclical_time_features(df: pd.DataFrame, timestamp_col: str = "timestamp") -> pd.DataFrame:
    out = df.copy()
    ts = pd.to_datetime(out[timestamp_col], utc=True).dt.tz_convert("Europe/London")
    half_hour = ts.dt.hour * 2 + ts.dt.minute // 30
    day_of_year = ts.dt.dayofyear
    day_of_week = ts.dt.dayofweek
    out["hh_sin"] = np.sin(2 * np.pi * half_hour / 48.0)
    out["hh_cos"] = np.cos(2 * np.pi * half_hour / 48.0)
    out["dow_sin"] = np.sin(2 * np.pi * day_of_week / 7.0)
    out["dow_cos"] = np.cos(2 * np.pi * day_of_week / 7.0)
    out["year_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    out["year_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)
    out["is_weekend"] = (day_of_week >= 5).astype(int)
    out["month"] = ts.dt.month
    return out


def add_weather_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "temperature_c" in out:
        out["hdd"] = (15.5 - out["temperature_c"]).clip(lower=0)
        out["cdd"] = (out["temperature_c"] - 22.0).clip(lower=0)
    if "wind_speed_ms" in out:
        out["wind_speed_cubed"] = out["wind_speed_ms"].clip(lower=0) ** 3
    return out


def add_lag_features(
    df: pd.DataFrame,
    columns: list[str],
    lags: tuple[int, ...] = (1, 2, 48, 96, 336),
) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column not in out:
            continue
        for lag in lags:
            out[f"lag_{column}_{lag}"] = out[column].shift(lag)
    return out


def add_system_balance_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create physical balance layers without pretending every series is perfect."""
    out = df.copy()
    required = [
        "demand_mw",
        "embedded_wind_mw",
        "embedded_solar_mw",
        "transmission_wind_mw",
        "nuclear_mw",
        "net_import_mw",
        "battery_net_mw",
    ]
    missing = [column for column in required if column not in out]
    if missing:
        raise KeyError(f"Missing balance columns: {missing}")

    out["total_wind_mw"] = out["embedded_wind_mw"] + out["transmission_wind_mw"]
    out["renewable_mw"] = out["total_wind_mw"] + out["embedded_solar_mw"]
    out["residual_before_nuclear_mw"] = out["demand_mw"] - out["renewable_mw"]
    out["residual_after_nuclear_mw"] = out["residual_before_nuclear_mw"] - out["nuclear_mw"]
    out["net_system_short_mw"] = (
        out["residual_after_nuclear_mw"]
        - out["net_import_mw"]
        - out["battery_net_mw"]
    )
    if "curtailed_wind_mw" in out:
        out["wind_potential_mw"] = out["total_wind_mw"] + out["curtailed_wind_mw"]
    if "curtailed_solar_mw" in out:
        out["solar_potential_mw"] = out["embedded_solar_mw"] + out["curtailed_solar_mw"]
    if "nuclear_available_mw" in out:
        out["nuclear_modulation_mw"] = (
            out["nuclear_available_mw"] - out["nuclear_mw"]
        ).clip(lower=0)
    return out


def choose_numeric_features(df: pd.DataFrame, exclude: set[str] | None = None) -> list[str]:
    exclude = exclude or set()
    return [
        column
        for column in df.select_dtypes(include=["number", "bool"]).columns
        if column not in exclude
    ]
