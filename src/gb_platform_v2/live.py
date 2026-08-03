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


def _existing_forecast_covers_delivery_day(
    forecasts_path: str | Path,
    model_version: str,
    delivery_times: pd.Series,
) -> bool:
    """Return whether an immutable stored forecast exactly covers these periods."""
    path = Path(forecasts_path)
    if not path.exists() or path.stat().st_size == 0:
        return False

    expected = pd.DatetimeIndex(pd.to_datetime(delivery_times, utc=True)).sort_values()
    expected_days = expected.tz_convert("Europe/London").date
    if len(set(expected_days)) != 1:
        raise ValueError("A repair run must contain exactly one GB delivery day")
    delivery_day = expected_days[0]

    existing = pd.read_csv(path)
    required = {"model_version", "delivery_time_utc"}
    missing = required - set(existing)
    if missing:
        raise KeyError(f"Existing forecast log is missing columns: {sorted(missing)}")
    existing["delivery_time_utc"] = pd.to_datetime(
        existing["delivery_time_utc"], utc=True, errors="raise"
    )
    existing_days = existing["delivery_time_utc"].dt.tz_convert("Europe/London").dt.date
    selected = existing.loc[
        existing["model_version"].astype(str).eq(str(model_version))
        & existing_days.eq(delivery_day)
    ].copy()
    if selected.empty:
        return False

    stored = pd.DatetimeIndex(selected["delivery_time_utc"]).sort_values()
    if not stored.equals(expected):
        raise ValueError(
            "Existing immutable forecast does not exactly cover the repair run's "
            f"delivery periods: model_version={model_version}, delivery_date={delivery_day}"
        )
    return True


def run_and_log_forecast(
    feature_path: str | Path,
    model_dir: str | Path,
    output_dir: str | Path,
    forecasts_path: str | Path,
    model_version: str,
    issue_time_utc: str | pd.Timestamp,
    scenarios: int = 1000,
    reuse_existing_day: bool = False,
) -> dict:
    """Run the frozen model and append immutable probabilistic forecasts.

    When ``reuse_existing_day`` is enabled, a complete immutable forecast that
    already covers the same model and GB delivery day is preserved rather than
    appended again. This mode is intended only for rebuilding missing reports
    and plots after a partially failed workflow run.
    """
    features = _load_feature_frame(feature_path)
    report = forecast_platform(features, model_dir, output_dir, scenarios)
    price_path = Path(output_dir) / "half_hourly_price_forecast.csv"
    prices = pd.read_csv(price_path, index_col=0)
    prices.index = pd.to_datetime(prices.index, utc=True)
    prices = prices.rename_axis("delivery_time_utc").reset_index()
    prices["model_version"] = model_version
    issue = pd.Timestamp(issue_time_utc)
    issue = issue.tz_localize("UTC") if issue.tzinfo is None else issue.tz_convert("UTC")
    if (prices["delivery_time_utc"] <= issue).any():
        raise ValueError("Forecast delivery periods must all be later than issue time")
    prices["issue_time_utc"] = issue

    reused = False
    if reuse_existing_day:
        reused = _existing_forecast_covers_delivery_day(
            forecasts_path,
            model_version,
            prices["delivery_time_utc"],
        )

    if not reused:
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

    if isinstance(report, dict):
        report = dict(report)
        report["forecast_log_status"] = (
            "reused_existing_immutable_day" if reused else "appended_new_immutable_day"
        )
    return report


def _gb_settlement_boundary_utc(value: str | pd.Timestamp) -> pd.Timestamp:
    day = pd.Timestamp(value).tz_localize(None).normalize()
    return day.tz_localize("Europe/London").tz_convert("UTC")


def collect_and_append_price_actuals(
    start: str,
    end: str,
    actuals_path: str | Path,
    revision: str,
) -> pd.DataFrame:
    """Collect APXMIDP actuals for a GB settlement-date ``[start, end)`` window."""
    start_utc = _gb_settlement_boundary_utc(start)
    end_utc = _gb_settlement_boundary_utc(end)
    parsed = parse_elexon_mid(
        ElexonClient().market_index(
            start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    )
    parsed["timestamp"] = pd.to_datetime(parsed["timestamp"], utc=True)
    parsed = parsed.loc[
        parsed["timestamp"].between(start_utc, end_utc, inclusive="left")
    ].copy()
    expected = pd.date_range(start_utc, end_utc, freq="30min", inclusive="left")
    actual = pd.DatetimeIndex(parsed["timestamp"])
    missing = expected.difference(actual)
    if len(parsed) != len(expected) or len(missing):
        raise ValueError(
            "APXMIDP actuals do not cover the complete GB settlement day: "
            f"rows={len(parsed)}, expected={len(expected)}, missing={len(missing)}"
        )
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
