"""Append-only forecast and actual storage with reproducible derived scores.

CSV is used for portability. Forecasts and actuals remain immutable source records.
Scores are derived records and may be recomputed when additional supporting
actuals, such as the prior-day persistence source, become available.
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


def _normalise_key_values(frame: pd.DataFrame, key: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for column in key:
        if column.endswith("_utc"):
            parsed = pd.to_datetime(out[column], utc=True, errors="raise")
            out[column] = parsed.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            out[column] = out[column].astype(str)
    return out


def _append_unique(
    new_rows: pd.DataFrame,
    path: str | Path,
    key: list[str],
) -> pd.DataFrame:
    missing = [column for column in key if column not in new_rows]
    if missing:
        raise KeyError(f"Missing immutable key columns: {missing}")
    existing = _read(path)
    new_normalised = _normalise_key_values(new_rows, key)
    existing_normalised = (
        _normalise_key_values(existing, key) if not existing.empty else existing.copy()
    )
    combined = pd.concat([existing_normalised, new_normalised], ignore_index=True)
    duplicates = combined.duplicated(subset=key, keep=False)
    if duplicates.any():
        duplicate_rows = combined.loc[duplicates, key].drop_duplicates().to_dict("records")
        raise ValueError(f"Refusing to overwrite existing immutable rows: {duplicate_rows[:5]}")
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(file, index=False)
    return combined


def _append_new_rows(
    new_rows: pd.DataFrame,
    path: str | Path,
    key: list[str],
) -> pd.DataFrame:
    """Append unseen immutable keys and silently skip keys already stored."""
    existing = _read(path)
    incoming = _normalise_key_values(new_rows, key)
    if not existing.empty:
        existing = _normalise_key_values(existing, key)
        existing_keys = set(map(tuple, existing[key].itertuples(index=False, name=None)))
        keep = [
            tuple(row) not in existing_keys
            for row in incoming[key].itertuples(index=False, name=None)
        ]
        incoming = incoming.loc[keep]
    if incoming.empty:
        return incoming
    combined = pd.concat([existing, incoming], ignore_index=True)
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(file, index=False)
    return incoming


def _upsert_derived_rows(
    rows: pd.DataFrame,
    path: str | Path,
    key: list[str],
) -> pd.DataFrame:
    """Replace derived rows with the latest deterministic recomputation."""
    missing = [column for column in key if column not in rows]
    if missing:
        raise KeyError(f"Missing derived key columns: {missing}")

    incoming = _normalise_key_values(rows, key)
    existing = _read(path)
    if not existing.empty:
        existing = _normalise_key_values(existing, key)
        incoming_keys = set(map(tuple, incoming[key].itertuples(index=False, name=None)))
        keep = [
            tuple(row) not in incoming_keys
            for row in existing[key].itertuples(index=False, name=None)
        ]
        existing = existing.loc[keep]

    combined = pd.concat([existing, incoming], ignore_index=True)
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(file, index=False)
    return incoming


def append_forecasts(rows: pd.DataFrame, path: str | Path) -> pd.DataFrame:
    out = rows.copy()
    out["issue_time_utc"] = pd.to_datetime(out["issue_time_utc"], utc=True)
    out["delivery_time_utc"] = pd.to_datetime(out["delivery_time_utc"], utc=True)

    versions = out["model_version"].astype(str).unique()
    delivery_days = (
        out["delivery_time_utc"].dt.tz_convert("Europe/London").dt.date.astype(str).unique()
    )
    if len(versions) != 1 or len(delivery_days) != 1:
        raise ValueError("One append_forecasts call must contain one model version and one GB delivery day")

    existing = _read(path)
    if not existing.empty:
        existing_times = pd.to_datetime(existing["delivery_time_utc"], utc=True, errors="raise")
        existing_days = existing_times.dt.tz_convert("Europe/London").dt.date.astype(str)
        duplicate_day = existing["model_version"].astype(str).eq(versions[0]) & existing_days.eq(
            delivery_days[0]
        )
        if duplicate_day.any():
            raise ValueError(
                "Refusing to overwrite an existing forecast for the same model version "
                "and GB delivery day: "
                f"model_version={versions[0]}, delivery_date={delivery_days[0]}"
            )

    if "forecast_id" not in out:
        out["forecast_id"] = (
            out["model_version"].astype(str)
            + "|"
            + out["issue_time_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            + "|"
            + out["delivery_time_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    return _append_unique(out, path, FORECAST_KEY)


def append_actuals(rows: pd.DataFrame, path: str | Path) -> pd.DataFrame:
    out = rows.copy()
    out["delivery_time_utc"] = pd.to_datetime(out["delivery_time_utc"], utc=True)
    return _append_new_rows(out, path, ACTUAL_KEY)


def _actual_persistence(actuals: pd.DataFrame, revision: str) -> pd.Series:
    revision_rows = actuals.loc[actuals["actual_revision"].astype(str).eq(str(revision))].copy()
    revision_rows = revision_rows.sort_values("delivery_time_utc").drop_duplicates(
        "delivery_time_utc", keep="last"
    )
    lookup = revision_rows.set_index("delivery_time_utc")["actual_price"].astype(float)
    source_times = revision_rows["delivery_time_utc"] - pd.Timedelta(days=1)
    values = lookup.reindex(source_times).to_numpy()
    return pd.Series(values, index=revision_rows["delivery_time_utc"].to_numpy())


def grade_forecasts(
    forecasts_path: str | Path,
    actuals_path: str | Path,
    scores_path: str | Path,
) -> pd.DataFrame:
    forecasts = _read(forecasts_path)
    actuals = _read(actuals_path)
    if forecasts.empty or actuals.empty:
        return pd.DataFrame()
    forecasts["delivery_time_utc"] = pd.to_datetime(
        forecasts["delivery_time_utc"], utc=True
    )
    forecasts["issue_time_utc"] = pd.to_datetime(forecasts["issue_time_utc"], utc=True)
    actuals["delivery_time_utc"] = pd.to_datetime(actuals["delivery_time_utc"], utc=True)
    actuals["actual_price"] = pd.to_numeric(actuals["actual_price"], errors="coerce")

    persistence_parts: list[pd.DataFrame] = []
    for revision in actuals["actual_revision"].astype(str).unique():
        values = _actual_persistence(actuals, revision)
        part = values.rename("persistence_price").reset_index()
        part.columns = ["delivery_time_utc", "persistence_price"]
        part["actual_revision"] = revision
        persistence_parts.append(part)
    persistence = pd.concat(persistence_parts, ignore_index=True) if persistence_parts else pd.DataFrame()

    joined = forecasts.merge(actuals, on="delivery_time_utc", how="inner")
    if not persistence.empty:
        joined = joined.merge(
            persistence,
            on=["delivery_time_utc", "actual_revision"],
            how="left",
            validate="many_to_one",
        )
    required = {"forecast_id", "actual_revision", "p10", "p50", "p90", "actual_price"}
    missing = required - set(joined)
    if missing:
        raise KeyError(f"Cannot grade forecasts; missing columns: {sorted(missing)}")

    persistence_price = joined.get(
        "persistence_price", pd.Series(np.nan, index=joined.index)
    )
    scores = pd.DataFrame(
        {
            "forecast_id": joined["forecast_id"],
            "model_version": joined["model_version"].astype(str),
            "issue_time_utc": joined["issue_time_utc"],
            "actual_revision": joined["actual_revision"].astype(str),
            "delivery_time_utc": joined["delivery_time_utc"],
            "actual_price": joined["actual_price"],
            "forecast_p50": joined["p50"],
            "error": joined["p50"] - joined["actual_price"],
            "absolute_error": (joined["p50"] - joined["actual_price"]).abs(),
            "squared_error": (joined["p50"] - joined["actual_price"]) ** 2,
            "p10_p90_covered": joined["actual_price"].between(joined["p10"], joined["p90"]),
            "actual_negative": joined["actual_price"] < 0,
            "predicted_negative_probability": joined.get(
                "negative_probability",
                pd.Series(np.nan, index=joined.index),
            ),
            "persistence_price": persistence_price,
            "persistence_absolute_error": (persistence_price - joined["actual_price"]).abs(),
            "graded_at_utc": pd.Timestamp.now(tz="UTC"),
        }
    )
    return _upsert_derived_rows(scores, scores_path, SCORE_KEY)
