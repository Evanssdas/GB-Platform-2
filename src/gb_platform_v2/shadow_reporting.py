"""Publish permanent, human-readable shadow forecast and risk records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


RISK_KEYS = ("scenario_var", "expected_shortfall", "worst_loss", "best_profit")
RISK_LOG_KEY = ["model_version", "issue_time_utc", "delivery_date"]


def _read_json(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected a JSON object in {path}")
    return payload


def _normalise_log(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if not out.empty:
        out["model_version"] = out["model_version"].astype(str)
        out["issue_time_utc"] = pd.to_datetime(
            out["issue_time_utc"], utc=True, errors="raise"
        ).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        out["delivery_date"] = pd.to_datetime(
            out["delivery_date"], errors="raise"
        ).dt.strftime("%Y-%m-%d")
    return out


def publish_shadow_report(
    daily_report_path: str | Path,
    feature_summary_path: str | Path,
    reports_root: str | Path,
    risk_log_path: str | Path,
    model_version: str,
    issue_time_utc: str,
    delivery_date: str,
    run_id: str,
    run_attempt: str,
    scenarios: int,
) -> dict:
    """Write one immutable daily report and append its summary to the risk log."""
    report = _read_json(daily_report_path)
    features = _read_json(feature_summary_path)
    risk = report.get("risk")
    if not isinstance(risk, dict):
        raise KeyError("Daily report is missing risk")
    missing_risk = [key for key in RISK_KEYS if key not in risk]
    if missing_risk:
        raise KeyError(f"Daily report is missing risk values: {missing_risk}")

    issue = pd.Timestamp(issue_time_utc)
    issue = issue.tz_localize("UTC") if issue.tzinfo is None else issue.tz_convert("UTC")
    delivery = pd.Timestamp(delivery_date).normalize()
    payload = {
        "workflow_revision": "shadow-risk-report-v1",
        "model_version": str(model_version),
        "delivery_date": delivery.strftime("%Y-%m-%d"),
        "issue_time_utc": issue.isoformat(),
        "github_run_id": str(run_id),
        "github_run_attempt": str(run_attempt),
        "monte_carlo_scenarios": int(scenarios),
        "position_mwh": 100.0,
        "confidence_level": 0.95,
        "period_count": int(report["period_count"]),
        "expected_period_count": int(features["expected_period_count"]),
        "p50_daily_min_gbp_mwh": float(report["p50_daily_min_gbp_mwh"]),
        "p50_daily_max_gbp_mwh": float(report["p50_daily_max_gbp_mwh"]),
        "p50_daily_mean_gbp_mwh": float(report["p50_daily_mean_gbp_mwh"]),
        "probability_any_negative_period": float(
            report["probability_any_negative_period"]
        ),
        "component_sources": report.get("component_sources", {}),
        "component_point_values_clipped_at_zero": report.get(
            "component_point_values_clipped_at_zero", {}
        ),
        "risk_gbp": {key: float(risk[key]) for key in RISK_KEYS},
        "source_artifact_path": "outputs/shadow/forecast/daily_report.json",
    }
    if payload["period_count"] != payload["expected_period_count"]:
        raise ValueError("Daily risk report does not cover the complete settlement day")

    report_path = (
        Path(reports_root)
        / payload["delivery_date"]
        / f"run-{run_id}-attempt-{run_attempt}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists():
        existing = _read_json(report_path)
        if existing != payload:
            raise ValueError(f"Refusing to replace immutable daily report {report_path}")
    else:
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    row = {
        "model_version": payload["model_version"],
        "issue_time_utc": issue.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "delivery_date": payload["delivery_date"],
        "github_run_id": payload["github_run_id"],
        "github_run_attempt": payload["github_run_attempt"],
        "monte_carlo_scenarios": payload["monte_carlo_scenarios"],
        "position_mwh": payload["position_mwh"],
        "confidence_level": payload["confidence_level"],
        "period_count": payload["period_count"],
        "p50_daily_min_gbp_mwh": payload["p50_daily_min_gbp_mwh"],
        "p50_daily_max_gbp_mwh": payload["p50_daily_max_gbp_mwh"],
        "p50_daily_mean_gbp_mwh": payload["p50_daily_mean_gbp_mwh"],
        "probability_any_negative_period": payload[
            "probability_any_negative_period"
        ],
        **{f"{key}_gbp": payload["risk_gbp"][key] for key in RISK_KEYS},
        "report_path": report_path.as_posix(),
    }
    log_path = Path(risk_log_path)
    existing_log = pd.read_csv(log_path) if log_path.exists() else pd.DataFrame()
    existing_log = _normalise_log(existing_log)
    incoming = _normalise_log(pd.DataFrame([row]))
    if not existing_log.empty:
        existing_keys = set(
            map(tuple, existing_log[RISK_LOG_KEY].itertuples(index=False, name=None))
        )
        incoming_key = tuple(incoming.loc[0, RISK_LOG_KEY])
        if incoming_key in existing_keys:
            existing_row = existing_log.loc[
                existing_log[RISK_LOG_KEY].eq(pd.Series(incoming_key, index=RISK_LOG_KEY)).all(axis=1)
            ]
            comparison = incoming.astype(str).reset_index(drop=True)
            common = [column for column in comparison if column in existing_row]
            if not existing_row[common].astype(str).reset_index(drop=True).equals(
                comparison[common]
            ):
                raise ValueError(f"Conflicting immutable risk-log row: {incoming_key}")
            return payload
    combined = pd.concat([existing_log, incoming], ignore_index=True)
    combined = combined.sort_values(["delivery_date", "issue_time_utc"]).reset_index(drop=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(log_path, index=False)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish permanent shadow risk evidence")
    parser.add_argument("--daily-report", required=True)
    parser.add_argument("--feature-summary", required=True)
    parser.add_argument("--reports-root", default="live/reports")
    parser.add_argument("--risk-log", default="live/risk_log.csv")
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--issue-time-utc", required=True)
    parser.add_argument("--delivery-date", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--scenarios", type=int, required=True)
    args = parser.parse_args()
    result = publish_shadow_report(
        args.daily_report,
        args.feature_summary,
        args.reports_root,
        args.risk_log,
        args.model_version,
        args.issue_time_utc,
        args.delivery_date,
        args.run_id,
        args.run_attempt,
        args.scenarios,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
