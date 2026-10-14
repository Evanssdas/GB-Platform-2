import json

import numpy as np
import pandas as pd

from gb_platform_v2.data.neso import NESO_RESOURCES
from gb_platform_v2.live_store import (
    append_component_actuals,
    append_component_forecasts,
    component_score_summary,
    grade_component_forecasts,
)
from gb_platform_v2.models import train_regressor


def test_2026_neso_embedded_archive_is_registered():
    assert NESO_RESOURCES["embedded_2026"] == "31861619-0b86-47ba-bac2-d008a760af54"


def test_lightgbm_accepts_missing_optional_feature_values():
    frame = pd.DataFrame(
        {
            "x": np.arange(100, dtype=float),
            "optional_market": np.where(np.arange(100) % 3 == 0, np.nan, 5.0),
            "target": np.arange(100, dtype=float) * 2.0,
        }
    )
    model = train_regressor(
        frame,
        ["x", "optional_market"],
        "target",
        params={
            "n_estimators": 20,
            "learning_rate": 0.1,
            "num_leaves": 7,
            "random_state": 42,
            "verbosity": -1,
        },
    )
    prediction = model.predict(frame)
    assert len(prediction) == len(frame)
    assert np.isfinite(prediction).all()


def test_component_forecasts_grade_and_summarise(tmp_path):
    forecast_path = tmp_path / "component_forecasts.csv"
    actual_path = tmp_path / "component_actuals.csv"
    score_path = tmp_path / "component_scores.csv"

    times = pd.date_range("2026-10-01", periods=4, freq="30min", tz="UTC")
    forecasts = pd.DataFrame(
        {
            "model_version": "v2",
            "issue_time_utc": pd.Timestamp("2026-09-30T12:00:00Z"),
            "delivery_time_utc": times,
            "demand_mw": [100.0, 110.0, 120.0, 130.0],
            "nuclear_mw": [10.0, 10.0, 10.0, 10.0],
        }
    )
    actuals = pd.DataFrame(
        {
            "delivery_time_utc": times,
            "actual_revision": "initial",
            "demand_mw": [101.0, 108.0, 124.0, 130.0],
            "nuclear_mw": [10.0, 9.0, 11.0, 10.0],
        }
    )

    append_component_forecasts(forecasts, forecast_path)
    append_component_actuals(actuals, actual_path)
    scored = grade_component_forecasts(forecast_path, actual_path, score_path)

    assert set(scored["component"]) == {"demand_mw", "nuclear_mw"}
    summary = component_score_summary(score_path, "v2")
    assert summary["demand_mw"]["rows"] == 4
    assert summary["demand_mw"]["mae"] == 1.75
    assert summary["nuclear_mw"]["mae"] == 0.5
