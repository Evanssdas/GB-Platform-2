"""Combine audited historical workflow artifacts into one modelling source tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import pandas as pd


CRITICAL_STATUS_KEYS = (
    "input_validation",
    "install_test",
    "elexon_core",
    "neso_embedded",
    "neso_inertia",
    "weather_demand",
    "weather_wind",
    "weather_solar",
    "audit",
)

HALF_HOURLY_SOURCES = {
    "elexon/elexon_mid.parquet": "timestamp",
    "elexon/elexon_demand.parquet": "timestamp",
    "elexon/elexon_fuelhh.parquet": "timestamp",
    "elexon/elexon_interconnectors.parquet": "timestamp",
    "neso/inertia.parquet": "timestamp",
}

WEATHER_GROUPS = ("demand", "wind", "solar")


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected a JSON object in {path}")
    return payload


def _date(value: str) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is not None:
        parsed = parsed.tz_convert("UTC").tz_localize(None)
    return parsed.normalize()


def _settlement_boundary_utc(value: str | pd.Timestamp) -> pd.Timestamp:
    day = _date(str(value))
    return day.tz_localize("Europe/London").tz_convert("UTC")


def _expected_half_hours(start: str, end: str) -> pd.DatetimeIndex:
    return pd.date_range(
        _settlement_boundary_utc(start),
        _settlement_boundary_utc(end),
        freq="30min",
        inclusive="left",
    )


def _expected_hours(start: str, end: str) -> pd.DatetimeIndex:
    return pd.date_range(
        _settlement_boundary_utc(start),
        _settlement_boundary_utc(end),
        freq="1h",
        inclusive="left",
    )


def _load_and_validate_artifact(root: Path) -> dict:
    context = _read_json(root / "workflow_context.json")
    status = _read_json(root / "workflow_status.json")
    audit = _read_json(root / "data_audit.json")

    if context.get("workflow_revision") != "historical-v4":
        raise ValueError(
            f"{root} is not a historical-v4 artifact: {context.get('workflow_revision')}"
        )
    failures = {
        key: status.get(key, "missing")
        for key in CRITICAL_STATUS_KEYS
        if status.get(key) != "success"
    }
    if failures:
        raise ValueError(f"Historical artifact {root} has critical failures: {failures}")
    if audit.get("errors"):
        raise ValueError(f"Historical artifact {root} audit errors: {audit['errors']}")

    start = str(context["start_date_inclusive"])
    end = str(context["end_date_exclusive"])
    if _date(end) <= _date(start):
        raise ValueError(f"Invalid artifact window in {root}: [{start}, {end})")
    return {"root": root, "context": context, "start": start, "end": end}


def _ordered_artifacts(
    roots: Iterable[str | Path],
    expected_start: str,
    expected_end: str,
) -> list[dict]:
    artifacts = [_load_and_validate_artifact(Path(root)) for root in roots]
    if not artifacts:
        raise ValueError("At least one historical artifact is required")
    artifacts.sort(key=lambda item: _date(item["start"]))

    if _date(artifacts[0]["start"]) != _date(expected_start):
        raise ValueError(
            f"First artifact starts {artifacts[0]['start']}, expected {expected_start}"
        )
    if _date(artifacts[-1]["end"]) != _date(expected_end):
        raise ValueError(
            f"Last artifact ends {artifacts[-1]['end']}, expected {expected_end}"
        )
    for left, right in zip(artifacts, artifacts[1:]):
        if _date(left["end"]) != _date(right["start"]):
            raise ValueError(
                "Historical artifact windows are not contiguous: "
                f"[{left['start']}, {left['end']}) then "
                f"[{right['start']}, {right['end']})"
            )
    return artifacts


def _read_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_parquet(path)


def _timestamp_frame(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    if "timestamp" not in frame:
        raise KeyError(f"{label} is missing timestamp")
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    if out["timestamp"].isna().any():
        raise ValueError(f"{label} contains invalid timestamps")
    return out.sort_values("timestamp").reset_index(drop=True)


def _assert_identical_duplicate_rows(frame: pd.DataFrame, label: str) -> None:
    duplicate = frame.loc[frame.duplicated("timestamp", keep=False)]
    if duplicate.empty:
        return
    comparison_columns = [column for column in frame.columns if column != "timestamp"]
    for timestamp, group in duplicate.groupby("timestamp", sort=False):
        if comparison_columns and any(
            group[column].astype("string").nunique(dropna=False) > 1
            for column in comparison_columns
        ):
            raise ValueError(f"{label} has conflicting rows at {timestamp}")


def _combine_unique_half_hourly(
    artifacts: list[dict],
    relative_path: str,
    expected: pd.DatetimeIndex,
) -> pd.DataFrame:
    frames = [
        _timestamp_frame(_read_parquet(item["root"] / relative_path), relative_path)
        for item in artifacts
    ]
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.loc[combined["timestamp"].isin(expected)].copy()
    _assert_identical_duplicate_rows(combined, relative_path)
    combined = combined.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
    actual = pd.DatetimeIndex(combined["timestamp"])
    missing = expected.difference(actual)
    extra = actual.difference(expected)
    if len(missing) or len(extra) or len(actual) != len(expected):
        raise ValueError(
            f"{relative_path} does not match the expected half-hour clock: "
            f"rows={len(actual)}, expected={len(expected)}, "
            f"missing={len(missing)}, extra={len(extra)}"
        )
    return combined.reset_index(drop=True)


def _issue_time_for_delivery(timestamp: pd.Series, hour: int, minute: int) -> pd.Series:
    local_delivery = pd.to_datetime(timestamp, utc=True).dt.tz_convert("Europe/London")
    issue_local = (
        local_delivery.dt.normalize()
        - pd.Timedelta(days=1)
        + pd.Timedelta(hours=hour, minutes=minute)
    )
    return issue_local.dt.tz_convert("UTC")


def _validate_missing_embedded_seam_days(
    missing: pd.DatetimeIndex,
    artifacts: list[dict],
) -> tuple[pd.DatetimeIndex, list[str]]:
    """Allow only complete settlement days missing exactly at archive seams.

    NESO annual archives can begin with revisions published after the configured
    D-1 issue time. Those rows cannot be used without leakage. A complete missing
    settlement day at a known artifact boundary is excluded from every training
    source and recorded explicitly. Partial days or non-boundary gaps remain fatal.
    """
    if missing.empty:
        return pd.DatetimeIndex([], tz="UTC"), []

    seam_dates = {_date(item["start"]).date() for item in artifacts[1:]}
    local_dates = pd.DatetimeIndex(missing).tz_convert("Europe/London").date
    excluded_parts: list[pd.DatetimeIndex] = []
    excluded_dates: list[str] = []

    for day in sorted(set(local_dates)):
        day_timestamp = pd.Timestamp(day)
        day_end = day_timestamp + pd.Timedelta(days=1)
        complete_day = _expected_half_hours(
            day_timestamp.strftime("%Y-%m-%d"),
            day_end.strftime("%Y-%m-%d"),
        )
        missing_for_day = missing.intersection(complete_day)
        if day not in seam_dates:
            raise ValueError(
                "Point-in-time embedded forecasts are missing outside an archive seam: "
                f"settlement_date={day}, rows={len(missing_for_day)}"
            )
        if len(missing_for_day) != len(complete_day):
            raise ValueError(
                "Point-in-time embedded forecasts have a partial settlement-day gap: "
                f"settlement_date={day}, missing={len(missing_for_day)}, "
                f"expected_day_rows={len(complete_day)}"
            )
        excluded_parts.append(complete_day)
        excluded_dates.append(day_timestamp.strftime("%Y-%m-%d"))

    excluded = excluded_parts[0]
    for part in excluded_parts[1:]:
        excluded = excluded.union(part)
    if len(excluded) != len(missing) or len(missing.difference(excluded)):
        raise ValueError("Embedded missing-row classification was incomplete")
    return excluded.sort_values(), excluded_dates


def _combine_embedded(
    artifacts: list[dict],
    expected: pd.DatetimeIndex,
    issue_hour: int,
    issue_minute: int,
) -> tuple[pd.DataFrame, int, pd.DatetimeIndex, list[str]]:
    frames = [
        _timestamp_frame(
            _read_parquet(item["root"] / "neso/embedded.parquet"),
            "neso/embedded.parquet",
        )
        for item in artifacts
    ]
    combined = pd.concat(frames, ignore_index=True)
    raw_rows = len(combined)
    if "published_at_utc" not in combined:
        raise KeyError("NESO embedded data are missing published_at_utc")
    combined["published_at_utc"] = pd.to_datetime(
        combined["published_at_utc"], utc=True, errors="coerce"
    )
    combined = combined.dropna(subset=["published_at_utc"])
    combined = combined.loc[combined["timestamp"].isin(expected)].copy()
    combined["selected_issue_time_utc"] = _issue_time_for_delivery(
        combined["timestamp"], issue_hour, issue_minute
    )
    eligible = combined.loc[
        combined["published_at_utc"].le(combined["selected_issue_time_utc"])
    ].copy()
    selected = (
        eligible.sort_values(["timestamp", "published_at_utc"])
        .drop_duplicates("timestamp", keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    actual = pd.DatetimeIndex(selected["timestamp"])
    missing = expected.difference(actual)
    excluded, excluded_dates = _validate_missing_embedded_seam_days(missing, artifacts)
    training_expected = expected.difference(excluded)
    remaining_missing = training_expected.difference(actual)
    extra = actual.difference(training_expected)
    if len(selected) != len(training_expected) or len(remaining_missing) or len(extra):
        raise ValueError(
            "Point-in-time embedded forecasts do not cover the leakage-safe training clock: "
            f"rows={len(selected)}, expected={len(training_expected)}, "
            f"missing={len(remaining_missing)}, extra={len(extra)}"
        )
    if (selected["published_at_utc"] > selected["selected_issue_time_utc"]).any():
        raise ValueError("Future embedded forecast revisions survived selection")
    return selected, raw_rows, excluded, excluded_dates


def _combine_weather(
    artifacts: list[dict],
    group: str,
    expected: pd.DatetimeIndex,
    end_utc: pd.Timestamp,
) -> pd.DataFrame:
    relative_path = f"weather/{group}.parquet"
    frames = [
        _timestamp_frame(_read_parquet(item["root"] / relative_path), relative_path)
        for item in artifacts
    ]
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.loc[combined["timestamp"].isin(expected)].copy()
    _assert_identical_duplicate_rows(combined, relative_path)
    combined = combined.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
    actual = pd.DatetimeIndex(combined["timestamp"])
    missing = expected.difference(actual)
    if len(combined) != len(expected) or len(missing):
        raise ValueError(
            f"{relative_path} does not match the expected hourly clock: "
            f"rows={len(combined)}, expected={len(expected)}, missing={len(missing)}"
        )
    combined = combined.rename(
        columns={
            column: f"weather_{group}_{column}"
            for column in combined.columns
            if column != "timestamp"
        }
    )
    boundary = combined.tail(1).copy()
    boundary["timestamp"] = end_utc
    combined = pd.concat([combined, boundary], ignore_index=True)
    return combined.reset_index(drop=True)


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def prepare_historical_artifacts(
    roots: Iterable[str | Path],
    output_root: str | Path,
    expected_start: str,
    expected_end: str,
    issue_hour: int = 13,
    issue_minute: int = 0,
    summary_path: str | Path | None = None,
) -> dict:
    """Validate and combine contiguous historical-v4 artifacts.

    The output layout matches ``config/data_mapping_core.yaml``. Embedded
    forecasts are reduced to the latest revision available by the configured D-1
    issue time. Complete unavailable settlement days at annual archive seams are
    excluded from every half-hourly source rather than filled with future data.
    """
    if not (0 <= issue_hour <= 23 and 0 <= issue_minute <= 59):
        raise ValueError("Invalid issue time")
    artifacts = _ordered_artifacts(roots, expected_start, expected_end)
    output = Path(output_root)
    full_expected_half_hours = _expected_half_hours(expected_start, expected_end)
    expected_hours = _expected_hours(expected_start, expected_end)
    end_utc = _settlement_boundary_utc(expected_end)

    embedded, embedded_raw_rows, excluded, excluded_dates = _combine_embedded(
        artifacts,
        full_expected_half_hours,
        issue_hour,
        issue_minute,
    )
    training_expected_half_hours = full_expected_half_hours.difference(excluded)

    source_rows: dict[str, int] = {}
    for relative_path in HALF_HOURLY_SOURCES:
        frame = _combine_unique_half_hourly(
            artifacts, relative_path, training_expected_half_hours
        )
        _write_frame(frame, output / relative_path)
        source_rows[relative_path] = len(frame)

    _write_frame(embedded, output / "neso/embedded.parquet")
    source_rows["neso/embedded.parquet"] = len(embedded)

    for group in WEATHER_GROUPS:
        weather = _combine_weather(artifacts, group, expected_hours, end_utc)
        _write_frame(weather, output / f"weather/{group}.parquet")
        source_rows[f"weather/{group}.parquet"] = len(weather)

    entsoe_paths = [item["root"] / "entsoe/neighbour_prices.parquet" for item in artifacts]
    if all(path.exists() for path in entsoe_paths):
        entsoe = pd.concat(
            [_timestamp_frame(_read_parquet(path), str(path)) for path in entsoe_paths],
            ignore_index=True,
        )
        entsoe = (
            entsoe.loc[entsoe["timestamp"].isin(training_expected_half_hours)]
            .drop_duplicates("timestamp", keep="last")
            .sort_values("timestamp")
            .reset_index(drop=True)
        )
        _write_frame(entsoe, output / "entsoe/neighbour_prices.parquet")
        source_rows["entsoe/neighbour_prices.parquet"] = len(entsoe)

    summary = {
        "workflow_revision": "history-artifact-merge-v2",
        "expected_start_date_inclusive": expected_start,
        "expected_end_date_exclusive": expected_end,
        "settlement_start_utc": full_expected_half_hours.min().isoformat(),
        "settlement_end_utc_exclusive": end_utc.isoformat(),
        "full_calendar_half_hour_rows": len(full_expected_half_hours),
        "training_half_hour_rows": len(training_expected_half_hours),
        "expected_hour_rows": len(expected_hours),
        "artifact_run_ids": [
            str(item["context"].get("run_id", "unknown")) for item in artifacts
        ],
        "artifact_windows": [
            {"start": item["start"], "end": item["end"]} for item in artifacts
        ],
        "issue_time_local": f"{issue_hour:02d}:{issue_minute:02d}",
        "embedded_raw_revision_rows": embedded_raw_rows,
        "embedded_selected_rows": len(embedded),
        "excluded_settlement_dates_local": excluded_dates,
        "excluded_half_hour_rows": len(excluded),
        "exclusion_reason": (
            "No embedded forecast revision existed by the configured D-1 issue time "
            "at an annual NESO archive seam; the complete settlement day was removed "
            "from every training source to prevent leakage."
            if excluded_dates
            else None
        ),
        "weather_boundary_policy": "carry final hourly forecast to exclusive end boundary",
        "source_rows": source_rows,
    }
    target = Path(summary_path) if summary_path else output / "history_merge_summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine audited historical-v4 artifacts for production-candidate training"
    )
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--issue-hour", type=int, default=13)
    parser.add_argument("--issue-minute", type=int, default=0)
    parser.add_argument("--summary")
    args = parser.parse_args()
    summary = prepare_historical_artifacts(
        args.inputs,
        args.output,
        args.start,
        args.end,
        args.issue_hour,
        args.issue_minute,
        args.summary,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
