import numpy as np
import pandas as pd
import pytest

from gb_platform_v2.calibration import fit_live_calibration
from gb_platform_v2.scenarios import (
    ScenarioResult,
    bootstrap_error_scenarios,
    calibrate_scenario_result,
)


def test_live_calibration_uses_only_pre_issue_history(tmp_path):
    issue = pd.Timestamp("2026-10-10T12:00:00Z")
    delivery = pd.date_range(
        issue - pd.Timedelta(days=7),
        periods=48 * 7,
        freq="30min",
        tz="UTC",
    )
    forecasts = pd.DataFrame(
        {
            "forecast_id": [f"f{i}" for i in range(len(delivery))],
            "model_version": "v1",
            "issue_time_utc": delivery - pd.Timedelta(days=1),
            "delivery_time_utc": delivery,
            "p10": 40.0,
            "p50": 50.0,
            "p90": 60.0,
        }
    )
    # Model is systematically GBP 30/MWh too low.
    scores = pd.DataFrame(
        {
            "forecast_id": forecasts["forecast_id"],
            "model_version": "v1",
            "issue_time_utc": forecasts["issue_time_utc"],
            "delivery_time_utc": delivery,
            "actual_price": 80.0,
            "error": -30.0,
        }
    )

    forecast_path = tmp_path / "forecasts.csv"
    score_path = tmp_path / "scores.csv"
    forecasts.to_csv(forecast_path, index=False)
    scores.to_csv(score_path, index=False)

    result = fit_live_calibration(
        score_path,
        forecast_path,
        issue,
        source_model_version="v1",
        lookback_days=7,
        min_rows=96,
    )

    assert result["enabled"] is True
    assert result["bias_correction_gbp_mwh"] == pytest.approx(30.0)
    assert result["history_rows"] == len(delivery)
    assert result["dispersion_scale"] >= 1.0


def test_scenario_bootstrap_adds_price_residual_from_same_draw():
    point = pd.DataFrame(
        {"demand_mw": [100.0, 100.0], "wind_mw": [50.0, 50.0]}
    )
    errors = pd.DataFrame(
        {
            "demand_mw": [1.0, 2.0, 3.0],
            "wind_mw": [-1.0, -2.0, -3.0],
            "price_error_gbp_mwh": [10.0, 20.0, 30.0],
        }
    )
    result = bootstrap_error_scenarios(
        point,
        errors,
        ["demand_mw", "wind_mw"],
        scenarios=20,
        random_seed=7,
    )
    assert "__price_error_gbp_mwh__" in result

    demand_error = result["demand_mw"] - 100.0
    wind_error = result["wind_mw"] - 50.0
    price_error = result["__price_error_gbp_mwh__"]

    # The three columns came from one historical row, not independent draws.
    assert np.allclose(wind_error, -demand_error)
    assert np.allclose(price_error, demand_error * 10.0)


def test_calibrate_scenario_result_shifts_and_widens_distribution():
    index = pd.date_range("2026-10-11", periods=2, freq="30min", tz="UTC")
    paths = np.array([[40.0, 50.0], [50.0, 60.0], [60.0, 70.0]])
    raw = ScenarioResult(
        price_paths=paths,
        quantiles=pd.DataFrame(
            {
                "p10": np.percentile(paths, 10, axis=0),
                "p50": np.percentile(paths, 50, axis=0),
                "p90": np.percentile(paths, 90, axis=0),
            },
            index=index,
        ),
        negative_probability=pd.Series(0.0, index=index),
    )

    adjusted = calibrate_scenario_result(
        raw,
        bias_correction_gbp_mwh=20.0,
        dispersion_scale=2.0,
    )

    assert np.allclose(
        adjusted.quantiles["p50"].to_numpy(),
        raw.quantiles["p50"].to_numpy() + 20.0,
    )
    assert np.all(
        (adjusted.quantiles["p90"] - adjusted.quantiles["p10"])
        > (raw.quantiles["p90"] - raw.quantiles["p10"])
    )
