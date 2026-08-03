#!/usr/bin/env python3
"""Check whether a GB daily forecast and its report archive are complete.

This script intentionally uses only the Python standard library so it can run
before project dependencies are installed in GitHub Actions.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

GB_TZ = ZoneInfo("Europe/London")
REQUIRED_REPORT_FILES = (
    "report.md",
    "report.json",
    "half_hourly_system_and_price_table.csv",
    "daily_system_summary.csv",
    "var_and_position_limits.csv",
    "plots/01_system_components.png",
    "plots/02_residual_demand.png",
    "plots/03_wind_solar_breakdown.png",
    "plots/04_net_imports_and_inertia.png",
    "plots/05_price_fan.png",
    "plots/06_negative_price_probability.png",
    "plots/07_risk_position_limits.png",
)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _gb_window(delivery_date: str) -> set[datetime]:
    day = date.fromisoformat(delivery_date)
    start_local = datetime.combine(day, datetime.min.time(), tzinfo=GB_TZ)
    end_local = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=GB_TZ)
    current = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    expected: set[datetime] = set()
    while current < end_utc:
        expected.add(current)
        current += timedelta(minutes=30)
    return expected


def _forecast_status(
    forecasts_path: Path,
    delivery_date: str,
    model_version: str,
) -> tuple[bool, int, str]:
    expected = _gb_window(delivery_date)
    if not forecasts_path.exists() or forecasts_path.stat().st_size == 0:
        return False, 0, ""

    selected_times: set[datetime] = set()
    issue_times: set[str] = set()
    with forecasts_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"model_version", "issue_time_utc", "delivery_time_utc"}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise SystemExit(f"Forecast log is missing required columns: {sorted(missing)}")
        for row in reader:
            if str(row["model_version"]) != str(model_version):
                continue
            delivery_utc = _parse_utc(row["delivery_time_utc"])
            if delivery_utc.astimezone(GB_TZ).date().isoformat() != delivery_date:
                continue
            selected_times.add(delivery_utc)
            issue_times.add(_parse_utc(row["issue_time_utc"]).isoformat())

    periods = len(selected_times)
    if periods and selected_times != expected:
        missing = len(expected - selected_times)
        extra = len(selected_times - expected)
        raise SystemExit(
            "Stored forecast day is incomplete or misaligned: "
            f"delivery_date={delivery_date}, periods={periods}, expected={len(expected)}, "
            f"missing={missing}, extra={extra}"
        )
    if len(issue_times) > 1:
        raise SystemExit(
            "Stored forecast day has multiple issue timestamps: "
            f"delivery_date={delivery_date}, issue_times={sorted(issue_times)}"
        )
    issue_time = next(iter(issue_times), "")
    return selected_times == expected, periods, issue_time


def _report_status(logs_root: Path, delivery_date: str) -> tuple[bool, str]:
    day_root = logs_root / "daily" / delivery_date
    if not (day_root / "README.md").is_file():
        return False, ""
    complete_reports: list[Path] = []
    for report_dir in sorted(day_root.glob("market-report-run-*")):
        if report_dir.is_dir() and all(
            (report_dir / relative).is_file() for relative in REQUIRED_REPORT_FILES
        ):
            complete_reports.append(report_dir)
    if not complete_reports:
        return False, ""
    return True, complete_reports[-1].name


def check_archive(
    delivery_date: str,
    model_version: str,
    forecasts_path: Path,
    logs_root: Path,
    requested_issue_time_utc: str,
) -> dict[str, object]:
    forecast_complete, periods, original_issue = _forecast_status(
        forecasts_path, delivery_date, model_version
    )
    report_complete, report_directory = _report_status(logs_root, delivery_date)
    effective_issue = original_issue or _parse_utc(requested_issue_time_utc).isoformat()
    return {
        "delivery_date": delivery_date,
        "forecast_periods": periods,
        "forecast_complete": forecast_complete,
        "report_complete": report_complete,
        "already_archived": forecast_complete and report_complete,
        "original_issue_time_utc": original_issue,
        "effective_issue_time_utc": effective_issue,
        "report_directory": report_directory,
    }


def _write_github_output(path: str, status: dict[str, object]) -> None:
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(f"complete={str(status['already_archived']).lower()}\n")
        handle.write(f"forecast_exists={str(status['forecast_complete']).lower()}\n")
        handle.write(f"report_exists={str(status['report_complete']).lower()}\n")
        handle.write(f"effective_issue_time_utc={status['effective_issue_time_utc']}\n")
        handle.write(f"original_issue_time_utc={status['original_issue_time_utc']}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delivery-date", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--forecasts", default="live/forecasts.csv")
    parser.add_argument("--logs-root", default="logs")
    parser.add_argument("--requested-issue-time-utc", required=True)
    parser.add_argument("--github-output", default="")
    args = parser.parse_args()
    status = check_archive(
        args.delivery_date,
        args.model_version,
        Path(args.forecasts),
        Path(args.logs_root),
        args.requested_issue_time_utc,
    )
    _write_github_output(args.github_output, status)
    print(json.dumps(status, sort_keys=True))


if __name__ == "__main__":
    main()
