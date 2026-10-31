"""Probabilistic forecast scoring used by the final V2-R paper analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd


def pinball_loss(actual: np.ndarray, quantile: np.ndarray, tau: float) -> float:
    if not 0.0 < tau < 1.0:
        raise ValueError("tau must be between zero and one")
    y = np.asarray(actual, dtype=float)
    q = np.asarray(quantile, dtype=float)
    error = y - q
    return float(np.mean(np.maximum(tau * error, (tau - 1.0) * error)))


def interval_score(
    actual: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    alpha: float = 0.20,
) -> float:
    """Gneiting-Raftery interval score; lower values are better."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")
    y = np.asarray(actual, dtype=float)
    lo = np.asarray(lower, dtype=float)
    hi = np.asarray(upper, dtype=float)
    if np.any(hi < lo):
        raise ValueError("upper interval bound is below lower bound")
    width = hi - lo
    below = (y < lo).astype(float)
    above = (y > hi).astype(float)
    score = width + (2.0 / alpha) * (lo - y) * below + (2.0 / alpha) * (y - hi) * above
    return float(np.mean(score))


def crps_ensemble(actual: np.ndarray, paths: np.ndarray) -> float:
    """Mean CRPS for scenario paths shaped [scenario, observation]."""
    y = np.asarray(actual, dtype=float)
    x = np.asarray(paths, dtype=float)
    if x.ndim != 2 or x.shape[1] != len(y):
        raise ValueError("paths must have shape [scenario, observation]")
    first = np.mean(np.abs(x - y[None, :]), axis=0)
    sorted_x = np.sort(x, axis=0)
    m = sorted_x.shape[0]
    ranks = np.arange(1, m + 1, dtype=float)[:, None]
    pair_mean = (2.0 / (m * m)) * np.sum(
        (2.0 * ranks - m - 1.0) * sorted_x,
        axis=0,
    )
    return float(np.mean(first - 0.5 * pair_mean))


def probabilistic_summary(
    actual: pd.Series | np.ndarray,
    p10: pd.Series | np.ndarray,
    p50: pd.Series | np.ndarray,
    p90: pd.Series | np.ndarray,
    scenario_paths: np.ndarray | None = None,
) -> dict[str, float]:
    y = np.asarray(actual, dtype=float)
    q10 = np.asarray(p10, dtype=float)
    q50 = np.asarray(p50, dtype=float)
    q90 = np.asarray(p90, dtype=float)
    losses = [
        pinball_loss(y, q10, 0.10),
        pinball_loss(y, q50, 0.50),
        pinball_loss(y, q90, 0.90),
    ]
    output = {
        "p10_p90_coverage": float(np.mean((y >= q10) & (y <= q90))),
        "mean_interval_width_gbp_mwh": float(np.mean(q90 - q10)),
        "interval_score_80": interval_score(y, q10, q90, alpha=0.20),
        "pinball_p10": losses[0],
        "pinball_p50": losses[1],
        "pinball_p90": losses[2],
        "mean_pinball_p10_p50_p90": float(np.mean(losses)),
    }
    if scenario_paths is not None:
        output["crps_ensemble"] = crps_ensemble(y, scenario_paths)
    return output
