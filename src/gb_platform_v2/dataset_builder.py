"""Assemble the real half-hourly modelling table from parsed source files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from .point_in_time import select_latest_available


FULL_COMPONENT_TARGETS = [
    "demand_mw",
    "embedded_wind_mw",
    "embedded_solar_mw",
    "transmission_wind_mw",
    "nuclear_mw",
    "net_import_mw",
    "battery_net_mw",
    "inertia_gvas",
]


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
        raise ValueError(f"Set columns.{key} in the data mapping")
    return str(value)


def _issue_time_for_delivery(timestamp: pd.Series, hour: int, minute: int) -> pd.Series:
    local_delivery = pd.to_datetime(timestamp, utc=True).dt.tz_convert("Europe/London")
    issue_local = (
        local_delivery.dt.normalize()
        - pd.Timedelta(days=1)
        + pd.Timedelta(hours=hour, minutes=minute)
    )
    return issue_local.dt.tz_convert("UTC")


def _align_weather(weather: pd.DataFrame, target_timestamps: pd.Series) -> pd.DataFrame:
    """Interpolate hourly weather onto the 30-minute settlement clock."""
    values = _timestamp(weather).set_index("timestamp").sort_index()
    numeric = values.select_dtypes(include="number")
    target_index = pd.DatetimeIndex(pd.to_datetime(target_timestamps, utc=True)).sort_values()
    union = numeric.index.union(target_index).sort_values()
    aligned = numeric.reindex(union).interpolate(method="time").reindex(target_index)
    aligned.index.name = "timestamp"
    return aligned.reset_index()


def _component_profile(config: dict) -> list[str]:
    configured = config.get("required_components", FULL_COMPONENT_TARGETS)
    if not isinstance(configured, list) or not configured:
        raise ValueError("required_components must be a non-empty list")
    unknown = sorted(set(configured) - set(FULL_COMPONENT_TARGETS))
    if unknown:
        raise ValueError(f"Unknown required components: {unknown}")
    required = [str(column) for column in configured]
    minimum = {
        "demand_mw",
        "embedded_wind_mw",
        "embedded_solar_mw",
        "transmission_wind_mw",
        "nuclear_mw",
        "net_import_mw",
        "inertia_gvas",
    }
    missing_minimum = sorted(minimum - set(required))
    if missing_minimum:
        raise ValueError(
            "The supported core profile still requires these components: "
            f"{missing_minimum}"
        )
    return required


def build_half_hourly_dataset(
    mapping_path: str | Path,
    output_path: str | Path,
) -> pd.DataFrame:
    """Build a modelling table without silently substituting missing variables.

    ``required_components`` in the mapping explicitly selects the modelling
    profile. The full profile includes battery output. The supported core
    profile omits battery output and records that omission in the output rather
    than filling an unavailable measured series with zero.
    """
    with Path(mapping_path).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    paths = config["paths"]
    columns = config["columns"]
    optional = config.get("optional_columns", {})
    required_components = _component_profile(config)

    loaded = {name: _read(path) for name, path in paths.items()}
    price = _timestamp(loaded["elexon_price"])
    demand = _timestamp(loaded["elexon_demand"])
    fuel = _timestamp(loaded["elexon_fuel"])

    price_column = _required(columns, "price_gbp_mwh")
    demand_column = _required(columns, "demand_mw")
    base = price[["timestamp", price_column]].rename(columns={price_column: "price_gbp_mwh"})
    base = base.merge(
        demand[["timestamp", demand_column]].rename(columns={demand_column: "demand_mw"}),
        on="timestamp",
        how="inner",
        validate="one_to_one",
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
        validate="one_to_one",
    )

    embedded = loaded["neso_embedded"].copy()
    embedded_timestamp = _required(columns, "embedded_timestamp")
    embedded_publish = _required(columns, "embedded_published_at")
    embedded = _timestamp(embedded, embedded_timestamp)
    embedded[embedded_publish] = pd.to_datetime(
        embedded[embedded_publish], utc=True, errors="coerce"
    )
    embedded = embedded.rename(columns={embedded_timestamp: "timestamp"})

    issue_settings = config.get("issue_time", {})
    base["issue_time_utc"] = _issue_time_for_delivery(
        base["timestamp"],
        int(issue_settings.get("local_hour", 13)),
        int(issue_settings.get("local_minute", 0)),
    )

    selected_embedded: list[pd.DataFrame] = []
    for issue_time, delivery_group in base.groupby("issue_time_utc", sort=True):
        eligible = select_latest_available(
            embedded,
            issue_time,
            delivery_columns=["timestamp"],
            published_column=embedded_publish,
        )
        delivery_times = set(delivery_group["timestamp"])
        selected_embedded.append(eligible.loc[eligible["timestamp"].isin(delivery_times)])
    if not selected_embedded:
        raise ValueError("No point-in-time embedded forecasts were eligible")
    embedded_asof = pd.concat(selected_embedded, ignore_index=True).drop_duplicates(
        "timestamp", keep="last"
    )

    embedded_columns = {
        _required(columns, "embedded_wind_mw"): "embedded_wind_mw",
        _required(columns, "embedded_solar_mw"): "embedded_solar_mw",
    }
    absent = [column for column in embedded_columns if column not in embedded_asof]
    if absent:
        raise KeyError(f"Mapped embedded columns are absent: {absent}")
    base = base.merge(
        embedded_asof[["timestamp", *embedded_columns]].rename(columns=embedded_columns),
        on="timestamp",
        how="left",
        validate="one_to_one",
    )

    inertia = loaded["neso_inertia"].copy()
    inertia_timestamp = _required(columns, "inertia_timestamp")
    inertia = _timestamp(inertia, inertia_timestamp).rename(columns={inertia_timestamp: "timestamp"})
    inertia_value = _required(columns, "inertia_gvas")
    if inertia_value not in inertia:
        raise KeyError(f"Mapped inertia column is absent: {inertia_value}")
    inertia = inertia[["timestamp", inertia_value]].drop_duplicates("timestamp", keep="last")
    base = base.merge(
        inertia.rename(columns={inertia_value: "inertia_gvas"}),
        on="timestamp",
        how="left",
        validate="one_to_one",
    )

    for weather_path in ("weather_demand", "weather_wind", "weather_solar"):
        weather = _align_weather(loaded[weather_path], base["timestamp"])
        value_columns = [column for column in weather.columns if column != "timestamp"]
        base = base.merge(
            weather[["timestamp", *value_columns]],
            on="timestamp",
            how="left",
            validate="one_to_one",
        )

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
            for candidate in loaded.values():
                if source_column in candidate and "timestamp" in candidate:
                    found = (
                        _timestamp(candidate)[["timestamp", source_column]]
                        .drop_duplicates("timestamp", keep="last")
                        .rename(columns={source_column: target})
                    )
                    break
            if found is None:
                raise KeyError(f"Configured optional column {source_column} was not found")
            base = base.merge(found, on="timestamp", how="left", validate="one_to_one")
        elif target in required_components:
            raise ValueError(
                f"{target} is required by this modelling profile. Configure its source column."
            )

    base = base.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    base["delivery_time_utc"] = base["timestamp"]
    base["model_profile"] = (
        "full" if "battery_net_mw" in required_components else "core_without_battery"
    )
    required_targets = ["price_gbp_mwh", *required_components]
    missing_counts = base[required_targets].isna().sum()
    if missing_counts.any():
        raise ValueError(
            f"Required target gaps remain: {missing_counts[missing_counts.gt(0)].to_dict()}"
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix == ".csv":
        base.to_csv(output, index=False)
    else:
        base.to_parquet(output, index=False)
    return base
