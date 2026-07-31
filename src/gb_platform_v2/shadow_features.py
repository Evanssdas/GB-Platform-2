"""Build leakage-safe feature tables for day-ahead shadow forecasts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from .collection import collect_elexon_core
from .data.clients import JsonClient
from .data.parsers import parse_open_meteo_hourly
from .features import add_cyclical_time_features, add_weather_features
from .timebase import LONDON_TZ, settlement_periods_for_day

LIVE_WEATHER_VARIABLES = [
    "temperature_2m",
    "wind_speed_100m",
    "shortwave_radiation",
    "cloud_cover",
]


def _utc(value: str | pd.Timestamp) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    return parsed.tz_localize("UTC") if parsed.tzinfo is None else parsed.tz_convert("UTC")


def _delivery_date(value: str | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(value).tz_localize(None).normalize()


def _forecast_weather_site(
    site: dict,
    delivery_date: pd.Timestamp,
) -> pd.DataFrame:
    client = JsonClient("https://api.open-meteo.com/v1", timeout=60, retries=4)
    payload = client.get(
        "forecast",
        {
            "latitude": float(site["latitude"]),
            "longitude": float(site["longitude"]),
            "hourly": ",".join(LIVE_WEATHER_VARIABLES),
            "start_date": delivery_date.strftime("%Y-%m-%d"),
            "end_date": delivery_date.strftime("%Y-%m-%d"),
            "timezone": "UTC",
        },
    )
    frame = parse_open_meteo_hourly(payload, str(site["name"]))
    rename = {
        f"{site['name']}_{variable}": f"{site['name']}_{variable}_previous_day1"
        for variable in LIVE_WEATHER_VARIABLES
    }
    return frame.rename(columns=rename)


def _weather_group(
    sites: list[dict],
    group: str,
    periods_utc: pd.DatetimeIndex,
    delivery_date: pd.Timestamp,
) -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    for site in sites:
        frame = _forecast_weather_site(site, delivery_date)
        merged = frame if merged is None else merged.merge(
            frame, on="timestamp", how="outer", validate="one_to_one"
        )
    if merged is None or merged.empty:
        raise ValueError(f"No live weather was collected for group {group}")
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True)
    merged = merged.set_index("timestamp").sort_index()

    # A forecast day is hourly. Interpolate in UTC onto the exact GB settlement
    # clock, including 46/50-period DST days. Add a right boundary only when the
    # API omitted the next midnight.
    right_boundary = periods_utc.max() + pd.Timedelta(minutes=30)
    if right_boundary not in merged.index:
        tail = merged.tail(1).copy()
        tail.index = pd.DatetimeIndex([right_boundary])
        merged = pd.concat([merged, tail])
    union = merged.index.union(periods_utc).sort_values()
    half_hourly = merged.reindex(union).interpolate(method="time").reindex(periods_utc)
    if half_hourly.isna().any().any():
        missing = half_hourly.columns[half_hourly.isna().any()].tolist()
        raise ValueError(f"Live weather contains gaps for {group}: {missing}")
    half_hourly = half_hourly.rename(
        columns={column: f"weather_{group}_{column}" for column in half_hourly.columns}
    )
    return half_hourly


def _collect_d7_fallbacks(
    delivery_date: pd.Timestamp,
    periods_utc: pd.DatetimeIndex,
    output_dir: Path,
) -> pd.DataFrame:
    source_day = delivery_date - pd.Timedelta(days=7)
    source_end = source_day + pd.Timedelta(days=1)
    collect_elexon_core(
        source_day.strftime("%Y-%m-%d"),
        source_end.strftime("%Y-%m-%d"),
        output_dir,
        chunk_days=1,
    )
    demand = pd.read_parquet(output_dir / "elexon_demand.parquet")
    fuel = pd.read_parquet(output_dir / "elexon_fuelhh.parquet")
    demand["timestamp"] = pd.to_datetime(demand["timestamp"], utc=True)
    fuel["timestamp"] = pd.to_datetime(fuel["timestamp"], utc=True)
    demand = demand.set_index("timestamp").sort_index()
    fuel = fuel.set_index("timestamp").sort_index()

    source_timestamps = periods_utc - pd.Timedelta(days=7)
    fallback = pd.DataFrame(index=periods_utc)
    fallback["fallback_d7_demand_mw"] = demand["demand_mw"].reindex(
        source_timestamps
    ).to_numpy()
    nuclear_column = "fuel_nuclear_mw"
    if nuclear_column not in fuel:
        raise KeyError(f"Elexon FUELHH is missing {nuclear_column}")
    fallback["fallback_d7_nuclear_mw"] = fuel[nuclear_column].reindex(
        source_timestamps
    ).to_numpy()
    if fallback.isna().any().any():
        raise ValueError("D-7 fallback profile is incomplete")
    return fallback


def build_shadow_features(
    delivery_date: str,
    issue_time_utc: str,
    config_path: str | Path,
    model_dir: str | Path,
    output_path: str | Path,
    recent_dir: str | Path,
    summary_path: str | Path | None = None,
) -> dict:
    delivery = _delivery_date(delivery_date)
    issue = _utc(issue_time_utc)
    local_start = delivery.tz_localize(LONDON_TZ)
    if issue >= local_start.tz_convert("UTC"):
        raise ValueError("Shadow forecast issue time must be before the delivery day")
    if issue < (local_start - pd.Timedelta(days=2)).tz_convert("UTC"):
        raise ValueError("Shadow forecast issue time is implausibly early")

    metadata = json.loads((Path(model_dir) / "metadata.json").read_text(encoding="utf-8"))
    if not metadata.get("operational_bundle_ready"):
        raise ValueError("Model bundle has not passed operational bundle preparation")
    settings = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    periods_local = settlement_periods_for_day(delivery)
    periods_utc = periods_local.tz_convert("UTC")

    frame = pd.DataFrame(index=periods_utc)
    frame["timestamp"] = periods_utc
    for group in ("demand", "wind", "solar"):
        weather = _weather_group(
            settings["weather_sites"][group], group, periods_utc, delivery
        )
        frame = frame.join(weather, how="left")

    strategy = metadata["operational_component_strategy"]
    fallback_targets = {
        target for target, rule in strategy.items() if rule.get("source") == "fallback_d7"
    }
    if fallback_targets:
        fallback = _collect_d7_fallbacks(delivery, periods_utc, Path(recent_dir))
        frame = frame.join(fallback, how="left")

    frame = add_cyclical_time_features(frame.reset_index(drop=True))
    frame = add_weather_features(frame)
    frame["issue_time_utc"] = issue
    frame["delivery_date"] = delivery.date()
    frame["model_profile"] = metadata.get("model_profile")

    required_features = list(metadata.get("features", []))
    missing = [column for column in required_features if column not in frame]
    if missing:
        raise KeyError(f"Live feature table is missing trained features: {missing}")
    nulls = frame[required_features].isna().sum()
    nulls = {column: int(value) for column, value in nulls.items() if value}
    if nulls:
        raise ValueError(f"Live trained features contain nulls: {nulls}")
    for target in fallback_targets:
        column = f"fallback_d7_{target}"
        if column not in frame or frame[column].isna().any():
            raise ValueError(f"Operational fallback column is incomplete: {column}")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False)
    summary = {
        "workflow_revision": "shadow-features-v1",
        "delivery_date_local": delivery.strftime("%Y-%m-%d"),
        "issue_time_utc": issue.isoformat(),
        "period_count": int(len(frame)),
        "expected_period_count": int(len(periods_utc)),
        "timestamp_min": periods_utc.min().isoformat(),
        "timestamp_max": periods_utc.max().isoformat(),
        "trained_feature_count": len(required_features),
        "fallback_targets": sorted(fallback_targets),
        "weather_source": "Open-Meteo current forecast retrieved at workflow runtime",
        "fallback_source": "Elexon observed profile at exact UTC timestamp minus 168 hours",
        "leakage_gate": "passed",
    }
    summary_file = Path(summary_path) if summary_path else output.with_suffix(".json")
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build tomorrow's leakage-safe shadow features")
    parser.add_argument("--delivery-date", required=True)
    parser.add_argument("--issue-time-utc", required=True)
    parser.add_argument("--config", default="config/example.yaml")
    parser.add_argument("--models", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--recent-dir", default="data/parsed/shadow_recent")
    parser.add_argument("--summary")
    args = parser.parse_args()
    result = build_shadow_features(
        args.delivery_date,
        args.issue_time_utc,
        args.config,
        args.models,
        args.output,
        args.recent_dir,
        args.summary,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
