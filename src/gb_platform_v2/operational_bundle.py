"""Prepare a leakage-safe operational bundle from a production candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


OPERATIONAL_FALLBACK_TARGETS = {"demand_mw", "nuclear_mw"}
FALLBACK_LAG = pd.Timedelta(days=7)


def _load_dataset(path: str | Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    if "timestamp" not in frame:
        raise KeyError("Production dataset is missing timestamp")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    return frame.set_index("timestamp", drop=False).sort_index()


def _lagged_series(series: pd.Series, lag: pd.Timedelta = FALLBACK_LAG) -> pd.Series:
    """Return the observed value at the exact UTC timestamp minus ``lag``."""
    source_index = series.index - lag
    lagged = series.reindex(source_index)
    lagged.index = series.index
    return lagged.astype(float)


def _mae(actual: pd.Series, predicted: pd.Series) -> tuple[float, int]:
    valid = actual.notna() & predicted.notna()
    if not valid.any():
        return float("nan"), 0
    return float(np.mean(np.abs(actual.loc[valid] - predicted.loc[valid]))), int(valid.sum())


def _normalise_error_index(errors: pd.DataFrame) -> pd.DataFrame:
    out = errors.copy()
    if isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, utc=True)
        return out.sort_index()
    for candidate in ("timestamp", "index"):
        if candidate in out:
            parsed = pd.to_datetime(out[candidate], utc=True, errors="coerce")
            if parsed.notna().all():
                out = out.drop(columns=[candidate])
                out.index = pd.DatetimeIndex(parsed)
                return out.sort_index()
    raise ValueError("Historical component errors do not have a timestamp index")


def prepare_operational_bundle(
    dataset_path: str | Path,
    model_dir: str | Path,
    holdout_rows: int = 4320,
    summary_path: str | Path | None = None,
) -> dict:
    """Select operationally available component sources and error distributions.

    Component models remain the default. Demand and nuclear may switch to exact
    seven-day persistence when it beats the model on the production candidate's
    chronological holdout. Seven-day persistence is fully observable at a D-1
    issue time, unlike a complete D-1 profile whose afternoon periods are not yet
    known at 13:00 local.
    """
    model_root = Path(model_dir)
    metadata_path = model_root / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    frame = _load_dataset(dataset_path)
    targets = list(metadata.get("component_targets", []))
    if not targets:
        raise ValueError("Model metadata contain no component targets")
    if holdout_rows <= 0 or holdout_rows >= len(frame):
        raise ValueError("holdout_rows must be between zero and dataset length")

    model_errors = _normalise_error_index(
        pd.read_parquet(model_root / "historical_component_errors.parquet")
    )
    holdout = frame.iloc[-holdout_rows:]
    strategy: dict[str, dict] = {}
    operational_errors = pd.DataFrame(index=frame.index)

    for target in targets:
        if target not in frame:
            raise KeyError(f"Production dataset is missing target {target}")
        model_metric = metadata.get("metrics", {}).get(target, {})
        model_mae = float(model_metric.get("model_mae", np.nan))
        source = "model"
        selected_mae = model_mae
        fallback_mae = float("nan")
        fallback_rows = 0

        lagged = _lagged_series(frame[target])
        if target in OPERATIONAL_FALLBACK_TARGETS:
            fallback_mae, fallback_rows = _mae(
                holdout[target], lagged.reindex(holdout.index)
            )
            if np.isfinite(fallback_mae) and (
                not np.isfinite(model_mae) or fallback_mae < model_mae
            ):
                source = "fallback_d7"
                selected_mae = fallback_mae

        if source == "fallback_d7":
            operational_errors[target] = frame[target].astype(float) - lagged
        else:
            if target not in model_errors:
                raise KeyError(f"Historical model errors are missing target {target}")
            operational_errors[target] = model_errors[target].reindex(frame.index)

        strategy[target] = {
            "source": source,
            "model_holdout_mae": model_mae,
            "fallback_d7_holdout_mae": fallback_mae,
            "fallback_comparison_rows": fallback_rows,
            "selected_holdout_mae": selected_mae,
            "fallback_definition": (
                "observed target at exact timestamp minus 168 hours"
                if target in OPERATIONAL_FALLBACK_TARGETS
                else None
            ),
        }

    complete_errors = operational_errors.dropna(subset=targets, how="any")
    if len(complete_errors) < 500:
        raise ValueError(
            f"Operational error history is too short: {len(complete_errors)} complete rows"
        )
    error_path = model_root / "operational_component_errors.parquet"
    complete_errors.to_parquet(error_path)

    metadata["operational_bundle_ready"] = True
    metadata["operational_component_strategy"] = strategy
    metadata["component_error_file"] = error_path.name
    metadata["operational_fallback_policy"] = {
        "eligible_targets": sorted(OPERATIONAL_FALLBACK_TARGETS),
        "lag_hours": int(FALLBACK_LAG / pd.Timedelta(hours=1)),
        "selection_rule": "choose D-7 only when its chronological holdout MAE beats the component model",
        "issue_time_compatibility": "fully observable before D-1 13:00 local issue time",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    summary = {
        "workflow_revision": "operational-bundle-v1",
        "model_profile": metadata.get("model_profile"),
        "training_rows": int(len(frame)),
        "holdout_rows": int(holdout_rows),
        "component_strategy": strategy,
        "operational_error_rows": int(len(complete_errors)),
        "component_error_file": error_path.name,
        "ready_for_shadow_forecasting": True,
        "ready_for_operational_deployment": False,
    }
    target_path = Path(summary_path) if summary_path else model_root / "operational_bundle.json"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare an operational hybrid model bundle")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--models", required=True)
    parser.add_argument("--holdout-rows", type=int, default=4320)
    parser.add_argument("--summary")
    args = parser.parse_args()
    result = prepare_operational_bundle(
        args.dataset,
        args.models,
        args.holdout_rows,
        args.summary,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
