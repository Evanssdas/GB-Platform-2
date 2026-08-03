"""Build a permanent human-readable index of daily forecast and grading history."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=object) if path.exists() else pd.DataFrame()


def _fmt(value: object, decimals: int = 2, suffix: str = "") -> str:
    if value is None or pd.isna(value) or str(value).strip() in {"", "nan", "None"}:
        return "—"
    try:
        return f"{float(value):,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def build_history_index(logs_root: str | Path = "logs") -> Path:
    root = Path(logs_root)
    daily_root = root / "daily"
    daily_root.mkdir(parents=True, exist_ok=True)

    summary = _read_csv(root / "daily_summary.csv")
    summary_rows: dict[str, pd.Series] = {}
    if not summary.empty and "delivery_date" in summary:
        summary = summary.drop_duplicates("delivery_date", keep="last")
        summary_rows = {
            str(row["delivery_date"]): row
            for _, row in summary.iterrows()
            if str(row.get("delivery_date", "")).strip()
        }

    directory_dates = {
        path.name
        for path in daily_root.iterdir()
        if path.is_dir() and len(path.name) == 10 and path.name[4] == "-" and path.name[7] == "-"
    }
    dates = sorted(directory_dates | set(summary_rows), reverse=True)

    lines = [
        "# GB daily forecast history",
        "",
        "Each dated folder preserves the 30-minute forecast table, plots, model metadata and grading status for that GB delivery day.",
        "",
        "| Delivery day | Forecast report | Grading | Model MAE | Persistence MAE | Improvement | P10–P90 coverage |",
        "|---|---|---|---:|---:|---:|---:|",
    ]

    for delivery in dates:
        row = summary_rows.get(delivery)
        day_readme = daily_root / delivery / "README.md"
        report = f"[{delivery}]({delivery}/README.md)" if day_readme.exists() else delivery
        if row is None:
            grading = "Pending"
            model_mae = persistence_mae = improvement = coverage = "—"
        else:
            graded = int(float(row.get("graded_periods", 0) or 0)) if not pd.isna(row.get("graded_periods")) else 0
            grading = f"Graded ({graded} periods)" if graded else "Pending"
            model_mae = _fmt(row.get("model_mae_gbp_mwh"))
            persistence_mae = _fmt(row.get("persistence_mae_gbp_mwh"))
            improvement = _fmt(row.get("improvement_percent"), suffix="%")
            coverage = _fmt(row.get("p10_p90_coverage"), 3)
        lines.append(
            f"| {delivery} | {report} | {grading} | {model_mae} | {persistence_mae} | {improvement} | {coverage} |"
        )

    if not dates:
        lines.append("| — | No daily forecasts have been archived yet | — | — | — | — | — |")

    lines.extend(
        [
            "",
            "## Permanent source files",
            "",
            "- [`../daily_summary.csv`](../daily_summary.csv): one row per delivery day.",
            "- [`../../live/forecasts.csv`](../../live/forecasts.csv): immutable half-hourly forecast log.",
            "- [`../../live/actuals.csv`](../../live/actuals.csv): collected market actuals.",
            "- [`../../live/scores.csv`](../../live/scores.csv): reproducible half-hourly grading records.",
            "",
        ]
    )

    output = daily_root / "README.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build daily forecast-history index")
    parser.add_argument("--logs-root", default="logs")
    args = parser.parse_args()
    print(build_history_index(args.logs_root))


if __name__ == "__main__":
    main()
