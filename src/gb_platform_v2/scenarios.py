"""Correlated Monte Carlo scenarios for component and price uncertainty."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .models import TrainedRegressor


@dataclass
class ScenarioResult:
    price_paths: np.ndarray
    quantiles: pd.DataFrame
    negative_probability: pd.Series


def bootstrap_error_scenarios(
    point_components: pd.DataFrame,
    historical_error_rows: pd.DataFrame,
    component_columns: list[str],
    scenarios: int = 1000,
    random_seed: int = 42,
    price_error_column: str | None = "price_error_gbp_mwh",
) -> dict[str, np.ndarray]:
    """Sample complete historical error rows to preserve empirical dependence.

    When an out-of-fold price residual column is available it is sampled from the
    same historical row as the component errors, so the scenario distribution
    includes uncertainty left unexplained by the physical price model.
    """
    if scenarios <= 0:
        raise ValueError("scenarios must be positive")
    required = list(component_columns)
    if price_error_column and price_error_column in historical_error_rows:
        required.append(price_error_column)
    errors = historical_error_rows.dropna(subset=required)
    if errors.empty:
        raise ValueError("No complete historical error rows")
    rng = np.random.default_rng(random_seed)
    draw_idx = rng.integers(0, len(errors), size=(scenarios, len(point_components)))
    output: dict[str, np.ndarray] = {}
    for column in component_columns:
        sampled = errors[column].to_numpy()[draw_idx]
        point = point_components[column].to_numpy()[None, :]
        values = point + sampled
        if column not in {"net_import_mw", "battery_net_mw"}:
            values = np.maximum(values, 0.0)
        output[column] = values
    if price_error_column and price_error_column in errors:
        output["__price_error_gbp_mwh__"] = errors[price_error_column].to_numpy()[draw_idx]
    return output


def calibrate_scenario_result(
    result: ScenarioResult,
    bias_correction_gbp_mwh: float = 0.0,
    dispersion_scale: float = 1.0,
) -> ScenarioResult:
    """Shift the scenario centre and rescale dispersion around each period median."""
    bias = float(bias_correction_gbp_mwh)
    scale = max(1.0, float(dispersion_scale))
    raw_paths = np.asarray(result.price_paths, dtype=float)
    raw_median = np.percentile(raw_paths, 50, axis=0)
    adjusted_center = raw_median + bias
    adjusted_paths = adjusted_center[None, :] + scale * (
        raw_paths - raw_median[None, :]
    )
    quantiles = pd.DataFrame(
        {
            "p10": np.percentile(adjusted_paths, 10, axis=0),
            "p50": np.percentile(adjusted_paths, 50, axis=0),
            "p90": np.percentile(adjusted_paths, 90, axis=0),
        },
        index=result.quantiles.index,
    )
    negative_probability = pd.Series(
        (adjusted_paths < 0).mean(axis=0),
        index=result.negative_probability.index,
    )
    return ScenarioResult(adjusted_paths, quantiles, negative_probability)


def run_price_monte_carlo(
    point_features: pd.DataFrame,
    component_scenarios: dict[str, np.ndarray],
    price_model: TrainedRegressor,
) -> ScenarioResult:
    scenario_count = next(iter(component_scenarios.values())).shape[0]
    horizon = len(point_features)
    paths = np.empty((scenario_count, horizon), dtype=float)

    for scenario in range(scenario_count):
        frame = point_features.copy()
        for column, values in component_scenarios.items():
            if column.startswith("__"):
                continue
            frame[column] = values[scenario]
        frame["total_wind_mw"] = frame.get("embedded_wind_mw", 0) + frame.get(
            "transmission_wind_mw", 0
        )
        frame["renewable_mw"] = frame["total_wind_mw"] + frame.get("embedded_solar_mw", 0)
        frame["residual_before_nuclear_mw"] = frame["demand_mw"] - frame["renewable_mw"]
        frame["residual_after_nuclear_mw"] = (
            frame["residual_before_nuclear_mw"] - frame.get("nuclear_mw", 0)
        )
        frame["net_system_short_mw"] = (
            frame["residual_after_nuclear_mw"]
            - frame.get("net_import_mw", 0)
            - frame.get("battery_net_mw", 0)
        )
        price_path = price_model.predict(frame)
        residuals = component_scenarios.get("__price_error_gbp_mwh__")
        if residuals is not None:
            price_path = price_path + residuals[scenario]
        paths[scenario] = price_path

    quantiles = pd.DataFrame(
        {
            "p10": np.percentile(paths, 10, axis=0),
            "p50": np.percentile(paths, 50, axis=0),
            "p90": np.percentile(paths, 90, axis=0),
        },
        index=point_features.index,
    )
    negative_probability = pd.Series((paths < 0).mean(axis=0), index=point_features.index)
    return ScenarioResult(paths, quantiles, negative_probability)
