"""Plots and daily summaries."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def daily_price_summary(
    quantiles: pd.DataFrame,
    negative_probability: pd.Series,
    scenario_paths: np.ndarray,
) -> dict:
    p50 = quantiles["p50"]
    return {
        "period_count": int(len(quantiles)),
        "p50_daily_min_gbp_mwh": float(p50.min()),
        "p50_daily_max_gbp_mwh": float(p50.max()),
        "p50_daily_mean_gbp_mwh": float(p50.mean()),
        "probability_any_negative_period": float((scenario_paths < 0).any(axis=1).mean()),
        "maximum_period_negative_probability": float(negative_probability.max()),
        "distribution_daily_min_p10": float(np.percentile(scenario_paths.min(axis=1), 10)),
        "distribution_daily_min_p50": float(np.percentile(scenario_paths.min(axis=1), 50)),
        "distribution_daily_min_p90": float(np.percentile(scenario_paths.min(axis=1), 90)),
        "distribution_daily_max_p10": float(np.percentile(scenario_paths.max(axis=1), 10)),
        "distribution_daily_max_p50": float(np.percentile(scenario_paths.max(axis=1), 50)),
        "distribution_daily_max_p90": float(np.percentile(scenario_paths.max(axis=1), 90)),
    }


def plot_price_fan_chart(
    quantiles: pd.DataFrame,
    negative_probability: pd.Series,
    output_path: str | Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    x = quantiles.index
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.fill_between(x, quantiles["p10"], quantiles["p90"], alpha=0.25, label="P10–P90")
    ax.plot(x, quantiles["p50"], label="P50")
    ax.axhline(0, linewidth=1)
    ax.set_ylabel("£/MWh")
    ax.set_title("GB half-hourly probabilistic price forecast")
    ax.legend(loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)

    probability_path = output_path.with_name(output_path.stem + "_negative_probability.png")
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(x, negative_probability)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Probability")
    ax.set_title("Probability of a negative price by settlement period")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(probability_path, dpi=160)
    plt.close(fig)


def write_json(data: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
