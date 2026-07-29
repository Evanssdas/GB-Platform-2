"""Illustrative risk calculations for signed electricity prices."""

from __future__ import annotations

import numpy as np
import pandas as pd


def parametric_var_absolute_changes(
    prices: pd.Series,
    position_mwh: float,
    confidence_z: float = 1.6448536269514722,
    lookback: int = 1440,
) -> float:
    """Legacy-style parametric VaR using absolute £/MWh changes.

    Absolute changes are used because percentage returns become unstable near
    zero and misleading when electricity prices are negative.
    """
    changes = prices.astype(float).diff().dropna().tail(lookback)
    if changes.empty:
        raise ValueError("Not enough prices for VaR")
    sigma = changes.std(ddof=1)
    return float(abs(position_mwh) * sigma * confidence_z)


def historical_simulation_var(
    prices: pd.Series,
    position_mwh: float,
    confidence: float = 0.95,
    lookback: int = 1440,
) -> dict[str, float]:
    changes = prices.astype(float).diff().dropna().tail(lookback)
    pnl = changes.to_numpy() * float(position_mwh)
    loss = -pnl
    var = np.quantile(loss, confidence)
    tail = loss[loss >= var]
    return {
        "var": float(var),
        "expected_shortfall": float(tail.mean()) if len(tail) else float(var),
    }


def scenario_risk(
    scenario_prices: np.ndarray,
    reference_prices: np.ndarray,
    position_mwh: float,
    confidence: float = 0.95,
) -> dict[str, float]:
    """Calculate VaR and ES from whole-horizon simulated P&L."""
    if scenario_prices.ndim != 2:
        raise ValueError("scenario_prices must be [scenario, period]")
    reference = np.asarray(reference_prices, dtype=float)
    if scenario_prices.shape[1] != len(reference):
        raise ValueError("Scenario horizon does not match reference prices")
    pnl = ((scenario_prices - reference[None, :]) * position_mwh * 0.5).sum(axis=1)
    loss = -pnl
    var = np.quantile(loss, confidence)
    tail = loss[loss >= var]
    return {
        "scenario_var": float(var),
        "expected_shortfall": float(tail.mean()) if len(tail) else float(var),
        "worst_loss": float(loss.max()),
        "best_profit": float(pnl.max()),
    }
