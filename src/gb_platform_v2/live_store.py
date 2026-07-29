"""Append-only forecast, actual and score storage.

CSV is used for portability. Production deployments can replace these functions
with a database while preserving the same unique-key and immutability rules.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

FORECAST_KEY = ["model_version", "issue_time_utc", "delivery_time_utc"]
ACTUAL_KEY = ["delivery_time_utc", "actual_revision"]
SCORE_KEY = ["forecast_id", "actual_revision"]


def _read(path: str | Path) -> pd.DataFrame:
    file = Path(path)
    return pd.read_csv(file) if file.exists() else pd.DataFrame()


def _append_unique(
    new_rows: pd.DataFrame,
    path: str | Path,
    key: list[str],
) -> pd.DataFrame:
    missing = [column for column in key if column not in new_rows]
    if missing:
        raise KeyError(f"Missing immutable key columns: {missing}")
    existing = _read(path)
    combined = pd.concat([existing, new_rows], ignore_index=True)
    duplicates = combined.duplicated(subset=key, keep=False)
    if duplicates.any():
        duplicate_rows = combined.loc[duplicates, key].drop_duplicates().to_dict("records")
        raise ValueError(f"Refusing to overwrite existing immutable rows: {duplicate_rows[:5]}")
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(file, index=False)
    return combined


def append_forecasts(rows: pd.DataFrame, path: str | Path) -> pd.DataFrame:
    out = rows.copy()
    out["issue_time_utc"] = pd.to_datetime(out["issue_time_utc"], utc=True)
    out["delivery_time_utc"] = pd.to_datetime(out["delivery_time_utc"], utc=True)
    if "forecast_id" not in out:
        out["forecast_id"] = (
            out["model_version"].astype(str)
            + "|"
            + out["issue_time_utc"].astype(str)
            + "|"
            + out["delivery_time_utc"].astype(str)
        )
    return _append_unique(out, path, FORECAST_KEY)


def append_actuals(rows: pd.DataFrame, path: str | Path) -> pd.DataFrame:
    out = rows.copy()
    out["delivery_time_utc"] = pd.to_datetime(out["delivery_time_utc"], utc=True)
    return _append_unique(out, path, ACTUAL_KEY)


def grade_forecasts(
    forecasts_path: str | Path,
    actuals_path: str | Path,
    scores_path: str | Path,
) -> pd.DataFrame:
    forecasts = _read(forecasts_path)
    actuals = _read(actuals_path)
    if forecasts.empty or actuals.empty:
        return pd.DataFrame()
    forecasts["delivery_time_utc"] = pd.to_datetime(forecasts["delivery_time_utc"], utc=True)
    actuals["delivery_time_utc"] = pd.to_datetime(actuals["delivery_time_utc"], utc=True)
    joined = forecasts.merge(actuals, on="delivery_time_utc", how="inner")
    required = {"forecast_id", "actual_revision", "p10", "p50", "p90", "actual_price"}
    missing = required - set(joined)
    if missing:
        raise KeyError(f"Cannot grade forecasts; missing columns: {sorted(missing)}")

    scores = pd.DataFrame(
        {
            "forecast_id": joined["forecast_id"],
            "actual_revision": joined["actual_revision"],
            "delivery_time_utc": joined["delivery_time_utc"],
            "error": joined["p50"] - joined["actual_price"],
            "absolute_error": (joined["p50"] - joined["actual_price"]).abs(),
            "squared_error": (joined["p50"] - joined["actual_price"]) ** 2,
            "p10_p90_covered": joined["actual_price"].between(joined["p10"], joined["p90"]),
            "actual_negative": joined["actual_price"] < 0,
            "predicted_negative_probability": joined.get(
                "negative_probability",
                pd.Series(np.nan, index=joined.index),
            ),
            "graded_at_utc": pd.Timestamp.now(tz="UTC"),
        }
    )
    existing = _read(scores_path)
    if not existing.empty:
        existing_keys = set(zip(existing["forecast_id"], existing["actual_revision"]))
        keep = [
            (forecast_id, revision) not in existing_keys
            for forecast_id, revision in zip(scores["forecast_id"], scores["actual_revision"])
        ]
        scores = scores.loc[keep]
    if scores.empty:
        return scores
    return _append_unique(scores, scores_path, SCORE_KEY)
