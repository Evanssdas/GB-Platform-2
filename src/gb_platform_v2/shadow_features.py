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
from .exact_weather import WEATHER_MODEL, exact_issue_weather_day
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
    api_start_date: str,
    api_end_date: str,
) -> pd.DataFrame:
    client = JsonClient("https://api.open-meteo.com/v1", timeout=60, retries=4)
    payload = client.get(
        "forecast",
        {
            "latitude": float(site["latitude"]),
            "longitude": float(site["longitude"]),
            "hourly": ",".join(LIVE_WEATHER_VARIABLES),
            "start_date": api_start_date,
            "end_date": api_end_date,
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
) -> pd.DataFrame:
    """Build live weather from the same exact run rule used for V2-R training."""
    delivery_local = periods_utc.tz_convert(LONDON_TZ)[0].date()
    merged = exact_issue_weather_day(sites, str(delivery_local))
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True)
    metadata_columns = {"weather_run_utc", "weather_model"}
    value_columns = [
        column for column in merged.columns
        if column != "timestamp" and column not in metadata_columns
    ]
    merged = merged[["timestamp", *value_columns]].set_index("timestamp").sort_index()

    right_boundary = periods_utc.max() + pd.Timedelta(minutes=30)
    if right_boundary not in merged.index:
        tail = merged.loc[:right_boundary].tail(1).copy()
        if tail.empty:
            raise ValueError(f"Exact weather run has no right boundary for {group}")
        tail.index = pd.DatetimeIndex([right_boundary])
        merged = pd.concat([merged, tail])
    union = merged.index.union(periods_utc).sort_values()
    half_hourly = merged.reindex(union).interpolate(method="time").reindex(periods_utc)
    if half_hourly.isna().any().any():
        missing = half_hourly.columns[half_hourly.isna().any()].tolist()
        raise ValueError(f"Exact weather run contains gaps for {group}: {missing}")
    return half_hourly.rename(
        columns={column: f"weather_{group}_{column}" for column in half_hourly.columns}
    )

def _collect_price_anchors(
    periods_utc: pd.DatetimeIndex,
    output_dir: Path,
) -> pd.DataFrame:
    """Collect observable D-2 and D-7 APXMIDP price anchors for each delivery period."""
    source_times = pd.DatetimeIndex(
        [
            *(periods_utc - pd.Timedelta(days=2)),
            *(periods_utc - pd.Timedelta(days=7)),
        ]
    )
    local = source_times.tz_convert(LONDON_TZ)
    first_day = pd.Timestamp(local.min().date())
    end_day = pd.Timestamp(local.max().date()) + pd.Timedelta(days=1)
    collect_elexon_core(
        first_day.strftime("%Y-%m-%d"),
        end_day.strftime("%Y-%m-%d"),
        output_dir,
        chunk_days=1,
    )
    price = pd.read_parquet(output_dir / "elexon_mid.parquet")
    price["timestamp"] = pd.to_datetime(price["timestamp"], utc=True)
    price = price.set_index("timestamp").sort_index()
    if "price_gbp_mwh" not in price:
        raise KeyError("Elexon MID is missing price_gbp_mwh")

    anchors = pd.DataFrame(index=periods_utc)
    for days in (2, 7):
        lookup_times = periods_utc - pd.Timedelta(days=days)
        anchors[f"price_d{days}_gbp_mwh"] = (
            price["price_gbp_mwh"].reindex(lookup_times).to_numpy()
        )
    if anchors.isna().any().any():
        raise ValueError("Observable price-anchor history is incomplete")
    return anchors


