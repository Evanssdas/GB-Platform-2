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
    prediction = fitted.predict(test)
    actual = test[target].to_numpy(dtype=float)
    baseline = test[target].shift(48).fillna(train[target].iloc[-1]).to_numpy(dtype=float)
    model_mae = mean_absolute_error(actual, prediction)
    baseline_mae = mean_absolute_error(actual, baseline)
    return {
        "model_mae": float(model_mae),
        "baseline_mae": float(baseline_mae),
        "improvement_percent": float(100 * (baseline_mae - model_mae) / baseline_mae)
        if baseline_mae else 0.0,
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
