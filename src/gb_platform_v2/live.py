"""Live forecast, actual and grading orchestration."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .data.elexon import ElexonClient
from .data.parsers import parse_elexon_mid
from .features import add_cyclical_time_features, add_weather_features
from .live_store import append_actuals, append_forecasts, grade_forecasts
from .pipeline import forecast_platform


def _load_feature_frame(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    frame = pd.read_parquet(source) if source.suffix == ".parquet" else pd.read_csv(source)
    if "timestamp" not in frame:
        raise KeyError("Live feature input must contain timestamp")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.set_index("timestamp", drop=False).sort_index()
    frame = add_cyclical_time_features(frame)
    return add_weather_features(frame)


def run_and_log_forecast(
    feature_path: str | Path,
    model_dir: str | Path,
    output_dir: str | Path,
    forecasts_path: str | Path,
    model_version: str,
    issue_time_utc: str | pd.Timestamp,
    scenarios: int = 1000,
) -> dict:
    """Run the frozen model and append immutable probabilistic forecasts."""
    features = _load_feature_frame(feature_path)
    report = forecast_platform(features, model_dir, output_dir, scenarios)
    price_path = Path(output_dir) / "half_hourly_price_forecast.csv"
    prices = pd.read_csv(price_path, index_col=0)
    prices.index = pd.to_datetime(prices.index, utc=True)
    prices = prices.rename_axis("delivery_time_utc").reset_index()
    prices["model_version"] = model_version
    issue = pd.Timestamp(issue_time_utc)
    issue = issue.tz_localize("UTC") if issue.tzinfo is None else issue.tz_convert("UTC")
    prices["issue_time_utc"] = issue
    append_forecasts(
        prices[
            [
                "model_version",
                "issue_time_utc",
                "delivery_time_utc",
                "p10",
                "p50",
                "p90",
                "point",
                "negative_probability",
            ]
        ],
        forecasts_path,
    )
    return report


def collect_and_append_price_actuals(
    start: str,
    end: str,
    actuals_path: str | Path,
    revision: str,
) -> pd.DataFrame:
    """Collect APXMIDP actuals and append them as a named source revision."""
    parsed = parse_elexon_mid(ElexonClient().market_index(start, end))
    actuals = parsed.rename(
        columns={"timestamp": "delivery_time_utc", "price_gbp_mwh": "actual_price"}
    )[["delivery_time_utc", "actual_price"]]
    actuals["actual_revision"] = revision
    return append_actuals(actuals, actuals_path)


def grade_live_store(
    forecasts_path: str | Path,
    actuals_path: str | Path,
    scores_path: str | Path,
) -> pd.DataFrame:
    return grade_forecasts(forecasts_path, actuals_path, scores_path)
