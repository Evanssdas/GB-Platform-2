"""Training and forecast orchestration."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .features import choose_numeric_features
from .models import (
    TrainedRegressor,
    chronological_holdout_score,
    train_marginal_technology_model,
    train_regressor,
)
from .reporting import daily_price_summary, plot_price_fan_chart, write_json
from .risk import scenario_risk
from .scenarios import bootstrap_error_scenarios, run_price_monte_carlo
from .validation import expanding_oof_predictions


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
CORE_COMPONENT_TARGETS = [
    "demand_mw",
    "embedded_wind_mw",
    "embedded_solar_mw",
    "transmission_wind_mw",
    "nuclear_mw",
    "net_import_mw",
    "inertia_gvas",
]
DERIVED_TARGET_COLUMNS = {
    "total_wind_mw",
    "renewable_mw",
    "residual_before_nuclear_mw",
    "residual_after_nuclear_mw",
    "net_system_short_mw",
}
BASE_NON_FEATURE_COLUMNS = {
    "timestamp",
    "timestamp_utc",
    "timestamp_local",
    "delivery_time_utc",
    "delivery_date",
    "issue_time_utc",
    "price_gbp_mwh",
    "marginal_technology",
    "model_profile",
    *FULL_COMPONENT_TARGETS,
    *DERIVED_TARGET_COLUMNS,
}


def _component_targets(frame: pd.DataFrame) -> tuple[str, list[str]]:
    profiles = set(frame.get("model_profile", pd.Series(dtype=str)).dropna().astype(str))
    if not profiles:
        targets = [column for column in FULL_COMPONENT_TARGETS if column in frame]
        profile = "full" if "battery_net_mw" in targets else "core_without_battery"
    elif profiles == {"full"}:
        profile = "full"
        targets = FULL_COMPONENT_TARGETS
    elif profiles == {"core_without_battery"}:
        profile = "core_without_battery"
        targets = CORE_COMPONENT_TARGETS
    else:
        raise ValueError(f"Dataset contains inconsistent model profiles: {sorted(profiles)}")

    missing = [column for column in targets if column not in frame]
    if missing:
        raise KeyError(f"Dataset is missing profile components: {missing}")
    return profile, targets


def _add_stacked_balance_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["total_wind_mw"] = out["embedded_wind_mw"] + out["transmission_wind_mw"]
    out["renewable_mw"] = out["total_wind_mw"] + out["embedded_solar_mw"]
    out["residual_before_nuclear_mw"] = out["demand_mw"] - out["renewable_mw"]
    out["residual_after_nuclear_mw"] = (
        out["residual_before_nuclear_mw"] - out["nuclear_mw"]
    )
    out["net_system_short_mw"] = out["residual_after_nuclear_mw"] - out["net_import_mw"]
    if "battery_net_mw" in out:
        out["net_system_short_mw"] = out["net_system_short_mw"] - out["battery_net_mw"]
    return out


def train_platform(
    frame: pd.DataFrame,
    model_dir: str | Path,
    holdout_rows: int = 4320,
    time_series_splits: int = 5,
) -> dict:
    """Train component and price models with leakage-safe stacking."""
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    profile, component_targets = _component_targets(frame)
    features = choose_numeric_features(frame, BASE_NON_FEATURE_COLUMNS)
    if not features:
        raise ValueError("No model features found")

    metrics: dict[str, dict] = {}
    component_errors = pd.DataFrame(index=frame.index)
    stacked = pd.DataFrame(index=frame.index)

    for target in component_targets:
        metrics[target] = chronological_holdout_score(
            frame, features, target, holdout_rows, transform="identity"
        )
        oof = expanding_oof_predictions(
            frame,
            features,
            target,
            n_splits=time_series_splits,
        )
        stacked[target] = oof
        component_errors[target] = frame[target] - oof
        train_regressor(frame, features, target).save(model_dir / f"{target}.joblib")

    price_training = frame.drop(columns=component_targets, errors="ignore").copy()
    for target in component_targets:
        price_training[target] = stacked[target]
    price_training = _add_stacked_balance_features(price_training)

    price_features = [
        *features,
        *component_targets,
        "total_wind_mw",
        "renewable_mw",
        "residual_before_nuclear_mw",
        "residual_after_nuclear_mw",
        "net_system_short_mw",
    ]
    price_features = list(
        dict.fromkeys(column for column in price_features if column in price_training.columns)
    )

    metrics["price_gbp_mwh"] = chronological_holdout_score(
        price_training,
        price_features,
        "price_gbp_mwh",
        holdout_rows,
        transform="arcsinh",
        scale=50.0,
    )
    train_regressor(
        price_training,
        price_features,
        "price_gbp_mwh",
        transform="arcsinh",
        scale=50.0,
    ).save(model_dir / "price_gbp_mwh.joblib")

    if "marginal_technology" in price_training.columns:
        marginal_frame = price_training.dropna(subset=[*price_features, "marginal_technology"])
        if not marginal_frame.empty:
            marginal = train_marginal_technology_model(
                marginal_frame,
                price_features,
                "marginal_technology",
            )
            import joblib

            joblib.dump(marginal, model_dir / "marginal_technology.joblib")

    component_errors.dropna(how="any").to_parquet(
        model_dir / "historical_component_errors.parquet"
    )
    write_json(
        {
            "model_profile": profile,
            "component_targets": component_targets,
            "features": features,
            "price_features": price_features,
            "metrics": metrics,
            "stacking": "expanding_window_out_of_fold",
            "time_series_splits": time_series_splits,
        },
        model_dir / "metadata.json",
    )
    return metrics


def _operational_component_point_forecasts(
    feature_frame: pd.DataFrame,
    model_dir: Path,
    metadata: dict,
) -> tuple[pd.DataFrame, dict[str, str]]:
    point = feature_frame.copy()
    targets = metadata.get("component_targets", FULL_COMPONENT_TARGETS)
    strategy = metadata.get("operational_component_strategy", {})
    used: dict[str, str] = {}

    for target in targets:
        source = strategy.get(target, {}).get("source", "model")
        if source == "fallback_d7":
            fallback_column = f"fallback_d7_{target}"
            if fallback_column not in point:
                raise KeyError(
                    f"Operational strategy requires missing column {fallback_column}"
                )
            values = pd.to_numeric(point[fallback_column], errors="coerce")
            if values.isna().any():
                raise ValueError(f"Operational fallback contains nulls: {fallback_column}")
            point[target] = values.to_numpy(dtype=float)
        elif source == "model":
            model = TrainedRegressor.load(model_dir / f"{target}.joblib")
            point[target] = model.predict(point)
        else:
            raise ValueError(f"Unsupported operational source for {target}: {source}")
        used[target] = source
        point[f"component_source_{target}"] = source
    return point, used


def forecast_platform(
    feature_frame: pd.DataFrame,
    model_dir: str | Path,
    output_dir: str | Path,
    scenarios: int = 1000,
    position_mwh: float = 100.0,
) -> dict:
    model_dir = Path(model_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    component_targets = metadata.get("component_targets", FULL_COMPONENT_TARGETS)

    point, component_sources = _operational_component_point_forecasts(
        feature_frame, model_dir, metadata
    )
    point = _add_stacked_balance_features(point)
    price_model = TrainedRegressor.load(model_dir / "price_gbp_mwh.joblib")
    point["price_point_gbp_mwh"] = price_model.predict(point)

    error_file = metadata.get("component_error_file", "historical_component_errors.parquet")
    errors = pd.read_parquet(model_dir / error_file)
    component_scenarios = bootstrap_error_scenarios(
        point,
        errors,
        component_targets,
        scenarios=scenarios,
    )
    result = run_price_monte_carlo(point, component_scenarios, price_model)

    price_output = result.quantiles.copy()
    price_output["point"] = point["price_point_gbp_mwh"]
    price_output["negative_probability"] = result.negative_probability
    price_output.to_csv(output_dir / "half_hourly_price_forecast.csv")
    point.to_csv(output_dir / "half_hourly_system_forecast.csv")
    plot_price_fan_chart(
        result.quantiles,
        result.negative_probability,
        output_dir / "price_fan_chart.png",
    )

    report = daily_price_summary(
        result.quantiles,
        result.negative_probability,
        result.price_paths,
    )
    report["model_profile"] = metadata.get("model_profile", "unknown")
    report["operational_bundle_ready"] = bool(metadata.get("operational_bundle_ready"))
    report["component_sources"] = component_sources
    report["component_error_file"] = error_file
    report["risk"] = scenario_risk(
        result.price_paths,
        point["price_point_gbp_mwh"].to_numpy(),
        position_mwh,
    )
    write_json(report, output_dir / "daily_report.json")
    return report
