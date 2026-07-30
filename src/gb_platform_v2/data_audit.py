"""Audit parsed market datasets before they are joined or used for training."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _read(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(path)


def _serialise(value: object) -> object:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    return value


def audit_frame(path: Path, root: Path) -> dict[str, object]:
    frame = _read(path)
    result: dict[str, object] = {
        "path": str(path.relative_to(root)),
        "format": path.suffix.lstrip("."),
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "column_count": int(len(frame.columns)),
        "duplicate_rows": int(frame.duplicated().sum()),
        "null_counts": {
            str(column): int(count)
            for column, count in frame.isna().sum().items()
            if int(count) > 0
        },
        "dtypes": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
    }

    timestamp_column = next(
        (
            candidate
            for candidate in (
                "timestamp",
                "delivery_time_utc",
                "published_at_utc",
                "settlement_date",
            )
            if candidate in frame.columns
        ),
        None,
    )
    if timestamp_column:
        timestamps = pd.to_datetime(frame[timestamp_column], utc=True, errors="coerce")
        valid = timestamps.dropna()
        result["timestamp_column"] = timestamp_column
        result["invalid_timestamps"] = int(timestamps.isna().sum())
        if not valid.empty:
            result["timestamp_min"] = valid.min().isoformat()
            result["timestamp_max"] = valid.max().isoformat()
            result["duplicate_timestamps"] = int(valid.duplicated().sum())

    if not frame.empty:
        sample = frame.head(2).copy()
        result["sample"] = [
            {str(key): _serialise(value) for key, value in row.items()}
            for row in sample.to_dict(orient="records")
        ]
    return result


def audit_directory(input_dir: str | Path, output_path: str | Path) -> dict[str, object]:
    root = Path(input_dir)
    output = Path(output_path)
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".parquet", ".csv"}
    )
    datasets: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for path in files:
        try:
            datasets.append(audit_frame(path, root))
        except Exception as error:  # Keep the audit useful even if one file is malformed.
            errors.append(
                {
                    "path": str(path.relative_to(root)),
                    "error_type": type(error).__name__,
                    "message": " ".join(str(error).split())[:500],
                }
            )

    report = {
        "input_directory": str(root),
        "dataset_count": len(datasets),
        "error_count": len(errors),
        "datasets": datasets,
        "errors": errors,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit collected market data")
    parser.add_argument("--input", default="data/parsed")
    parser.add_argument("--output", default="data/parsed/data_audit.json")
    args = parser.parse_args()
    report = audit_directory(args.input, args.output)
    print(
        {
            "datasets": report["dataset_count"],
            "errors": report["error_count"],
            "output": args.output,
        }
    )


if __name__ == "__main__":
    main()
