"""Leakage-safe live calibration from previously graded forecasts."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def fit_live_calibration(
    scores_path: str | Path,
    forecasts_path: str | Path,
    issue_time_utc: str | pd.Timestamp,
    source_model_version: str | None = None,
    lookback_days: int = 7,
    target_coverage: float = 0.80,
    min_rows: int = 96,
    max_dispersion_scale: float = 4.0,
) -> dict:
    """Estimate rolling location and dispersion using only already-delivered outcomes.

    Error is forecast P50 minus actual, so the location correction is minus the
    median historical error. Dispersion is calibrated from the empirical ratio
    between the bias-adjusted miss and the corresponding raw P10/P90 half-width.
    No delivery at or after issue_time_utc is eligible.
    """
    issue = pd.Timestamp(issue_time_utc)
    issue = issue.tz_localize("UTC") if issue.tzinfo is None else issue.tz_convert("UTC")
    score_file = Path(scores_path)
    forecast_file = Path(forecasts_path)
    unavailable = {
        "enabled": False,
        "reason": "insufficient_past_grading",
        "bias_correction_gbp_mwh": 0.0,
        "dispersion_scale": 1.0,
        "history_rows": 0,
        "lookback_days": int(lookback_days),
        "target_coverage": float(target_coverage),
        "source_model_version": source_model_version,
    }
    if not score_file.exists() or not forecast_file.exists():
        return unavailable

    scores = pd.read_csv(score_file)
    forecasts = pd.read_csv(forecast_file)
    if scores.empty or forecasts.empty:
        return unavailable

    for frame in (scores, forecasts):
        frame["delivery_time_utc"] = pd.to_datetime(
            frame["delivery_time_utc"], utc=True, errors="coerce"
        )
    scores["issue_time_utc"] = pd.to_datetime(
        scores["issue_time_utc"], utc=True, errors="coerce"
    )
    forecasts["issue_time_utc"] = pd.to_datetime(
        forecasts["issue_time_utc"], utc=True, errors="coerce"
    )

    if source_model_version:
        scores = scores.loc[
            scores["model_version"].astype(str).eq(str(source_model_version))
        ]
        forecasts = forecasts.loc[
            forecasts["model_version"].astype(str).eq(str(source_model_version))
        ]

    cutoff = issue - pd.Timedelta(days=int(lookback_days))
    scores = scores.loc[
        scores["delivery_time_utc"].lt(issue)
        & scores["delivery_time_utc"].ge(cutoff)
    ].copy()
    if len(scores) < min_rows:
        unavailable["history_rows"] = int(len(scores))
        return unavailable

    needed = ["forecast_id", "p10", "p50", "p90"]
    if any(column not in forecasts for column in needed):
        unavailable["reason"] = "forecast_history_missing_quantiles"
        return unavailable

    quantiles = forecasts[needed].drop_duplicates("forecast_id", keep="last")
    history = scores.merge(quantiles, on="forecast_id", how="inner", validate="many_to_one")
    history = history.dropna(subset=["actual_price", "p10", "p50", "p90"])
    if len(history) < min_rows:
        unavailable["history_rows"] = int(len(history))
        return unavailable

    raw_error = pd.to_numeric(history["p50"], errors="coerce") - pd.to_numeric(
        history["actual_price"], errors="coerce"
    )
    median_error = float(np.nanmedian(raw_error))
    bias_correction = -median_error
    adjusted_center = pd.to_numeric(history["p50"], errors="coerce") + bias_correction
    actual = pd.to_numeric(history["actual_price"], errors="coerce")
    lower_width = (
        pd.to_numeric(history["p50"], errors="coerce")
        - pd.to_numeric(history["p10"], errors="coerce")
    ).clip(lower=1e-6)
    upper_width = (
        pd.to_numeric(history["p90"], errors="coerce")
        - pd.to_numeric(history["p50"], errors="coerce")
    ).clip(lower=1e-6)
    miss = actual - adjusted_center
    required_scale = np.where(
        miss < 0,
        np.abs(miss.to_numpy()) / lower_width.to_numpy(),
        np.abs(miss.to_numpy()) / upper_width.to_numpy(),
    )
    required_scale = required_scale[np.isfinite(required_scale)]
    if len(required_scale) < min_rows:
        dispersion = 1.0
    else:
        dispersion = float(np.quantile(required_scale, target_coverage))
        dispersion = float(np.clip(dispersion, 1.0, max_dispersion_scale))

    before_coverage = float(actual.between(history["p10"], history["p90"]).mean())
    adjusted_low = adjusted_center - dispersion * lower_width
    adjusted_high = adjusted_center + dispersion * upper_width
    after_coverage = float(actual.between(adjusted_low, adjusted_high).mean())

    return {
        "enabled": True,
        "reason": "rolling_past_grading",
        "bias_correction_gbp_mwh": bias_correction,
        "dispersion_scale": dispersion,
        "history_rows": int(len(history)),
        "lookback_days": int(lookback_days),
        "target_coverage": float(target_coverage),
        "source_model_version": source_model_version,
        "lookback_raw_coverage": before_coverage,
        "lookback_adjusted_coverage": after_coverage,
    }