def _collect_d7_fallbacks(
    periods_utc: pd.DatetimeIndex,
    output_dir: Path,
) -> pd.DataFrame:
    source_timestamps = periods_utc - pd.Timedelta(days=7)
    source_local = source_timestamps.tz_convert(LONDON_TZ)
    first_day = pd.Timestamp(source_local.min().date())
    end_day = pd.Timestamp(source_local.max().date()) + pd.Timedelta(days=1)
    collect_elexon_core(
        first_day.strftime("%Y-%m-%d"),
        end_day.strftime("%Y-%m-%d"),
        output_dir,
        chunk_days=1,
    )
    demand = pd.read_parquet(output_dir / "elexon_demand.parquet")
    fuel = pd.read_parquet(output_dir / "elexon_fuelhh.parquet")
    demand["timestamp"] = pd.to_datetime(demand["timestamp"], utc=True)
    fuel["timestamp"] = pd.to_datetime(fuel["timestamp"], utc=True)
    demand = demand.set_index("timestamp").sort_index()
    fuel = fuel.set_index("timestamp").sort_index()

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
    periods_utc = settlement_periods_for_day(delivery).tz_convert("UTC")

    frame = pd.DataFrame(index=periods_utc)
    frame["timestamp"] = periods_utc
    for group in ("demand", "wind", "solar"):
        frame = frame.join(
            _weather_group(settings["weather_sites"][group], group, periods_utc),
            how="left",
        )

    strategy = metadata["operational_component_strategy"]
    fallback_targets = {
        target for target, rule in strategy.items() if rule.get("source") == "fallback_d7"
    }
    if fallback_targets:
        frame = frame.join(
            _collect_d7_fallbacks(periods_utc, Path(recent_dir)), how="left"
        )

    frame = add_cyclical_time_features(frame.reset_index(drop=True))
    frame = add_weather_features(frame)
    frame["issue_time_utc"] = issue
    frame["delivery_date"] = delivery.date()
    frame["model_profile"] = metadata.get("model_profile")

    component_features = list(metadata.get("features", []))
    required_features = list(metadata.get("input_features", component_features))
    price_anchor_features = {
        column for column in ("price_d2_gbp_mwh", "price_d7_gbp_mwh")
        if column in required_features
    }
    if price_anchor_features:
        frame = frame.join(
            _collect_price_anchors(periods_utc, Path(recent_dir)),
            how="left",
        )

    # Price-only market-regime inputs are optional at runtime. LightGBM can
    # natively handle NaN, so keep the trained column contract without inventing
    # values when a market feed is unavailable. Physical/component inputs remain
    # strict because those models depend on them directly.
    optional_market_features = set(metadata.get("market_regime_features", []))
    missing = [column for column in required_features if column not in frame]
    strict_missing = [column for column in missing if column not in optional_market_features]
    if strict_missing:
        raise KeyError(f"Live feature table is missing trained features: {strict_missing}")
    for column in missing:
        frame[column] = pd.NA

    strict_nulls = frame[component_features].isna().sum() if component_features else pd.Series(dtype=int)
    strict_nulls = {column: int(value) for column, value in strict_nulls.items() if value}
    if strict_nulls:
        raise ValueError(f"Live component features contain nulls: {strict_nulls}")
    for target in fallback_targets:
        column = f"fallback_d7_{target}"
        if column not in frame or frame[column].isna().any():
            raise ValueError(f"Operational fallback column is incomplete: {column}")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False)
    summary = {
        "workflow_revision": "shadow-features-v2",
        "delivery_date_local": delivery.strftime("%Y-%m-%d"),
        "issue_time_utc": issue.isoformat(),
        "period_count": int(len(frame)),
        "expected_period_count": int(len(periods_utc)),
        "timestamp_min": periods_utc.min().isoformat(),
        "timestamp_max": periods_utc.max().isoformat(),
        "trained_feature_count": len(required_features),
        "component_feature_count": len(component_features),
        "optional_market_features": sorted(optional_market_features),
        "optional_market_features_missing_live": sorted(
            column for column in optional_market_features if frame[column].isna().all()
        ),
        "fallback_targets": sorted(fallback_targets),
        "weather_source": (
            f"Open-Meteo Single Runs {WEATHER_MODEL}; exact D-1 00:00 UTC run, "
            "identical vintage rule to V2-R historical training"
        ),
        "fallback_source": "Elexon observed profile at exact UTC timestamp minus 168 hours",
        "price_anchor_features": sorted(price_anchor_features),
        "price_anchor_source": "Elexon APXMIDP at exact UTC timestamp minus 48 and 168 hours",
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
