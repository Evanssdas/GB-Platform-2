"""Create easy-to-review forecast, risk and grading logs.

The append-only ``live`` files remain the source of truth. This module maintains a
compact review layer under ``logs`` with one daily summary table, permanent JSON
records and a generated Markdown dashboard.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SUMMARY_COLUMNS = [
    "delivery_date",
    "model_version",
    "forecast_issue_time_utc",
    "forecast_run_id",
    "period_count",
    "monte_carlo_scenarios",
    "p50_min_gbp_mwh",
    "p50_mean_gbp_mwh",
    "p50_max_gbp_mwh",
    "probability_any_negative_period",
    "scenario_var_gbp",
    "expected_shortfall_gbp",
    "worst_loss_gbp",
    "best_profit_gbp",
    "actual_revision",
    "actual_periods",
    "graded_periods",
    "model_mae_gbp_mwh",
    "model_rmse_gbp_mwh",
    "model_bias_gbp_mwh",
    "persistence_mae_gbp_mwh",
    "improvement_percent",
    "p10_p90_coverage",
    "actual_negative_periods",
    "deployment_ready",
    "deployment_mode",
    "graded_delivery_days_total",
    "deployment_improvement_percent",
]

FORECAST_HISTORY_KEY = ["model_version", "forecast_issue_time_utc", "delivery_date"]
GRADING_HISTORY_KEY = ["model_version", "delivery_date", "actual_revision"]


def _read_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object in {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any], *, immutable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists():
        existing = _read_json(path)
        if existing != payload:
            raise ValueError(f"Refusing to replace immutable review log {path}")
        return
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _normalise_date(value: str | pd.Timestamp) -> str:
    return pd.Timestamp(value).tz_localize(None).normalize().strftime("%Y-%m-%d")


def _normalise_utc(value: str | pd.Timestamp) -> str:
    parsed = pd.Timestamp(value)
    parsed = parsed.tz_localize("UTC") if parsed.tzinfo is None else parsed.tz_convert("UTC")
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def _upsert_history(
    path: Path,
    row: dict[str, Any],
    key: list[str],
    *,
    replace_existing: bool = False,
) -> pd.DataFrame:
    existing = _read_csv(path)
    incoming = pd.DataFrame([row])
    if existing.empty:
        combined = incoming
    else:
        missing = [column for column in key if column not in existing or column not in incoming]
        if missing:
            raise KeyError(f"History key columns are missing: {missing}")
        existing_key = existing[key].astype(str).agg("|".join, axis=1)
        incoming_key = incoming[key].astype(str).agg("|".join, axis=1).iloc[0]
        matched = existing_key.eq(incoming_key)
        if matched.any():
            if not replace_existing:
                old = existing.loc[matched].reset_index(drop=True).astype(str)
                common = [column for column in incoming if column in old]
                if not old[common].equals(incoming[common].astype(str)):
                    raise ValueError(f"Conflicting immutable history row in {path}: {incoming_key}")
                return existing
            existing = existing.loc[~matched]
        combined = pd.concat([existing, incoming], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(path, index=False)
    return combined


def _update_daily_summary(root: Path, delivery_date: str, values: dict[str, Any]) -> pd.DataFrame:
    path = root / "daily_summary.csv"
    frame = _read_csv(path)
    if frame.empty:
        frame = pd.DataFrame(columns=SUMMARY_COLUMNS)
    for column in SUMMARY_COLUMNS:
        if column not in frame:
            frame[column] = np.nan
    matched = frame["delivery_date"].astype(str).eq(delivery_date)
    if not matched.any():
        frame = pd.concat(
            [frame, pd.DataFrame([{column: np.nan for column in SUMMARY_COLUMNS}])],
            ignore_index=True,
        )
        matched = frame.index == frame.index[-1]
        frame.loc[matched, "delivery_date"] = delivery_date
    for key, value in values.items():
        if key not in frame:
            frame[key] = np.nan
        frame.loc[matched, key] = value
    frame = frame[SUMMARY_COLUMNS].sort_values("delivery_date").reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def _fmt(value: Any, decimals: int = 2, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "—"
    try:
        return f"{float(value):,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def _markdown_dashboard(root: Path) -> None:
    summary = _read_csv(root / "daily_summary.csv")
    forecasts = _read_csv(root / "forecast_history.csv")
    gradings = _read_csv(root / "grading_history.csv")
    gate = _read_json(root / "latest_deployment_gate.json") if (root / "latest_deployment_gate.json").exists() else {}

    lines = [
        "# GB Platform Review Logs",
        "",
        "This folder is the human-readable review layer. The append-only files under `live/` remain the raw source of truth.",
        "",
        "## Current deployment gate",
        "",
    ]
    if gate:
        metrics = gate.get("metrics", {})
        lines.extend(
            [
                f"- **Mode:** `{gate.get('mode', 'unknown')}`",
                f"- **Deployment ready:** `{gate.get('deployment_ready', False)}`",
                f"- **Graded days:** {_fmt(metrics.get('graded_delivery_days'), 0)} / 30",
                f"- **Model MAE:** {_fmt(metrics.get('model_mae_gbp_mwh'))} GBP/MWh",
                f"- **Persistence MAE:** {_fmt(metrics.get('persistence_mae_gbp_mwh'))} GBP/MWh",
                f"- **Improvement:** {_fmt(metrics.get('improvement_percent'))}%",
                f"- **P10–P90 coverage:** {_fmt(metrics.get('p10_p90_coverage'), 3)}",
                "",
            ]
        )
    else:
        lines.extend(["No deployment-gate snapshot has been registered yet.", ""])

    lines.extend(["## Latest daily results", ""])
    if summary.empty:
        lines.extend(["No daily records yet.", ""])
    else:
        recent = summary.sort_values("delivery_date", ascending=False).head(14)
        lines.extend(
            [
                "| Delivery date | P50 mean | VaR | Expected shortfall | Model MAE | Persistence MAE | Improvement | Coverage |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for _, row in recent.iterrows():
            lines.append(
                "| {date} | {p50} | {var} | {es} | {mae} | {base} | {imp} | {cov} |".format(
                    date=row.get("delivery_date", "—"),
                    p50=_fmt(row.get("p50_mean_gbp_mwh")),
                    var=_fmt(row.get("scenario_var_gbp")),
                    es=_fmt(row.get("expected_shortfall_gbp")),
                    mae=_fmt(row.get("model_mae_gbp_mwh")),
                    base=_fmt(row.get("persistence_mae_gbp_mwh")),
                    imp=_fmt(row.get("improvement_percent"), suffix="%"),
                    cov=_fmt(row.get("p10_p90_coverage"), 3),
                )
            )
        lines.append("")

    lines.extend(
        [
            "## Files",
            "",
            "- [`daily_summary.csv`](daily_summary.csv): one row per delivery date, updated after grading.",
            "- [`forecast_history.csv`](forecast_history.csv): append-only daily forecast and risk history.",
            "- [`grading_history.csv`](grading_history.csv): append-only grading history.",
            "- [`latest_forecast.json`](latest_forecast.json): latest forecast review snapshot.",
            "- [`latest_grading.json`](latest_grading.json): latest grading review snapshot.",
            "- [`latest_deployment_gate.json`](latest_deployment_gate.json): latest deployment-gate state.",
            "- [`daily/`](daily): permanent detailed JSON records grouped by delivery date.",
            "",
            f"Registered forecast runs: **{len(forecasts)}**  ",
            f"Registered grading runs: **{len(gradings)}**",
            "",
        ]
    )
    (root / "README.md").write_text("\n".join(lines), encoding="utf-8")


def register_forecast(
    logs_root: str | Path,
    daily_report_path: str | Path,
    feature_summary_path: str | Path,
    price_forecast_path: str | Path,
    system_forecast_path: str | Path,
    model_version: str,
    delivery_date: str,
    issue_time_utc: str,
    run_id: str,
    run_attempt: str,
    scenarios: int,
) -> dict[str, Any]:
    root = Path(logs_root)
    root.mkdir(parents=True, exist_ok=True)
    report = _read_json(daily_report_path)
    features = _read_json(feature_summary_path)
    prices = pd.read_csv(price_forecast_path)
    system = pd.read_csv(system_forecast_path)
    risk = report.get("risk", {})
    required_risk = {"scenario_var", "expected_shortfall", "worst_loss", "best_profit"}
    if not required_risk.issubset(risk):
        raise KeyError(f"Forecast report is missing risk values: {sorted(required_risk - set(risk))}")

    delivery = _normalise_date(delivery_date)
    issue = _normalise_utc(issue_time_utc)
    expected_periods = int(features["expected_period_count"])
    if len(prices) != expected_periods or len(system) != expected_periods:
        raise ValueError("Forecast review inputs do not cover the complete settlement day")

    payload = {
        "workflow_revision": "review-forecast-v1",
        "delivery_date": delivery,
        "model_version": str(model_version),
        "issue_time_utc": issue,
        "github_run_id": str(run_id),
        "github_run_attempt": str(run_attempt),
        "monte_carlo_scenarios": int(scenarios),
        "feature_summary": features,
        "daily_report": report,
        "price_forecast_rows": int(len(prices)),
        "system_forecast_rows": int(len(system)),
    }
    detail_path = root / "daily" / delivery / f"forecast-run-{run_id}-attempt-{run_attempt}.json"
    _write_json(detail_path, payload, immutable=True)
    _write_json(root / "latest_forecast.json", payload)

    history_row = {
        "delivery_date": delivery,
        "model_version": str(model_version),
        "forecast_issue_time_utc": issue,
        "github_run_id": str(run_id),
        "github_run_attempt": str(run_attempt),
        "period_count": int(report["period_count"]),
        "monte_carlo_scenarios": int(scenarios),
        "p50_min_gbp_mwh": float(report["p50_daily_min_gbp_mwh"]),
        "p50_mean_gbp_mwh": float(report["p50_daily_mean_gbp_mwh"]),
        "p50_max_gbp_mwh": float(report["p50_daily_max_gbp_mwh"]),
        "probability_any_negative_period": float(report["probability_any_negative_period"]),
        "scenario_var_gbp": float(risk["scenario_var"]),
        "expected_shortfall_gbp": float(risk["expected_shortfall"]),
        "worst_loss_gbp": float(risk["worst_loss"]),
        "best_profit_gbp": float(risk["best_profit"]),
        "component_sources": json.dumps(report.get("component_sources", {}), sort_keys=True),
        "detail_path": detail_path.as_posix(),
    }
    _upsert_history(root / "forecast_history.csv", history_row, FORECAST_HISTORY_KEY)
    _update_daily_summary(
        root,
        delivery,
        {
            "model_version": str(model_version),
            "forecast_issue_time_utc": issue,
            "forecast_run_id": str(run_id),
            "period_count": int(report["period_count"]),
            "monte_carlo_scenarios": int(scenarios),
            "p50_min_gbp_mwh": float(report["p50_daily_min_gbp_mwh"]),
            "p50_mean_gbp_mwh": float(report["p50_daily_mean_gbp_mwh"]),
            "p50_max_gbp_mwh": float(report["p50_daily_max_gbp_mwh"]),
            "probability_any_negative_period": float(report["probability_any_negative_period"]),
            "scenario_var_gbp": float(risk["scenario_var"]),
            "expected_shortfall_gbp": float(risk["expected_shortfall"]),
            "worst_loss_gbp": float(risk["worst_loss"]),
            "best_profit_gbp": float(risk["best_profit"]),
        },
    )
    _markdown_dashboard(root)
    return payload


def _bool_mean(series: pd.Series) -> float | None:
    if series.empty:
        return None
    values = series.astype(str).str.lower().map({"true": 1.0, "false": 0.0, "1": 1.0, "0": 0.0})
    return float(values.dropna().mean()) if values.notna().any() else None


def register_grading(
    logs_root: str | Path,
    actuals_path: str | Path,
    scores_path: str | Path,
    deployment_gate_path: str | Path,
    model_version: str,
    delivery_date: str,
    run_id: str,
    run_attempt: str,
    actual_revision: str = "initial",
) -> dict[str, Any]:
    root = Path(logs_root)
    root.mkdir(parents=True, exist_ok=True)
    delivery = _normalise_date(delivery_date)
    actuals = pd.read_csv(actuals_path)
    actuals["delivery_time_utc"] = pd.to_datetime(actuals["delivery_time_utc"], utc=True)
    actuals["delivery_date_local"] = actuals["delivery_time_utc"].dt.tz_convert("Europe/London").dt.date.astype(str)
    actual_day = actuals.loc[
        actuals["delivery_date_local"].eq(delivery)
        & actuals["actual_revision"].astype(str).eq(str(actual_revision))
    ].copy()

    score_file = Path(scores_path)
    scores = pd.read_csv(score_file) if score_file.exists() else pd.DataFrame()
    if not scores.empty:
        scores["delivery_time_utc"] = pd.to_datetime(scores["delivery_time_utc"], utc=True)
        scores["delivery_date_local"] = scores["delivery_time_utc"].dt.tz_convert("Europe/London").dt.date.astype(str)
        selected = scores.loc[
            scores["delivery_date_local"].eq(delivery)
            & scores["model_version"].astype(str).eq(str(model_version))
            & scores["actual_revision"].astype(str).eq(str(actual_revision))
        ].copy()
    else:
        selected = pd.DataFrame()

    gate = _read_json(deployment_gate_path)
    metrics = gate.get("metrics", {})
    grading_metrics: dict[str, Any] = {
        "actual_periods": int(len(actual_day)),
        "graded_periods": int(len(selected)),
        "model_mae_gbp_mwh": None,
        "model_rmse_gbp_mwh": None,
        "model_bias_gbp_mwh": None,
        "persistence_mae_gbp_mwh": None,
        "improvement_percent": None,
        "p10_p90_coverage": None,
        "actual_negative_periods": None,
    }
    if not selected.empty:
        error = pd.to_numeric(selected["error"], errors="coerce")
        absolute = pd.to_numeric(selected["absolute_error"], errors="coerce")
        squared = pd.to_numeric(selected["squared_error"], errors="coerce")
        persistence = pd.to_numeric(selected["persistence_absolute_error"], errors="coerce")
        model_mae = float(absolute.mean())
        persistence_mae = float(persistence.mean()) if persistence.notna().any() else None
        improvement = (
            float(100 * (persistence_mae - model_mae) / persistence_mae)
            if persistence_mae not in (None, 0.0)
            else None
        )
        grading_metrics.update(
            {
                "model_mae_gbp_mwh": model_mae,
                "model_rmse_gbp_mwh": float(np.sqrt(squared.mean())),
                "model_bias_gbp_mwh": float(error.mean()),
                "persistence_mae_gbp_mwh": persistence_mae,
                "improvement_percent": improvement,
                "p10_p90_coverage": _bool_mean(selected["p10_p90_covered"]),
                "actual_negative_periods": int(selected["actual_negative"].astype(str).str.lower().isin(["true", "1"]).sum()),
            }
        )

    payload = {
        "workflow_revision": "review-grading-v1",
        "delivery_date": delivery,
        "model_version": str(model_version),
        "actual_revision": str(actual_revision),
        "github_run_id": str(run_id),
        "github_run_attempt": str(run_attempt),
        "grading_metrics": grading_metrics,
        "deployment_gate": gate,
    }
    detail_path = root / "daily" / delivery / f"grading-run-{run_id}-attempt-{run_attempt}.json"
    _write_json(detail_path, payload, immutable=True)
    _write_json(root / "latest_grading.json", payload)
    _write_json(root / "latest_deployment_gate.json", gate)

    history_row = {
        "delivery_date": delivery,
        "model_version": str(model_version),
        "actual_revision": str(actual_revision),
        "github_run_id": str(run_id),
        "github_run_attempt": str(run_attempt),
        **grading_metrics,
        "deployment_ready": bool(gate.get("deployment_ready", False)),
        "deployment_mode": gate.get("mode"),
        "graded_delivery_days_total": metrics.get("graded_delivery_days"),
        "deployment_model_mae_gbp_mwh": metrics.get("model_mae_gbp_mwh"),
        "deployment_persistence_mae_gbp_mwh": metrics.get("persistence_mae_gbp_mwh"),
        "deployment_improvement_percent": metrics.get("improvement_percent"),
        "deployment_p10_p90_coverage": metrics.get("p10_p90_coverage"),
        "detail_path": detail_path.as_posix(),
    }
    _upsert_history(root / "grading_history.csv", history_row, GRADING_HISTORY_KEY, replace_existing=True)
    _update_daily_summary(
        root,
        delivery,
        {
            "model_version": str(model_version),
            "actual_revision": str(actual_revision),
            **grading_metrics,
            "deployment_ready": bool(gate.get("deployment_ready", False)),
            "deployment_mode": gate.get("mode"),
            "graded_delivery_days_total": metrics.get("graded_delivery_days"),
            "deployment_improvement_percent": metrics.get("improvement_percent"),
        },
    )
    _markdown_dashboard(root)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain human-readable GB platform logs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    forecast = subparsers.add_parser("forecast")
    forecast.add_argument("--logs-root", default="logs")
    forecast.add_argument("--daily-report", required=True)
    forecast.add_argument("--feature-summary", required=True)
    forecast.add_argument("--price-forecast", required=True)
    forecast.add_argument("--system-forecast", required=True)
    forecast.add_argument("--model-version", required=True)
    forecast.add_argument("--delivery-date", required=True)
    forecast.add_argument("--issue-time-utc", required=True)
    forecast.add_argument("--run-id", required=True)
    forecast.add_argument("--run-attempt", required=True)
    forecast.add_argument("--scenarios", type=int, required=True)

    grading = subparsers.add_parser("grading")
    grading.add_argument("--logs-root", default="logs")
    grading.add_argument("--actuals", required=True)
    grading.add_argument("--scores", required=True)
    grading.add_argument("--deployment-gate", required=True)
    grading.add_argument("--model-version", required=True)
    grading.add_argument("--delivery-date", required=True)
    grading.add_argument("--run-id", required=True)
    grading.add_argument("--run-attempt", required=True)
    grading.add_argument("--actual-revision", default="initial")

    args = parser.parse_args()
    if args.command == "forecast":
        result = register_forecast(
            args.logs_root,
            args.daily_report,
            args.feature_summary,
            args.price_forecast,
            args.system_forecast,
            args.model_version,
            args.delivery_date,
            args.issue_time_utc,
            args.run_id,
            args.run_attempt,
            args.scenarios,
        )
    else:
        result = register_grading(
            args.logs_root,
            args.actuals,
            args.scores,
            args.deployment_gate,
            args.model_version,
            args.delivery_date,
            args.run_id,
            args.run_attempt,
            args.actual_revision,
        )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
