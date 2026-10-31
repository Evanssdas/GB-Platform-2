"""Exact issue-time weather vintages from Open-Meteo Single Runs.

The paper workflow uses the ECMWF IFS HRES 00 UTC run from D-1. That run is
comfortably available before the configured GB D-1 13:00 local forecast issue
and can be reproduced historically from the Single Runs archive.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import requests
import yaml

from .data.parsers import parse_open_meteo_hourly
from .timebase import LONDON_TZ, settlement_periods_for_day

WEATHER_VARIABLES = [
    "temperature_2m",
    "wind_speed_100m",
    "shortwave_radiation",
    "cloud_cover",
]
SINGLE_RUN_URL = "https://single-runs-api.open-meteo.com/v1/forecast"
WEATHER_MODEL = "ecmwf_ifs"


def _delivery_days(start: str, end: str) -> list[pd.Timestamp]:
    first = pd.Timestamp(start).normalize()
    final = pd.Timestamp(end).normalize()
    if final <= first:
        raise ValueError("end must be later than start")
    return list(pd.date_range(first, final, freq="D", inclusive="left"))


def _payloads_for_sites(
    sites: list[dict],
    run_utc: pd.Timestamp,
    session: requests.Session,
) -> list[dict]:
    params = {
        "latitude": ",".join(str(float(site["latitude"])) for site in sites),
        "longitude": ",".join(str(float(site["longitude"])) for site in sites),
        "hourly": ",".join(WEATHER_VARIABLES),
        "run": run_utc.strftime("%Y-%m-%dT%H:%M"),
        "forecast_days": 3,
        "timezone": "UTC",
        "models": WEATHER_MODEL,
    }
    response = session.get(SINGLE_RUN_URL, params=params, timeout=90)
    response.raise_for_status()
    payload = response.json()
    payloads = payload if isinstance(payload, list) else [payload]
    if len(payloads) != len(sites):
        raise ValueError(
            f"Single Runs returned {len(payloads)} locations for {len(sites)} sites"
        )
    return payloads



def exact_issue_weather_day(
    sites: list[dict],
    delivery: str | pd.Timestamp,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Return the exact D-1 00 UTC ECMWF run for one GB delivery day."""
    day = pd.Timestamp(delivery).tz_localize(None).normalize()
    client = session or requests.Session()
    client.headers.update({"User-Agent": "GB-Power-Market-Platform-V2/0.2"})
    run_utc = (day - pd.Timedelta(days=1)).tz_localize("UTC")
    periods = settlement_periods_for_day(day).tz_convert("UTC")
    left = periods.min()
    right = periods.max() + pd.Timedelta(minutes=30)
    payloads = _payloads_for_sites(sites, run_utc, client)

    merged: pd.DataFrame | None = None
    for site, payload in zip(sites, payloads):
        frame = parse_open_meteo_hourly(payload, str(site["name"]))
        rename = {
            f"{site['name']}_{variable}": f"{site['name']}_{variable}_previous_day1"
            for variable in WEATHER_VARIABLES
        }
        frame = frame.rename(columns=rename)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.loc[
            frame["timestamp"].between(left, right, inclusive="both")
        ].copy()
        merged = (
            frame
            if merged is None
            else merged.merge(frame, on="timestamp", how="outer", validate="one_to_one")
        )
    if merged is None or merged.empty:
        raise ValueError(f"No exact-run weather for delivery date {day.date()}")
    merged["weather_run_utc"] = run_utc
    merged["weather_model"] = WEATHER_MODEL
    return merged.sort_values("timestamp").drop_duplicates("timestamp", keep="last")

def collect_exact_issue_weather(
    sites: list[dict],
    start: str,
    end: str,
    output: str | Path,
) -> Path:
    """Collect one reproducible D-1 00 UTC ECMWF IFS HRES run per delivery day."""
    session = requests.Session()
    session.headers.update({"User-Agent": "GB-Power-Market-Platform-V2/0.2"})
    daily_frames: list[pd.DataFrame] = []

    for delivery in _delivery_days(start, end):
        daily_frames.append(exact_issue_weather_day(sites, delivery, session))

    combined = (
        pd.concat(daily_frames, ignore_index=True)
        .sort_values("timestamp")
        .drop_duplicates("timestamp", keep="last")
    )
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(target, index=False)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect exact D-1 ECMWF weather runs")
    parser.add_argument("--config", default="config/example.yaml")
    parser.add_argument("--group", choices=["demand", "wind", "solar"], required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    settings = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    path = collect_exact_issue_weather(
        settings["weather_sites"][args.group],
        args.start,
        args.end,
        args.output,
    )
    print({
        "output": str(path),
        "model": WEATHER_MODEL,
        "run_rule": "D-1 00:00 UTC ECMWF IFS HRES",
        "issue_time_compatibility": "available before D-1 13:00 Europe/London",
    })


if __name__ == "__main__":
    main()
