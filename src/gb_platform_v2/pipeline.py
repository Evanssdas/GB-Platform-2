"""Training and forecast orchestration."""

from __future__ import annotations

from pathlib import Path

import numpy as np
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

COMPONENT_TARGETS = [
    "demand_mw",
    "embedded_wind_mw",
    "embedded_solar_mw",
    "transmission_wind_mw",
    "nuclear_mw",
    "net_import_mw",
    "battery_net_mw",
    "inertia_gvas",
]

NON_FEATURE_COLUMNS = {
    "timestamp",
    "timestamp_utc",
    "timestamp_local",
    "delivery_date",
    "price_gbp_mwh",
    "marginal_technology",
    *COMPONENT_TARGETS,
}


def train_platform(
    frame: pd.DataFrame,
    model_dir: str | Path,
    holdout_rows: int = 4320,
) -> dict:
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    features = choose_numeric_features(frame, NON_FEATURE_COLUMNS)
    if not features:
        raise ValueError("No model features found")

    metrics: dict[str, dict] = {}
    component_models: dict[str, TrainedRegressor] = {}
    component_errors = pd.DataFrame(index=frame.index)

    for target in COMPONENT_TARGETS:
        metrics[target] = chronological_holdout_score(
            frame, features, target, holdout_rows, transform="identity"
        )
        fitted = train_regressor(frame, features, target)
        fitted.save(model_dir / f"{target}.joblib")
        component_models[target] = fitted
        component_errors[target] = frame[target] - fitted.predict(frame)

    price_features = [
        *features,
        *COMPONENT_TARGETS,
        "total_wind_mw",
        "renewable_mw",
        "residual_before_nuclear_mw",
        "residual_after_nuclear_mw",
        "net_system_short_mw",
    ]
    price_features = list(dict.fromkeys(column for column in price_features if column in frame.columns))
    metrics["price_gbp_mwh"] = chronological_holdout_score(
        frame,
        price_features,
        "price_gbp_mwh",
        holdout_rows,
        transform="arcsinh",
        scale=50.0,
    )
    price_model = train_regressor(
        frame,
        price_features,
        "price_gbp_mwh",
        transform="arcsinh",
        scale=50.0,
    )
    price_model.save(model_dir / "price_gbp_mwh.joblib")

    if "marginal_technology" in frame.columns:
        marginal = train_marginal_technology_model(frame, price_features, "marginal_technology")
        import joblib

        joblib.dump(marginal, model_dir / "marginal_technology.joblib")

    component_errors.to_parquet(model_dir / "historical_component_errors.parquet")
    write_json({"features": features, "price_features": price_features, "metrics": metrics}, model_dir / "metadata.json")
    return metrics


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

    point = feature_frame.copy()
    for target in COMPONENT_TARGETS:
        model = TrainedRegressor.load(model_dir / f"{target}.joblib")
        point[target] = model.predict(point)

    point["total_wind_mw"] = point["embedded_wind_mw"] + point["transmission_wind_mw"]
    point["renewable_mw"] = point["total_wind_mw"] + point["embedded_solar_mw"]
    point["residual_before_nuclear_mw"] = point["demand_mw"] - point["renewable_mw"]
    point["residual_after_nuclear_mw"] = point["residual_before_nuclear_mw"] - point["nuclear_mw"]
    point["net_system_short_mw"] = (
        point["residual_after_nuclear_mw"] - point["net_import_mw"] - point["battery_net_mw"]
    )

    price_model = TrainedRegressor.load(model_dir / "price_gbp_mwh.joblib")
    point["price_point_gbp_mwh"] = price_model.predict(point)

    errors = pd.read_parquet(model_dir / "historical_component_errors.parquet")
    component_scenarios = bootstrap_error_scenarios(
        point,
        errors,
        COMPONENT_TARGETS,
        scenarios=scenarios,
    )
    result = run_price_monte_carlo(point, component_scenarios, price_model)

    price_output = result.quantiles.copy()
    price_output["point"] = point["price_point_gbp_mwh"]
    price_output["negative_probability"] = result.negative_probability
    price_output.to_csv(output_dir / "half_hourly_price_forecast.csv")
    point.to_csv(output_dir / "half_hourly_system_forecast.csv")
    plot_price_fan_chart(result.quantiles, result.negative_probability, output_dir / "price_fan_chart.png")

    report = daily_price_summary(result.quantiles, result.negative_probability, result.price_paths)
    report["risk"] = scenario_risk(
        result.price_paths,
        point["price_point_gbp_mwh"].to_numpy(),
        position_mwh,
    )
    write_json(report, output_dir / "daily_report.json")
    return report
