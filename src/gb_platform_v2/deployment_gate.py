"""Objective deployment gate for immutable shadow forecasts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


DEFAULT_MIN_DAYS = 30
DEFAULT_MIN_IMPROVEMENT_PERCENT = 5.0
DEFAULT_COVERAGE_MIN = 0.70
DEFAULT_COVERAGE_MAX = 0.90
DEFAULT_MIN_LEAD_HOURS = 8.0


def evaluate_deployment_gate(
    scores_path: str | Path,
    model_version: str,
    output_path: str | Path,
    min_days: int = DEFAULT_MIN_DAYS,
    min_improvement_percent: float = DEFAULT_MIN_IMPROVEMENT_PERCENT,
    coverage_min: float = DEFAULT_COVERAGE_MIN,
    coverage_max: float = DEFAULT_COVERAGE_MAX,
    min_lead_hours: float = DEFAULT_MIN_LEAD_HOURS,
) -> dict:
    path = Path(scores_path)
    if not path.exists():
        scores = pd.DataFrame()
    else:
        scores = pd.read_csv(path)
    if not scores.empty:
        required = {
            "model_version",
            "issue_time_utc",
            "delivery_time_utc",
            "absolute_error",
            "persistence_absolute_error",
            "p10_p90_covered",
        }
        missing = required - set(scores)
        if missing:
            raise KeyError(f"Shadow score store is missing columns: {sorted(missing)}")
        scores = scores.loc[scores["model_version"].astype(str).eq(str(model_version))].copy()

    gates: dict[str, dict] = {}
    if scores.empty:
        metrics = {
            "model_version": model_version,
            "graded_periods": 0,
            "graded_delivery_days": 0,
            "model_mae_gbp_mwh": None,
            "persistence_mae_gbp_mwh": None,
            "improvement_percent": None,
            "p10_p90_coverage": None,
            "minimum_lead_hours": None,
        }
        gates = {
            "minimum_shadow_days": {"passed": False, "required": min_days, "observed": 0},
            "consecutive_delivery_days": {"passed": False, "missing_dates": None},
            "complete_periods": {"passed": False, "missing_periods": None},
            "pre_delivery_issue_time": {"passed": False, "required_hours": min_lead_hours},
            "beats_persistence": {"passed": False, "required_improvement_percent": min_improvement_percent},
            "interval_coverage": {"passed": False, "required_range": [coverage_min, coverage_max]},
        }
    else:
        scores["issue_time_utc"] = pd.to_datetime(scores["issue_time_utc"], utc=True)
        scores["delivery_time_utc"] = pd.to_datetime(scores["delivery_time_utc"], utc=True)
        scores["absolute_error"] = pd.to_numeric(scores["absolute_error"], errors="coerce")
        scores["persistence_absolute_error"] = pd.to_numeric(
            scores["persistence_absolute_error"], errors="coerce"
        )
        coverage_values = scores["p10_p90_covered"].astype(str).str.lower().map(
            {"true": True, "false": False, "1": True, "0": False}
        )
        scores["coverage_bool"] = coverage_values
        scores["delivery_date_local"] = scores["delivery_time_utc"].dt.tz_convert(
            "Europe/London"
        ).dt.date
        scores["lead_hours"] = (
            scores["delivery_time_utc"] - scores["issue_time_utc"]
        ).dt.total_seconds() / 3600.0

        dates = sorted(pd.Timestamp(value) for value in scores["delivery_date_local"].unique())
        observed_days = len(dates)
        expected_dates = (
            pd.date_range(dates[0], dates[-1], freq="D") if dates else pd.DatetimeIndex([])
        )
        missing_dates = sorted(
            date.strftime("%Y-%m-%d")
            for date in expected_dates.difference(pd.DatetimeIndex(dates))
        )

        missing_periods: dict[str, int] = {}
        for day, group in scores.groupby("delivery_date_local"):
            start = pd.Timestamp(day).tz_localize("Europe/London").tz_convert("UTC")
            end = (pd.Timestamp(day) + pd.Timedelta(days=1)).tz_localize(
                "Europe/London"
            ).tz_convert("UTC")
            expected_count = len(pd.date_range(start, end, freq="30min", inclusive="left"))
            actual_count = group["delivery_time_utc"].nunique()
            if actual_count != expected_count:
                missing_periods[str(day)] = int(expected_count - actual_count)

        comparable = scores.dropna(subset=["absolute_error", "persistence_absolute_error"])
        model_mae = float(comparable["absolute_error"].mean()) if not comparable.empty else None
        persistence_mae = (
            float(comparable["persistence_absolute_error"].mean())
            if not comparable.empty
            else None
        )
        improvement = (
            float(100 * (persistence_mae - model_mae) / persistence_mae)
            if persistence_mae not in (None, 0.0) and model_mae is not None
            else None
        )
        coverage = (
            float(scores["coverage_bool"].dropna().mean())
            if scores["coverage_bool"].notna().any()
            else None
        )
        minimum_lead = float(scores["lead_hours"].min())

        metrics = {
            "model_version": model_version,
            "graded_periods": int(len(scores)),
            "comparable_persistence_periods": int(len(comparable)),
            "graded_delivery_days": observed_days,
            "first_delivery_date": dates[0].strftime("%Y-%m-%d") if dates else None,
            "last_delivery_date": dates[-1].strftime("%Y-%m-%d") if dates else None,
            "model_mae_gbp_mwh": model_mae,
            "persistence_mae_gbp_mwh": persistence_mae,
            "improvement_percent": improvement,
            "p10_p90_coverage": coverage,
            "minimum_lead_hours": minimum_lead,
        }
        gates = {
            "minimum_shadow_days": {
                "passed": observed_days >= min_days,
                "required": min_days,
                "observed": observed_days,
            },
            "consecutive_delivery_days": {
                "passed": not missing_dates and observed_days >= min_days,
                "missing_dates": missing_dates,
            },
            "complete_periods": {
                "passed": not missing_periods and observed_days >= min_days,
                "missing_periods": missing_periods,
            },
            "pre_delivery_issue_time": {
                "passed": minimum_lead >= min_lead_hours,
                "required_hours": min_lead_hours,
                "observed_minimum_hours": minimum_lead,
            },
            "beats_persistence": {
                "passed": improvement is not None and improvement >= min_improvement_percent,
                "required_improvement_percent": min_improvement_percent,
                "observed_improvement_percent": improvement,
            },
            "interval_coverage": {
                "passed": coverage is not None and coverage_min <= coverage <= coverage_max,
                "required_range": [coverage_min, coverage_max],
                "observed": coverage,
            },
        }

    ready = all(item["passed"] for item in gates.values())
    report = {
        "workflow_revision": "deployment-gate-v1",
        "deployment_ready": ready,
        "mode": "eligible_for_controlled_operational_review" if ready else "shadow_only",
        "metrics": metrics,
        "gates": gates,
        "warning": (
            "Passing this software gate supports controlled human review; it is not financial advice or an autonomous trading authorisation."
        ),
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate shadow forecast deployment gates")
    parser.add_argument("--scores", default="live/scores.csv")
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--output", default="live/deployment_gate.json")
    parser.add_argument("--min-days", type=int, default=DEFAULT_MIN_DAYS)
    parser.add_argument(
        "--min-improvement-percent", type=float, default=DEFAULT_MIN_IMPROVEMENT_PERCENT
    )
    parser.add_argument("--coverage-min", type=float, default=DEFAULT_COVERAGE_MIN)
    parser.add_argument("--coverage-max", type=float, default=DEFAULT_COVERAGE_MAX)
    parser.add_argument("--min-lead-hours", type=float, default=DEFAULT_MIN_LEAD_HOURS)
    args = parser.parse_args()
    result = evaluate_deployment_gate(
        args.scores,
        args.model_version,
        args.output,
        args.min_days,
        args.min_improvement_percent,
        args.coverage_min,
        args.coverage_max,
        args.min_lead_hours,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
