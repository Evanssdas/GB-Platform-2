"""Generate a complete human-readable daily GB shadow-market report."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REQUIRED_SYSTEM_COLUMNS = {
    "timestamp",
    "demand_mw",
    "embedded_wind_mw",
    "embedded_solar_mw",
    "transmission_wind_mw",
    "nuclear_mw",
    "net_import_mw",
    "inertia_gvas",
    "total_wind_mw",
    "residual_before_nuclear_mw",
    "residual_after_nuclear_mw",
    "net_system_short_mw",
    "price_point_gbp_mwh",
}
REQUIRED_PRICE_COLUMNS = {
    "timestamp",
    "p10",
    "p50",
    "p90",
    "point",
    "negative_probability",
}


def _read_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected a JSON object in {path}")
    return payload


def _load_csv(path: str | Path, required: set[str], label: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = sorted(required - set(frame))
    if missing:
        raise KeyError(f"{label} is missing columns: {missing}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    return frame.sort_values("timestamp").reset_index(drop=True)


def _local_time_labels(timestamp: pd.Series) -> pd.Series:
    return timestamp.dt.tz_convert("Europe/London").dt.strftime("%H:%M")


def _local_timestamp_text(value: pd.Timestamp) -> str:
    return value.tz_convert("Europe/London").strftime("%Y-%m-%d %H:%M %Z")


def _save_line_plot(
    frame: pd.DataFrame,
    columns: list[tuple[str, str]],
    title: str,
    ylabel: str,
    output: Path,
    *,
    zero_line: bool = False,
) -> None:
    fig, ax = plt.subplots(figsize=(13, 6))
    for column, label in columns:
        ax.plot(frame["timestamp_local"], frame[column], label=label)
    if zero_line:
        ax.axhline(0, linewidth=1)
    ax.set_title(title)
    ax.set_xlabel("GB delivery time")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _save_price_fan(price: pd.DataFrame, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.fill_between(
        price["timestamp_local"],
        price["p10"],
        price["p90"],
        alpha=0.25,
        label="P10–P90",
    )
    ax.plot(price["timestamp_local"], price["p50"], label="P50 Monte Carlo")
    ax.plot(price["timestamp_local"], price["point"], label="Point model")
    ax.axhline(0, linewidth=1)
    ax.set_title("GB half-hourly probabilistic price forecast")
    ax.set_xlabel("GB delivery time")
    ax.set_ylabel("GBP/MWh")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _save_negative_probability(price: pd.DataFrame, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 4.5))
    ax.plot(price["timestamp_local"], price["negative_probability"] * 100.0)
    ax.set_ylim(bottom=0)
    ax.set_title("Probability of a negative price by settlement period")
    ax.set_xlabel("GB delivery time")
    ax.set_ylabel("Probability (%)")
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _save_risk_limits(risk: dict[str, float], output: Path) -> None:
    labels = ["Reference position", "VaR maximum", "VaR + ES binding maximum"]
    values = [
        risk["reference_position_mwh"],
        risk["maximum_volume_var_mwh"],
        risk["maximum_volume_binding_mwh"],
    ]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    bars = ax.barh(labels, values)
    ax.set_title("Paper-position limits under the daily risk budget")
    ax.set_xlabel("Position volume (MWh)")
    ax.grid(True, axis="x", alpha=0.25)
    for bar, value in zip(bars, values):
        ax.text(value, bar.get_y() + bar.get_height() / 2, f" {value:,.1f}", va="center")
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def _peak(frame: pd.DataFrame, column: str, mode: str = "max") -> dict[str, Any]:
    index = frame[column].idxmax() if mode == "max" else frame[column].idxmin()
    return {
        "value": float(frame.loc[index, column]),
        "timestamp_local": _local_timestamp_text(frame.loc[index, "timestamp_local"]),
    }


def _daily_energy(frame: pd.DataFrame, column: str) -> float:
    return float(pd.to_numeric(frame[column], errors="raise").sum() * 0.5)


def _risk_position_limits(
    daily_report: dict[str, Any],
    paper_capital_gbp: float,
    var_budget_fraction: float,
    reference_position_mwh: float,
    confidence_level: float,
) -> dict[str, float]:
    if paper_capital_gbp <= 0 or not 0 < var_budget_fraction <= 1:
        raise ValueError("Paper capital and VaR budget fraction must be positive")
    if reference_position_mwh <= 0:
        raise ValueError("Reference position must be positive")
    risk = daily_report.get("risk")
    if not isinstance(risk, dict):
        raise KeyError("Daily report is missing risk")
    scenario_var = float(risk["scenario_var"])
    expected_shortfall = float(risk["expected_shortfall"])
    worst_loss = float(risk["worst_loss"])
    best_profit = float(risk["best_profit"])
    if scenario_var <= 0 or expected_shortfall <= 0:
        raise ValueError("VaR and Expected Shortfall must be positive for position sizing")

    budget = paper_capital_gbp * var_budget_fraction
    maximum_var = reference_position_mwh * budget / scenario_var
    maximum_es = reference_position_mwh * budget / expected_shortfall
    return {
        "paper_capital_gbp": float(paper_capital_gbp),
        "var_budget_fraction": float(var_budget_fraction),
        "daily_risk_budget_gbp": float(budget),
        "confidence_level": float(confidence_level),
        "reference_position_mwh": float(reference_position_mwh),
        "reference_scenario_var_gbp": scenario_var,
        "reference_expected_shortfall_gbp": expected_shortfall,
        "reference_worst_loss_gbp": worst_loss,
        "reference_best_profit_gbp": best_profit,
        "reference_var_budget_utilisation_percent": float(100.0 * scenario_var / budget),
        "reference_es_budget_utilisation_percent": float(100.0 * expected_shortfall / budget),
        "maximum_volume_var_mwh": float(maximum_var),
        "maximum_volume_expected_shortfall_mwh": float(maximum_es),
        "maximum_volume_binding_mwh": float(min(maximum_var, maximum_es)),
    }


def _component_sources(system: pd.DataFrame, daily_report: dict[str, Any]) -> dict[str, str]:
    sources = daily_report.get("component_sources", {})
    if isinstance(sources, dict) and sources:
        return {str(key): str(value) for key, value in sources.items()}
    output: dict[str, str] = {}
    for column in system.columns:
        if column.startswith("component_source_"):
            target = column.removeprefix("component_source_")
            values = system[column].dropna().astype(str).unique()
            output[target] = values[0] if len(values) == 1 else "mixed"
    return output


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---:" if pd.api.types.is_numeric_dtype(frame[column]) else "---" for column in columns) + "|",
    ]
    for _, row in frame.iterrows():
        values: list[str] = []
        for column in columns:
            value = row[column]
            if pd.isna(value):
                values.append("—")
            elif isinstance(value, (float, np.floating)):
                values.append(f"{float(value):,.2f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def build_daily_market_report(
    system_forecast_path: str | Path,
    price_forecast_path: str | Path,
    daily_report_path: str | Path,
    feature_summary_path: str | Path,
    output_dir: str | Path,
    model_version: str,
    delivery_date: str,
    issue_time_utc: str,
    run_id: str,
    run_attempt: str,
    scenarios: int,
    paper_capital_gbp: float = 500_000.0,
    var_budget_fraction: float = 0.02,
    reference_position_mwh: float = 100.0,
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    """Generate plots, tables and a Markdown report for one shadow forecast day."""
    output = Path(output_dir)
    plots = output / "plots"
    plots.mkdir(parents=True, exist_ok=True)

    system = _load_csv(system_forecast_path, REQUIRED_SYSTEM_COLUMNS, "system forecast")
    price = _load_csv(price_forecast_path, REQUIRED_PRICE_COLUMNS, "price forecast")
    if len(system) != len(price):
        raise ValueError("System and price forecasts have different row counts")
    if not system["timestamp"].equals(price["timestamp"]):
        raise ValueError("System and price forecast timestamps do not align")

    system["timestamp_local"] = system["timestamp"].dt.tz_convert("Europe/London")
    price["timestamp_local"] = price["timestamp"].dt.tz_convert("Europe/London")
    daily_report = _read_json(daily_report_path)
    feature_summary = _read_json(feature_summary_path)
    if len(system) != int(feature_summary["expected_period_count"]):
        raise ValueError("Report inputs do not cover the complete GB settlement day")

    risk = _risk_position_limits(
        daily_report,
        paper_capital_gbp,
        var_budget_fraction,
        reference_position_mwh,
        confidence_level,
    )
    sources = _component_sources(system, daily_report)

    plot_paths = {
        "system_components": plots / "01_system_components.png",
        "residual_demand": plots / "02_residual_demand.png",
        "wind_solar": plots / "03_wind_solar_breakdown.png",
        "imports_inertia": plots / "04_net_imports_and_inertia.png",
        "price_fan": plots / "05_price_fan.png",
        "negative_probability": plots / "06_negative_price_probability.png",
        "risk_limits": plots / "07_risk_position_limits.png",
    }
    _save_line_plot(
        system,
        [
            ("demand_mw", "Demand"),
            ("total_wind_mw", "Total wind"),
            ("embedded_solar_mw", "Embedded solar"),
            ("nuclear_mw", "Nuclear"),
        ],
        "Forecast system components",
        "MW",
        plot_paths["system_components"],
    )
    _save_line_plot(
        system,
        [
            ("demand_mw", "Demand"),
            ("residual_before_nuclear_mw", "Residual before nuclear"),
            ("residual_after_nuclear_mw", "Residual after nuclear"),
            ("net_system_short_mw", "Net system short"),
        ],
        "Demand and residual-demand layers",
        "MW",
        plot_paths["residual_demand"],
        zero_line=True,
    )
    _save_line_plot(
        system,
        [
            ("embedded_wind_mw", "Embedded wind"),
            ("transmission_wind_mw", "Transmission wind"),
            ("total_wind_mw", "Total wind"),
            ("embedded_solar_mw", "Embedded solar"),
        ],
        "Wind and solar forecast breakdown",
        "MW",
        plot_paths["wind_solar"],
    )

    fig, ax = plt.subplots(figsize=(13, 5.5))
    ax.plot(system["timestamp_local"], system["net_import_mw"], label="Net imports (MW)")
    ax.axhline(0, linewidth=1)
    ax.set_title("Net imports and system inertia")
    ax.set_xlabel("GB delivery time")
    ax.set_ylabel("Net imports (MW)")
    ax.grid(True, alpha=0.25)
    second = ax.twinx()
    second.plot(system["timestamp_local"], system["inertia_gvas"], label="Inertia (GVA·s)")
    second.set_ylabel("Inertia (GVA·s)")
    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = second.get_legend_handles_labels()
    ax.legend(handles1 + handles2, labels1 + labels2, loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(plot_paths["imports_inertia"], dpi=180)
    plt.close(fig)

    _save_price_fan(price, plot_paths["price_fan"])
    _save_negative_probability(price, plot_paths["negative_probability"])
    _save_risk_limits(risk, plot_paths["risk_limits"])

    half_hourly = pd.DataFrame(
        {
            "settlement_period": np.arange(1, len(system) + 1),
            "gb_time": _local_time_labels(system["timestamp"]),
            "demand_mw": system["demand_mw"],
            "embedded_wind_mw": system["embedded_wind_mw"],
            "transmission_wind_mw": system["transmission_wind_mw"],
            "total_wind_mw": system["total_wind_mw"],
            "solar_mw": system["embedded_solar_mw"],
            "nuclear_mw": system["nuclear_mw"],
            "net_import_mw": system["net_import_mw"],
            "residual_before_nuclear_mw": system["residual_before_nuclear_mw"],
            "residual_after_nuclear_mw": system["residual_after_nuclear_mw"],
            "net_system_short_mw": system["net_system_short_mw"],
            "inertia_gvas": system["inertia_gvas"],
            "price_p10_gbp_mwh": price["p10"],
            "price_p50_gbp_mwh": price["p50"],
            "price_p90_gbp_mwh": price["p90"],
            "negative_price_probability": price["negative_probability"],
        }
    )
    half_hourly.to_csv(output / "half_hourly_system_and_price_table.csv", index=False)

    daily_system = pd.DataFrame(
        [
            {
                "metric": "Demand energy",
                "value": _daily_energy(system, "demand_mw"),
                "unit": "MWh",
            },
            {
                "metric": "Total wind energy",
                "value": _daily_energy(system, "total_wind_mw"),
                "unit": "MWh",
            },
            {
                "metric": "Solar energy",
                "value": _daily_energy(system, "embedded_solar_mw"),
                "unit": "MWh",
            },
            {
                "metric": "Nuclear energy",
                "value": _daily_energy(system, "nuclear_mw"),
                "unit": "MWh",
            },
            {
                "metric": "Net import energy",
                "value": _daily_energy(system, "net_import_mw"),
                "unit": "MWh",
            },
        ]
    )
    daily_system.to_csv(output / "daily_system_summary.csv", index=False)

    risk_table = pd.DataFrame(
        [
            {"metric": "Paper capital", "value": risk["paper_capital_gbp"], "unit": "GBP"},
            {"metric": "Daily VaR appetite", "value": 100 * risk["var_budget_fraction"], "unit": "% capital"},
            {"metric": "Daily risk budget", "value": risk["daily_risk_budget_gbp"], "unit": "GBP"},
            {"metric": "Confidence level", "value": 100 * risk["confidence_level"], "unit": "%"},
            {"metric": "Reference position", "value": risk["reference_position_mwh"], "unit": "MWh"},
            {"metric": "Scenario VaR", "value": risk["reference_scenario_var_gbp"], "unit": "GBP"},
            {"metric": "Expected Shortfall", "value": risk["reference_expected_shortfall_gbp"], "unit": "GBP"},
            {"metric": "Worst simulated loss", "value": risk["reference_worst_loss_gbp"], "unit": "GBP"},
            {"metric": "Best simulated profit", "value": risk["reference_best_profit_gbp"], "unit": "GBP"},
            {"metric": "VaR budget utilisation", "value": risk["reference_var_budget_utilisation_percent"], "unit": "%"},
            {"metric": "ES budget utilisation", "value": risk["reference_es_budget_utilisation_percent"], "unit": "%"},
            {"metric": "Maximum volume by VaR", "value": risk["maximum_volume_var_mwh"], "unit": "MWh"},
            {"metric": "Maximum volume by Expected Shortfall", "value": risk["maximum_volume_expected_shortfall_mwh"], "unit": "MWh"},
            {"metric": "Binding maximum permissible volume", "value": risk["maximum_volume_binding_mwh"], "unit": "MWh"},
        ]
    )
    risk_table.to_csv(output / "var_and_position_limits.csv", index=False)

    peaks = {
        "peak_demand": _peak(system, "demand_mw"),
        "peak_total_wind": _peak(system, "total_wind_mw"),
        "peak_solar": _peak(system, "embedded_solar_mw"),
        "minimum_nuclear": _peak(system, "nuclear_mw", "min"),
        "peak_residual_after_nuclear": _peak(system, "residual_after_nuclear_mw"),
        "peak_net_system_short": _peak(system, "net_system_short_mw"),
        "peak_p50_price": _peak(price.rename(columns={"p50": "value_series"}), "value_series"),
        "minimum_p50_price": _peak(price.rename(columns={"p50": "value_series"}), "value_series", "min"),
    }

    summary = {
        "workflow_revision": "daily-market-report-v1",
        "model_version": str(model_version),
        "model_profile": daily_report.get("model_profile"),
        "delivery_date": str(delivery_date),
        "issue_time_utc": str(issue_time_utc),
        "github_run_id": str(run_id),
        "github_run_attempt": str(run_attempt),
        "monte_carlo_scenarios": int(scenarios),
        "period_count": int(len(system)),
        "component_sources": sources,
        "risk_and_position_limits": risk,
        "peaks": peaks,
        "daily_system_energy": daily_system.to_dict("records"),
        "price_summary": {
            "p50_min_gbp_mwh": float(price["p50"].min()),
            "p50_mean_gbp_mwh": float(price["p50"].mean()),
            "p50_max_gbp_mwh": float(price["p50"].max()),
            "maximum_negative_price_probability": float(price["negative_probability"].max()),
        },
        "definitions": {
            "total_wind_mw": "embedded_wind_mw + transmission_wind_mw",
            "residual_before_nuclear_mw": "demand_mw - total_wind_mw - embedded_solar_mw",
            "residual_after_nuclear_mw": "residual_before_nuclear_mw - nuclear_mw",
            "net_system_short_mw": "residual_after_nuclear_mw - net_import_mw",
            "maximum_volume_var_mwh": "reference_position_mwh * daily_risk_budget_gbp / reference_scenario_var_gbp",
            "maximum_volume_binding_mwh": "minimum of VaR-based and Expected-Shortfall-based maximum volumes",
        },
    }
    (output / "report.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    source_rows = pd.DataFrame(
        [{"component": key, "source": value} for key, value in sorted(sources.items())]
    )
    risk_markdown = risk_table.copy()
    risk_markdown["value"] = risk_markdown["value"].map(lambda value: f"{float(value):,.2f}")
    system_markdown = daily_system.copy()
    system_markdown["value"] = system_markdown["value"].map(lambda value: f"{float(value):,.1f}")

    report_lines = [
        f"# GB day-ahead market report — {delivery_date}",
        "",
        f"**Model:** `{model_version}`  ",
        f"**Profile:** `{daily_report.get('model_profile', 'unknown')}`  ",
        f"**Issue time:** `{issue_time_utc}`  ",
        f"**Monte Carlo scenarios:** `{scenarios:,}`  ",
        f"**Settlement periods:** `{len(system)}`",
        "",
        "## Executive summary",
        "",
        f"- P50 price range: **£{price['p50'].min():,.2f}–£{price['p50'].max():,.2f}/MWh**; daily mean **£{price['p50'].mean():,.2f}/MWh**.",
        f"- Peak demand: **{peaks['peak_demand']['value']:,.0f} MW** at **{peaks['peak_demand']['timestamp_local']}**.",
        f"- Peak residual demand after nuclear: **{peaks['peak_residual_after_nuclear']['value']:,.0f} MW** at **{peaks['peak_residual_after_nuclear']['timestamp_local']}**.",
        f"- Scenario VaR for the illustrative {reference_position_mwh:,.0f} MWh position: **£{risk['reference_scenario_var_gbp']:,.2f}**.",
        f"- Expected Shortfall: **£{risk['reference_expected_shortfall_gbp']:,.2f}**.",
        f"- Maximum volume under the VaR limit: **{risk['maximum_volume_var_mwh']:,.2f} MWh**.",
        f"- Conservative binding maximum under both VaR and Expected Shortfall: **{risk['maximum_volume_binding_mwh']:,.2f} MWh**.",
        "",
        "> Position limits are illustrative paper-risk outputs, not autonomous trading authorisation or financial advice.",
        "",
        "## Demand, wind, solar and nuclear",
        "",
        "![System components](plots/01_system_components.png)",
        "",
        "![Wind and solar breakdown](plots/03_wind_solar_breakdown.png)",
        "",
        "### Daily energy summary",
        "",
        _markdown_table(system_markdown),
        "",
        "### Component forecast sources",
        "",
        _markdown_table(source_rows),
        "",
        "## Residual demand and system balance",
        "",
        "![Residual demand](plots/02_residual_demand.png)",
        "",
        "Definitions:",
        "",
        "- `residual_before_nuclear_mw = demand_mw - total_wind_mw - embedded_solar_mw`",
        "- `residual_after_nuclear_mw = residual_before_nuclear_mw - nuclear_mw`",
        "- `net_system_short_mw = residual_after_nuclear_mw - net_import_mw`",
        "",
        "![Net imports and inertia](plots/04_net_imports_and_inertia.png)",
        "",
        "## Probabilistic price forecast",
        "",
        "![Price fan](plots/05_price_fan.png)",
        "",
        "![Negative-price probability](plots/06_negative_price_probability.png)",
        "",
        "## VaR, Expected Shortfall and maximum permissible volume",
        "",
        "The position limit uses the explicitly labelled paper assumptions below. Risk is scaled linearly from the Monte Carlo result for the reference position.",
        "",
        _markdown_table(risk_markdown),
        "",
        "![Risk position limits](plots/07_risk_position_limits.png)",
        "",
        "## Detailed tables",
        "",
        "- [Half-hourly system and price table](half_hourly_system_and_price_table.csv)",
        "- [Daily system summary](daily_system_summary.csv)",
        "- [VaR and position limits](var_and_position_limits.csv)",
        "- [Machine-readable report](report.json)",
        "",
    ]
    (output / "report.md").write_text("\n".join(report_lines), encoding="utf-8")

    latest = output.parent.parent / "latest_report.md"
    latest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(output / "report.md", latest)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the complete daily GB market report")
    parser.add_argument("--system-forecast", required=True)
    parser.add_argument("--price-forecast", required=True)
    parser.add_argument("--daily-report", required=True)
    parser.add_argument("--feature-summary", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--delivery-date", required=True)
    parser.add_argument("--issue-time-utc", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--scenarios", type=int, required=True)
    parser.add_argument("--paper-capital-gbp", type=float, default=500_000.0)
    parser.add_argument("--var-budget-fraction", type=float, default=0.02)
    parser.add_argument("--reference-position-mwh", type=float, default=100.0)
    parser.add_argument("--confidence-level", type=float, default=0.95)
    args = parser.parse_args()
    result = build_daily_market_report(
        args.system_forecast,
        args.price_forecast,
        args.daily_report,
        args.feature_summary,
        args.output_dir,
        args.model_version,
        args.delivery_date,
        args.issue_time_utc,
        args.run_id,
        args.run_attempt,
        args.scenarios,
        args.paper_capital_gbp,
        args.var_budget_fraction,
        args.reference_position_mwh,
        args.confidence_level,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
