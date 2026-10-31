"""Exact issue-time weather vintages from Open-Meteo Single Runs.

The paper workflow uses the ECMWF IFS HRES 00 UTC run from D-1. That run is
comfortably available before the configured GB D-1 13:00 local forecast issue
and can be reproduced historically from the Single Runs archive.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .data.parsers import parse_open_meteo_hourly
from .timebase import LONDON_TZ, settlement_periods_for_day

WEATHER_VARIABLES = [
    "temperature_2m",
    "wind_speed_100m",
    "shortwave_radiation",
    "cloud_cover",
]
SINGLE_RUN_URL = "https://single-runs-api.open-meteo.com/v1/forecast"
PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
WEATHER_MODEL = "ecmwf_ifs"


class ExactRunUnavailable(RuntimeError):
    """Raised when Open-Meteo does not expose the requested archived run."""


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
    last_error: Exception | None = None
    payload = None
    for attempt in range(6):
        try:
            response = session.get(SINGLE_RUN_URL, params=params, timeout=(30, 180))
            response.raise_for_status()
            payload = response.json()
            break
        except requests.HTTPError as exc:
            last_error = exc
            status = getattr(exc.response, "status_code", None)
            # A 400 from Single Runs generally means that exact archived model
            # initialisation is not available. Retrying the same request cannot
            # repair that, so fall back explicitly to fixed-lead Previous Runs.
            if status == 400:
                raise ExactRunUnavailable(str(exc)) from exc
            if attempt == 5:
                raise
            time.sleep(min(30.0, 2.0 ** attempt))
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt == 5:
                raise
            time.sleep(min(30.0, 2.0 ** attempt))
    if payload is None:
        raise RuntimeError("Open-Meteo Single Runs returned no JSON payload") from last_error
    payloads = payload if isinstance(payload, list) else [payload]
    if len(payloads) != len(sites):
        raise ValueError(
            f"Single Runs returned {len(payloads)} locations for {len(sites)} sites"
        )
    return payloads




def _previous_day1_weather_day(
    sites: list[dict],
    delivery: str | pd.Timestamp,
    session: requests.Session,
) -> pd.DataFrame:
    """Return fixed 24-hour-lead ECMWF weather when an exact run is unavailable."""
    day = pd.Timestamp(delivery).tz_localize(None).normalize()
    periods = settlement_periods_for_day(day).tz_convert("UTC")
    left = periods.min()
    right = periods.max() + pd.Timedelta(minutes=30)
    api_start = left.floor("D").strftime("%Y-%m-%d")
    api_end = right.floor("D").strftime("%Y-%m-%d")
    variables = [f"{variable}_previous_day1" for variable in WEATHER_VARIABLES]
    params = {
        "latitude": ",".join(str(float(site["latitude"])) for site in sites),
        "longitude": ",".join(str(float(site["longitude"])) for site in sites),
        "hourly": ",".join(variables),
        "start_date": api_start,
        "end_date": api_end,
        "timezone": "UTC",
        "models": WEATHER_MODEL,
    }
    response = session.get(PREVIOUS_RUNS_URL, params=params, timeout=(30, 180))
    response.raise_for_status()
    payload = response.json()
    payloads = payload if isinstance(payload, list) else [payload]
    if len(payloads) != len(sites):
        raise ValueError(
            f"Previous Runs returned {len(payloads)} locations for {len(sites)} sites"
        )
    merged: pd.DataFrame | None = None
    for site, site_payload in zip(sites, payloads):
        frame = parse_open_meteo_hourly(site_payload, str(site["name"]))
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
        raise ValueError(f"No Previous Runs weather for delivery date {day.date()}")
    merged["weather_run_utc"] = pd.NaT
    merged["weather_model"] = WEATHER_MODEL
    merged["weather_vintage_source"] = "previous_runs_fixed_lead_day1"
    return merged.sort_values("timestamp").drop_duplicates("timestamp", keep="last")


def exact_issue_weather_day(
    sites: list[dict],
    delivery: str | pd.Timestamp,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Return the exact D-1 00 UTC ECMWF run for one GB delivery day."""
    day = pd.Timestamp(delivery).tz_localize(None).normalize()
    if session is None:
        retry = Retry(
            total=6,
            connect=6,
            read=6,
            status=6,
            backoff_factor=2.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        client = requests.Session()
        client.mount("https://", HTTPAdapter(max_retries=retry))
    else:
        client = session
    client.headers.update({"User-Agent": "GB-Power-Market-Platform-V2/0.2"})
    run_utc = (day - pd.Timedelta(days=1)).tz_localize("UTC")
    periods = settlement_periods_for_day(day).tz_convert("UTC")
    left = periods.min()
    right = periods.max() + pd.Timedelta(minutes=30)
    try:
        payloads = _payloads_for_sites(sites, run_utc, client)
    except ExactRunUnavailable:
        return _previous_day1_weather_day(sites, day, client)

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
    merged["weather_vintage_source"] = "single_run_d1_00utc"
    return merged.sort_values("timestamp").drop_duplicates("timestamp", keep="last")

def collect_exact_issue_weather(
    sites: list[dict],
    start: str,
    end: str,
    output: str | Path,
) -> Path:
    """Collect one reproducible D-1 00 UTC ECMWF IFS HRES run per delivery day."""
    retry = Retry(
        total=6,
        connect=6,
        read=6,
        status=6,
        backoff_factor=2.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
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
    source_counts = (
        combined[["timestamp", "weather_vintage_source"]]
        .drop_duplicates("timestamp")["weather_vintage_source"]
        .value_counts()
        .to_dict()
    )
    metadata = {
        "requested_rule": "D-1 00:00 UTC ECMWF IFS HRES Single Run",
        "fallback_rule": "ECMWF IFS fixed 24-hour lead Previous Runs (_previous_day1)",
        "source_row_counts": {str(key): int(value) for key, value in source_counts.items()},
        "training_live_equivalence": (
            "Exact Single Runs preserve model initialisation where archived; fixed-lead "
            "Previous Runs are used only when the exact archived run is unavailable."
        ),
    }
    target.with_suffix(".vintage.json").write_text(
        __import__("json").dumps(metadata, indent=2), encoding="utf-8"
    )
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
        "run_rule": "D-1 00:00 UTC ECMWF IFS HRES where archived",
        "fallback_rule": "fixed 24-hour lead Previous Runs where exact run unavailable",
        "issue_time_compatibility": "both sources represent information available before D-1 13:00 Europe/London",
    })


if __name__ == "__main__":
    main()
