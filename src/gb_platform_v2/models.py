"""Model wrappers used by the GB V2 platform."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.metrics import mean_absolute_error

from .transforms import arcsinh_transform, inverse_arcsinh


DEFAULT_REGRESSOR_PARAMS = {
    "n_estimators": 600,
    "learning_rate": 0.03,
    "num_leaves": 31,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "random_state": 42,
    "verbosity": -1,
}


@dataclass
class TrainedRegressor:
    model: LGBMRegressor
    features: list[str]
    target: str
    transform: str = "identity"
    scale: float = 50.0

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        raw = self.model.predict(frame[self.features])
        if self.transform == "arcsinh":
            return inverse_arcsinh(raw, self.scale)
        return np.asarray(raw, dtype=float)

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: str | Path) -> "TrainedRegressor":
        return joblib.load(path)


def train_regressor(
    frame: pd.DataFrame,
    features: list[str],
    target: str,
    transform: str = "identity",
    scale: float = 50.0,
    params: dict | None = None,
) -> TrainedRegressor:
    clean = frame.dropna(subset=[*features, target]).copy()
    if clean.empty:
        raise ValueError(f"No complete rows available for target {target}")
    y = clean[target].to_numpy(dtype=float)
    if transform == "arcsinh":
        y = arcsinh_transform(y, scale)
    elif transform != "identity":
        raise ValueError(f"Unsupported transform: {transform}")
    model = LGBMRegressor(**(params or DEFAULT_REGRESSOR_PARAMS))
    model.fit(clean[features], y)
    return TrainedRegressor(model, features, target, transform, scale)


def _timestamp_series(frame: pd.DataFrame) -> pd.Series:
    if "timestamp" in frame:
        values = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    elif isinstance(frame.index, pd.DatetimeIndex):
        values = pd.Series(pd.to_datetime(frame.index, utc=True), index=frame.index)
    else:
        raise KeyError("Timestamp-aware scoring requires a timestamp column or DatetimeIndex")
    if values.isna().any():
        raise ValueError("Timestamp-aware scoring found invalid timestamps")
    return values


def _daily_persistence_for_test(
    clean: pd.DataFrame,
    test: pd.DataFrame,
    target: str,
) -> pd.Series:
    """Return the observed target at the exact UTC timestamp minus 24 hours.

    This avoids row-shift errors when a settlement day is excluded or when GB DST
    produces 46- or 50-period local settlement days. Rows without a genuine
    timestamp-matched daily baseline remain missing and are excluded from the
    baseline comparison rather than filled with an unrelated value.
    """
    clean_timestamps = _timestamp_series(clean)
    history = pd.Series(
        pd.to_numeric(clean[target], errors="coerce").to_numpy(),
        index=pd.DatetimeIndex(clean_timestamps),
        name="daily_persistence",
    )
    if history.index.duplicated().any():
        raise ValueError("Timestamp-aware persistence requires unique timestamps")
    test_timestamps = pd.DatetimeIndex(_timestamp_series(test))
    prior_timestamps = test_timestamps - pd.Timedelta(hours=24)
    baseline = history.reindex(prior_timestamps)
    baseline.index = test.index
    return baseline


def chronological_holdout_score(
    frame: pd.DataFrame,
    features: list[str],
    target: str,
    holdout_rows: int,
    transform: str = "identity",
    scale: float = 50.0,
) -> dict[str, float]:
    clean = frame.dropna(subset=[*features, target]).copy()
    if holdout_rows <= 0 or holdout_rows >= len(clean):
        raise ValueError("holdout_rows must be between zero and dataset length")
    train = clean.iloc[:-holdout_rows]
    test = clean.iloc[-holdout_rows:]
    fitted = train_regressor(train, features, target, transform, scale)
    prediction = pd.Series(fitted.predict(test), index=test.index, dtype=float)
    actual = pd.to_numeric(test[target], errors="coerce").astype(float)
    baseline = _daily_persistence_for_test(clean, test, target)
    comparable = baseline.notna() & actual.notna() & prediction.notna()
    if not comparable.any():
        raise ValueError(f"No timestamp-matched daily persistence rows for target {target}")
    model_mae = mean_absolute_error(actual.loc[comparable], prediction.loc[comparable])
    baseline_mae = mean_absolute_error(actual.loc[comparable], baseline.loc[comparable])
    return {
        "model_mae": float(model_mae),
        "baseline_mae": float(baseline_mae),
        "improvement_percent": float(100 * (baseline_mae - model_mae) / baseline_mae)
        if baseline_mae
        else 0.0,
        "comparison_rows": int(comparable.sum()),
        "holdout_rows": int(len(test)),
        "baseline_missing_rows": int((~baseline.notna()).sum()),
        "baseline_definition": "observed target at exact timestamp minus 24 hours",
    }


@dataclass
class CurtailmentModel:
    classifier: LGBMClassifier
    volume_model: LGBMRegressor
    features: list[str]

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        probability = self.classifier.predict_proba(frame[self.features])[:, 1]
        conditional_volume = np.maximum(0.0, self.volume_model.predict(frame[self.features]))
        return pd.DataFrame(
            {
                "curtailment_probability": probability,
                "conditional_curtailed_mw": conditional_volume,
                "expected_curtailed_mw": probability * conditional_volume,
            },
            index=frame.index,
        )


def train_curtailment_model(
    frame: pd.DataFrame,
    features: list[str],
    curtailed_column: str,
) -> CurtailmentModel:
    clean = frame.dropna(subset=[*features, curtailed_column]).copy()
    event = (clean[curtailed_column] > 0).astype(int)
    if event.nunique() < 2:
        raise ValueError("Curtailment classifier needs both event and non-event rows")
    classifier = LGBMClassifier(**DEFAULT_REGRESSOR_PARAMS)
    classifier.fit(clean[features], event)
    positive = clean.loc[event.eq(1)]
    volume_model = LGBMRegressor(**DEFAULT_REGRESSOR_PARAMS)
    volume_model.fit(positive[features], positive[curtailed_column])
    return CurtailmentModel(classifier, volume_model, features)


@dataclass
class MarginalTechnologyModel:
    classifier: LGBMClassifier
    features: list[str]
    classes: list[str]

    def probabilities(self, frame: pd.DataFrame) -> pd.DataFrame:
        values = self.classifier.predict_proba(frame[self.features])
        return pd.DataFrame(values, columns=self.classes, index=frame.index)


def train_marginal_technology_model(
    frame: pd.DataFrame,
    features: list[str],
    label_column: str,
) -> MarginalTechnologyModel:
    clean = frame.dropna(subset=[*features, label_column]).copy()
    classifier = LGBMClassifier(**DEFAULT_REGRESSOR_PARAMS)
    classifier.fit(clean[features], clean[label_column].astype(str))
    return MarginalTechnologyModel(classifier, features, classifier.classes_.tolist())
