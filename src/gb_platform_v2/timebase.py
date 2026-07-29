"""DST-safe GB settlement-period utilities."""

from __future__ import annotations

import pandas as pd

LONDON_TZ = "Europe/London"


def settlement_periods_for_day(day: str | pd.Timestamp) -> pd.DatetimeIndex:
    """Return all 30-minute period starts for a GB local delivery day.

    The returned index is timezone-aware. It naturally contains 46, 48 or 50
    periods on daylight-saving transition days.
    """
    local_day = pd.Timestamp(day).tz_localize(None).normalize()
    start = local_day.tz_localize(LONDON_TZ)
    end = (local_day + pd.Timedelta(days=1)).tz_localize(LONDON_TZ)
    return pd.date_range(start, end, freq="30min", inclusive="left")


def add_settlement_columns(df: pd.DataFrame, timestamp_col: str = "timestamp") -> pd.DataFrame:
    """Add local delivery date, settlement period and UTC timestamp columns."""
    out = df.copy()
    ts = pd.to_datetime(out[timestamp_col], utc=True, errors="raise")
    local = ts.dt.tz_convert(LONDON_TZ)
    midnight = local.dt.normalize()
    elapsed_minutes = (local - midnight).dt.total_seconds() / 60.0
    out["timestamp_utc"] = ts
    out["timestamp_local"] = local
    out["delivery_date"] = local.dt.date
    out["settlement_period"] = (elapsed_minutes // 30).astype(int) + 1
    return out


def validate_half_hourly_index(index: pd.DatetimeIndex) -> None:
    """Raise when an index is not unique, ordered and 30-minute spaced in UTC."""
    if index.tz is None:
        raise ValueError("Index must be timezone-aware")
    if not index.is_monotonic_increasing:
        raise ValueError("Index must be sorted")
    if index.has_duplicates:
        raise ValueError("Index contains duplicates")
    if len(index) > 1:
        gaps = index.tz_convert("UTC").to_series().diff().dropna()
        if not gaps.eq(pd.Timedelta(minutes=30)).all():
            raise ValueError("Index is not continuous at 30-minute resolution")
