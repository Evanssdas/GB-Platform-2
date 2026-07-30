import numpy as np
import pandas as pd
import pytest

from gb_platform_v2.live_store import append_actuals, append_forecasts, grade_forecasts
from gb_platform_v2.point_in_time import require_no_future_information, select_latest_available
from gb_platform_v2.validation import expanding_oof_predictions


def test_select_latest_revision_available_at_issue_time():
    frame = pd.DataFrame(
        {
            "delivery": ["2026-08-01", "2026-08-01", "2026-08-01"],
            "published_at_utc": [
                "2026-07-30T08:00:00Z",
                "2026-07-31T08:00:00Z",
                "2026-07-31T15:00:00Z",
            ],
            "value": [10.0, 11.0, 99.0],
        }
    )
    selected = select_latest_available(
        frame,
        pd.Timestamp("2026-07-31T13:00:00Z"),
        ["delivery"],
    )
    assert selected.iloc[0]["value"] == 11.0


def test_future_information_check_raises():
    frame = pd.DataFrame(
        {
            "issue_time_utc": ["2026-07-31T13:00:00Z"],
            "weather_published_at_utc": ["2026-07-31T14:00:00Z"],
        }
    )
    with pytest.raises(ValueError, match="Future-information leakage"):
        require_no_future_information(frame)


def test_append_forecast_rejects_same_immutable_key_after_csv_reload(tmp_path):
    path = tmp_path / "forecasts.csv"
    rows = pd.DataFrame(
        {
            "model_version": ["v1"],
            "issue_time_utc": ["2026-07-31T13:00:00Z"],
            "delivery_time_utc": ["2026-08-01T00:00:00Z"],
            "p10": [20.0],
            "p50": [30.0],
            "p90": [40.0],
        }
    )
    append_forecasts(rows, path)
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        append_forecasts(rows, path)


def test_grading_is_append_only(tmp_path):
    forecast_path = tmp_path / "forecasts.csv"
    actual_path = tmp_path / "actuals.csv"
    scores_path = tmp_path / "scores.csv"
    append_forecasts(
        pd.DataFrame(
            {
                "model_version": ["v1"],
                "issue_time_utc": ["2026-07-31T13:00:00Z"],
                "delivery_time_utc": ["2026-08-01T00:00:00Z"],
                "p10": [20.0],
                "p50": [30.0],
                "p90": [40.0],
                "negative_probability": [0.0],
            }
        ),
        forecast_path,
    )
    append_actuals(
        pd.DataFrame(
            {
                "delivery_time_utc": ["2026-08-01T00:00:00Z"],
                "actual_revision": ["initial"],
                "actual_price": [35.0],
            }
        ),
        actual_path,
    )
    first = grade_forecasts(forecast_path, actual_path, scores_path)
    second = grade_forecasts(forecast_path, actual_path, scores_path)
    assert len(first) == 1
    assert second.empty
    assert first.iloc[0]["absolute_error"] == 5.0
    assert bool(first.iloc[0]["p10_p90_covered"])


def test_expanding_oof_predictions_leave_initial_training_block_blank():
    size = 240
    frame = pd.DataFrame(
        {
            "x": np.arange(size, dtype=float),
            "target": np.arange(size, dtype=float) * 2.0,
        },
        index=pd.date_range("2026-01-01", periods=size, freq="30min", tz="UTC"),
    )
    prediction = expanding_oof_predictions(frame, ["x"], "target", n_splits=4)
    assert prediction.isna().any()
    assert prediction.notna().sum() > 0
    first_predicted = prediction.first_valid_index()
    assert first_predicted > frame.index[0]
