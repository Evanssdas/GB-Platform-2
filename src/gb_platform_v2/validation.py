"""Leakage-safe chronological validation and stacking utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from .models import train_regressor


def expanding_oof_predictions(
    frame: pd.DataFrame,
    features: list[str],
    target: str,
    n_splits: int = 5,
    transform: str = "identity",
    scale: float = 50.0,
) -> pd.Series:
    """Return expanding-window out-of-fold predictions aligned to ``frame``.

    Rows in the first training block remain missing because no honest earlier model
    can predict them. Each populated row is predicted by a model trained only on
    earlier rows.
    """
    clean = frame.dropna(subset=[*features, target]).copy()
    if len(clean) < n_splits + 2:
        raise ValueError("Not enough complete rows for time-series out-of-fold prediction")

    output = pd.Series(np.nan, index=frame.index, dtype=float, name=f"oof_{target}")
    splitter = TimeSeriesSplit(n_splits=n_splits)
    for train_positions, validation_positions in splitter.split(clean):
        train = clean.iloc[train_positions]
        validation = clean.iloc[validation_positions]
        fitted = train_regressor(
            train,
            features,
            target,
            transform=transform,
            scale=scale,
        )
        output.loc[validation.index] = fitted.predict(validation)
    return output


def same_period_persistence(
    series: pd.Series,
    periods: int = 48,
) -> pd.Series:
    """Simple same-settlement-period persistence baseline."""
    return series.shift(periods)
