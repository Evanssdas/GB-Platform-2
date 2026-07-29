"""Assemble the real half-hourly modelling table from parsed source files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from .point_in_time import select_latest_available


def _read(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    return pd.read_parquet(source) if source.suffix == ".parquet" else pd.read_csv(source)


def _timestamp(frame: pd.DataFrame, column: str = "timestamp") -> pd.DataFrame:
    if column not in frame:
        raise KeyError(f"Missing timestamp column {column}")
    out = frame.copy()
    out[column] = pd.to_datetime(out[column], utc=True, errors="coerce")
    return out.dropna(subset=[column]).sort_values(column)


def _required(mapping: dict, key: str) -> str:
    value = mapping.get(key)
    if not value or str(value).startswith("REQUIRED_"):
        raise ValueError(f"Set columns.{key} in config/data_mapping.yaml")
    return str(value)


def _issue_time_for_delivery(timestamp: pd.Series, hour: int, minute: int) -> pd.Series:
    local_delivery = pd.to_datetime(timestamp, utc=True).dt.tz_convert("Europe/London")
    issue_local = (
        local_delivery.dt.normalize()
        - pd.Timedelta(days=1)
        + pd.Timedelta(hours=hour, minutes=minute)
    )
    return issue_local.dt.tz_convert("UTC")


def build_half_hourly_dataset(
    mapping_path: str | Path,
    output_path: str | Path,
) -> pd.DataFrame:
    """Build a modelling table without silently substituting missing variables."""
    with Path(mapping_path).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    paths = config["paths"]
    columns = config["columns"]
    optional = config.get("optional_columns", {})

    price = _timestamp(_read(paths["elexon_price"]))
    demand = _timestamp(_read(paths["elexon_demand"]))
    fuel = _timestamp(_read(paths["elexon_fuel"]))

    base = price[["timestamp", _required(columns, "price_gbp_mwh")]].rename(
        columns={_required(columns, "price_gbp_mwh"): "price_gbp_mwh"}
    )
    base = base.merge(
        demand[["timestamp", _required(columns, "demand_mw")]].rename(
            columns={_required(columns, "demand_mw"): "demand_mw"}
        ),
        on="timestamp",
        how="inner",
    )
    fuel_columns = {
        _required(columns, "transmission_wind_mw"): "transmission_wind_mw",
        _required(columns, "nuclear_mw"): "nuclear_mw",
    }
    missing_fuel = [column for column in fuel_columns if column not in fuel]
    if missing_fuel:
        raise KeyError(f"Mapped FUELHH columns are absent: {missing_fuel}")
    base = base.merge(
        fuel[["timestamp", *fuel_columns]].rename(columns=fuel_columns),
        on="timestamp",
        how="inner",
    )

    embedded = _read(paths["neso_embedded"])
    embedded_timestamp = _required(columns, "embedded_timestamp")
    embedded_publish = _required(columns, "embedded_published_at")
    embedded = _timestamp(embedded, embedded_timestamp)
    embedded[embedded_publish] = pd.to_datetime(embedded[embedded_publish], utc=True, errors="coerce")
    embedded = embedded.rename(columns={embedded_timestamp: "timestamp"})

    issue_settings = config.get("issue_time", {})
    base["issue_time_utc"] = _issue_time_for_delivery(
        base["timestamp"],
        int(issue_settings.get("local_hour", 13)),
        int(issue_settings.get("local_minute", 0)),
    )

    selected_embedded: list[pd.DataFrame] = []
    for issue_time, group in base.groupby("issue_time_utc", sort=True):
        eligible = select_latest_available(
            embedded,
            issue_time,
            delivery_columns=["timestamp"],
            published_column=embedded_publish,
        )
        selected_embedded.append(eligible)
    embedded_asof = pd.concat(selected_embedded, ignore_index=True).drop_duplicates(
        "timestamp", keep="last"
    )
    embedded_columns = {
        _required(columns, "embedded_wind_mw"): "embedded_wind_mw",
        _required(columns, "embedded_solar_mw"): "embedded_solar_mw",
    }
    base = base.merge(
        embedded_asof[["timestamp", *embedded_columns]].rename(columns=embedded_columns),
        on="timestamp",
        how="left",
    )

    inertia = _read(paths["neso_inertia"])
    inertia_timestamp = _required(columns, "inertia_timestamp")
    inertia = _timestamp(inertia, inertia_timestamp).rename(columns={inertia_timestamp: "timestamp"})
    inertia_value = _required(columns, "inertia_gvas")
    base = base.merge(
        inertia[["timestamp", inertia_value]].rename(columns={inertia_value: "inertia_gvas"}),
        on="timestamp",
        how="left",
    )

    for weather_path in ("weather_demand", "weather_wind", "weather_solar"):
        weather = _timestamp(_read(paths[weather_path]))
        value_columns = [column for column in weather.columns if column != "timestamp"]
        base = base.merge(weather[["timestamp", *value_columns]], on="timestamp", how="left")

    for target in (
        "net_import_mw",
        "battery_net_mw",
        "curtailed_wind_mw",
        "curtailed_solar_mw",
        "nuclear_available_mw",
        "nuclear_outage_mw",
    ):
        source_column = optional.get(target)
        if source_column:
            found = None
            for candidate_path in paths.values():
                candidate = _read(candidate_path)
                if source_column in candidate and "timestamp" in candidate:
                    found = _timestamp(candidate)[["timestamp", source_column]].rename(
                        columns={source_column: target}
                    )
                    break
            if found is None:
                raise KeyError(f"Configured optional column {source_column} was not found")
            base = base.merge(found, on="timestamp", how="left")
        elif target in {"net_import_mw", "battery_net_mw"}:
            raise ValueError(
                f"{target} is a required model target. Configure its source column before training."
            )

    base = base.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    base["delivery_time_utc"] = base["timestamp"]
    required_targets = [
        "price_gbp_mwh",
        "demand_mw",
        "embedded_wind_mw",
        "embedded_solar_mw",
        "transmission_wind_mw",
        "nuclear_mw",
        "net_import_mw",
        "battery_net_mw",
        "inertia_gvas",
    ]
    missing_counts = base[required_targets].isna().sum()
    if missing_counts.any():
        raise ValueError(f"Required target gaps remain: {missing_counts[missing_counts.gt(0)].to_dict()}")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix == ".csv":
        base.to_csv(output, index=False)
    else:
        base.to_parquet(output, index=False)
    return base
