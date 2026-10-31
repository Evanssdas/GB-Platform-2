"""Frozen analysis path for the final V2-R manuscript results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from .evaluation import probabilistic_summary
from .features import (
    add_cyclical_time_features,
    add_market_regime_features,
    add_weather_features,
    choose_numeric_features,
)
from .models import chronological_holdout_score, train_regressor
from .pipeline import (
    BASE_NON_FEATURE_COLUMNS,
    SIGNED_COMPONENT_TARGETS,
    _add_stacked_balance_features,
    _component_targets,
    _is_price_layer_feature,
)
from .scenarios import bootstrap_error_scenarios, run_price_monte_carlo
from .validation import expanding_oof_predictions


def _persistence(frame: pd.DataFrame, target: str, timestamps: pd.Series) -> pd.Series:
    history = pd.Series(
        pd.to_numeric(frame[target], errors="coerce").to_numpy(dtype=float),
        index=pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True)),
    )
    lookup = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True)) - pd.Timedelta(hours=48)
    values = history.reindex(lookup).to_numpy(dtype=float)
    return pd.Series(values, index=timestamps.index, dtype=float)


def _metrics(actual: pd.Series, prediction: pd.Series, persistence: pd.Series) -> dict:
    valid = actual.notna() & prediction.notna() & persistence.notna()
    y = actual.loc[valid].astype(float)
    p = prediction.loc[valid].astype(float)
    b = persistence.loc[valid].astype(float)
    model_mae = float(mean_absolute_error(y, p))
    persistence_mae = float(mean_absolute_error(y, b))
    return {
        "rows": int(valid.sum()),
        "mae": model_mae,
        "rmse": float(mean_squared_error(y, p) ** 0.5),
        "bias": float((p - y).mean()),
        "persistence_mae": persistence_mae,
        "improvement_percent": float(
            100.0 * (persistence_mae - model_mae) / persistence_mae
        ) if persistence_mae else 0.0,
    }


def _save_figures(
    test: pd.DataFrame,
    price: pd.DataFrame,
    component_predictions: pd.DataFrame,
    importance: pd.DataFrame,
    shap_summary: pd.DataFrame,
    output: Path,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    local = pd.to_datetime(test["timestamp"], utc=True).dt.tz_convert("Europe/London")
    display_rows = min(len(test), 48 * 14)

    fig, ax = plt.subplots(figsize=(13, 5.5))
    ax.plot(local.iloc[:display_rows], test["price_gbp_mwh"].iloc[:display_rows], label="Observed APXMIDP")
    ax.plot(local.iloc[:display_rows], price["prediction"].iloc[:display_rows], label="V2-R")
    ax.plot(local.iloc[:display_rows], price["persistence"].iloc[:display_rows], label="D-2 persistence", alpha=0.75)
    ax.set_title("Untouched V2-R hold-out: observed and predicted price")
    ax.set_ylabel("GBP/MWh")
    ax.set_xlabel("GB delivery time")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output / "price_observed_vs_predicted.png", dpi=200)
    plt.close(fig)

    fan_rows = min(len(test), 48 * 7)
    fig, ax = plt.subplots(figsize=(13, 5.5))
    ax.fill_between(
        local.iloc[:fan_rows],
        price["p10"].iloc[:fan_rows],
        price["p90"].iloc[:fan_rows],
        alpha=0.25,
        label="P10-P90",
    )
    ax.plot(local.iloc[:fan_rows], price["p50"].iloc[:fan_rows], label="V2-R P50")
    ax.plot(local.iloc[:fan_rows], test["price_gbp_mwh"].iloc[:fan_rows], label="Observed APXMIDP")
    ax.set_title("V2-R probabilistic price forecast on untouched hold-out")
    ax.set_ylabel("GBP/MWh")
    ax.set_xlabel("GB delivery time")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output / "price_probabilistic_fan.png", dpi=200)
    plt.close(fig)

    renew_rows = min(len(test), 48 * 7)
    observed_wind = (
        pd.to_numeric(test["embedded_wind_mw"], errors="coerce")
        + pd.to_numeric(test["transmission_wind_mw"], errors="coerce")
    )
    predicted_wind = (
        component_predictions["embedded_wind_mw"]
        + component_predictions["transmission_wind_mw"]
    )
    fig, ax = plt.subplots(figsize=(13, 5.5))
    ax.plot(local.iloc[:renew_rows], observed_wind.iloc[:renew_rows], label="Observed total wind")
    ax.plot(local.iloc[:renew_rows], predicted_wind.iloc[:renew_rows], label="Predicted total wind")
    ax.plot(local.iloc[:renew_rows], test["embedded_solar_mw"].iloc[:renew_rows], label="Observed embedded solar")
    ax.plot(local.iloc[:renew_rows], component_predictions["embedded_solar_mw"].iloc[:renew_rows], label="Predicted embedded solar")
    ax.set_title("Renewable-generation forecasts on untouched V2-R hold-out")
    ax.set_ylabel("MW")
    ax.set_xlabel("GB delivery time")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output / "renewables_observed_vs_predicted.png", dpi=200)
    plt.close(fig)

    daily = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(test["timestamp"], utc=True),
            "model_abs_error": (price["prediction"] - test["price_gbp_mwh"]).abs(),
            "persistence_abs_error": (price["persistence"] - test["price_gbp_mwh"]).abs(),
        }
    )
    daily["date"] = daily["timestamp"].dt.tz_convert("Europe/London").dt.date
    daily = daily.groupby("date")[["model_abs_error", "persistence_abs_error"]].mean()
    fig, ax = plt.subplots(figsize=(13, 5.5))
    ax.plot(daily.index, daily["model_abs_error"], label="V2-R")
    ax.plot(daily.index, daily["persistence_abs_error"], label="D-2 persistence")
    ax.set_title("Daily MAE across the untouched 90-day hold-out")
    ax.set_ylabel("MAE (GBP/MWh)")
    ax.set_xlabel("GB delivery date")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output / "daily_mae_v2_vs_persistence.png", dpi=200)
    plt.close(fig)

    top_gain = importance.head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(top_gain["feature"], top_gain["gain_percent"])
    ax.set_title("V2-R price-model feature importance by LightGBM gain")
    ax.set_xlabel("Gain importance (%)")
    fig.tight_layout()
    fig.savefig(output / "feature_importance_gain.png", dpi=200)
    plt.close(fig)

    top_shap = shap_summary.head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(top_shap["feature"], top_shap["mean_abs_contribution"])
    ax.set_title("V2-R mean absolute TreeSHAP contribution on untouched hold-out")
    ax.set_xlabel("Mean absolute contribution on model scale")
    fig.tight_layout()
    fig.savefig(output / "feature_importance_shap.png", dpi=200)
    plt.close(fig)


def run_analysis(
    dataset_path: str | Path,
    output_dir: str | Path,
    holdout_rows: int = 4320,
    validation_rows: int = 1440,
    time_series_splits: int = 5,
    scenarios: int = 1000,
) -> dict:
    frame = pd.read_parquet(dataset_path).copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame = frame.sort_values("timestamp").set_index("timestamp", drop=False)

    # Match the feature-preparation path used by the production training CLI.
    # The paper analysis must evaluate the same model inputs as the released
    # candidate rather than a reduced raw-feature variant.
    frame = add_cyclical_time_features(frame)
    frame = add_weather_features(frame)
    frame = add_market_regime_features(frame)
    frame = frame.reset_index(drop=True)
    if holdout_rows <= 0 or holdout_rows + validation_rows >= len(frame):
        raise ValueError("Insufficient rows for pre-holdout validation plus final holdout")

    profile, component_targets = _component_targets(frame)
    input_features = choose_numeric_features(frame, BASE_NON_FEATURE_COLUMNS)
    market_features = [c for c in input_features if _is_price_layer_feature(c)]
    component_features = [c for c in input_features if c not in market_features]

    pre = frame.iloc[:-holdout_rows].copy()
    test = frame.iloc[-holdout_rows:].copy().reset_index(drop=True)

    stacked_pre = pd.DataFrame(index=pre.index)
    component_errors = pd.DataFrame(index=pre.index)
    component_predictions = pd.DataFrame(index=test.index)
    component_metrics: dict[str, dict] = {}

    for target in component_targets:
        oof = expanding_oof_predictions(
            pre, component_features, target, n_splits=time_series_splits
        )
        stacked_pre[target] = oof
        component_errors[target] = pd.to_numeric(pre[target], errors="coerce") - oof

        fitted = train_regressor(pre, component_features, target)
        predicted = pd.Series(fitted.predict(test), index=test.index, dtype=float)
        if target not in SIGNED_COMPONENT_TARGETS:
            predicted = predicted.clip(lower=0.0)
        component_predictions[target] = predicted

        actual = pd.to_numeric(test[target], errors="coerce")
        persistence = _persistence(frame, target, test["timestamp"])
        component_metrics[target] = _metrics(actual, predicted, persistence)

    price_training = pre.drop(columns=component_targets, errors="ignore").copy()
    for target in component_targets:
        price_training[target] = stacked_pre[target]
    price_training = _add_stacked_balance_features(price_training)

    price_test = test.drop(columns=component_targets, errors="ignore").copy()
    for target in component_targets:
        price_test[target] = component_predictions[target].to_numpy()
    price_test = _add_stacked_balance_features(price_test)

    price_features = list(
        dict.fromkeys(
            [
                *component_features,
                *market_features,
                *component_targets,
                "total_wind_mw",
                "renewable_mw",
                "residual_before_nuclear_mw",
                "residual_after_nuclear_mw",
                "net_system_short_mw",
            ]
        )
    )
    price_features = [c for c in price_features if c in price_training]

    transform_validation = {}
    for transform in ("identity", "arcsinh"):
        transform_validation[transform] = chronological_holdout_score(
            price_training,
            price_features,
            "price_gbp_mwh",
            validation_rows,
            transform=transform,
            scale=50.0,
        )
    selected_transform = min(
        transform_validation,
        key=lambda name: transform_validation[name]["model_mae"],
    )

    price_model = train_regressor(
        price_training,
        price_features,
        "price_gbp_mwh",
        transform=selected_transform,
        scale=50.0,
    )
    price_prediction = pd.Series(price_model.predict(price_test), index=test.index, dtype=float)
    price_persistence = _persistence(frame, "price_gbp_mwh", test["timestamp"])
    price_actual = pd.to_numeric(test["price_gbp_mwh"], errors="coerce")
    price_metrics = _metrics(price_actual, price_prediction, price_persistence)

    price_oof = expanding_oof_predictions(
        price_training,
        price_features,
        "price_gbp_mwh",
        n_splits=time_series_splits,
        transform=selected_transform,
        scale=50.0,
    )
    component_errors["price_error_gbp_mwh"] = (
        pd.to_numeric(pre["price_gbp_mwh"], errors="coerce") - price_oof
    )
    error_rows = component_errors.dropna(how="any")

    component_scenarios = bootstrap_error_scenarios(
        price_test,
        error_rows,
        component_targets,
        scenarios=scenarios,
        random_seed=42,
        price_error_column="price_error_gbp_mwh",
    )
    scenario_result = run_price_monte_carlo(price_test, component_scenarios, price_model)
    prob = probabilistic_summary(
        price_actual,
        scenario_result.quantiles["p10"],
        scenario_result.quantiles["p50"],
        scenario_result.quantiles["p90"],
        scenario_result.price_paths,
    )

    price_output = pd.DataFrame(
        {
            "timestamp": test["timestamp"],
            "actual": price_actual,
            "prediction": price_prediction,
            "persistence": price_persistence,
            "p10": scenario_result.quantiles["p10"].to_numpy(),
            "p50": scenario_result.quantiles["p50"].to_numpy(),
            "p90": scenario_result.quantiles["p90"].to_numpy(),
            "negative_probability": scenario_result.negative_probability.to_numpy(),
        }
    )

    booster = price_model.model.booster_
    gain = booster.feature_importance(importance_type="gain").astype(float)
    gain_percent = 100.0 * gain / gain.sum() if gain.sum() else gain
    importance = (
        pd.DataFrame({"feature": price_features, "gain": gain, "gain_percent": gain_percent})
        .sort_values("gain", ascending=False)
        .reset_index(drop=True)
    )
    contributions = booster.predict(price_test[price_features], pred_contrib=True)
    if contributions.shape[1] == len(price_features) + 1:
        contributions = contributions[:, :-1]
    shap_summary = (
        pd.DataFrame(
            {
                "feature": price_features,
                "mean_abs_contribution": np.mean(np.abs(contributions), axis=0),
            }
        )
        .sort_values("mean_abs_contribution", ascending=False)
        .reset_index(drop=True)
    )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    price_output.to_csv(output / "v2r_price_holdout_predictions.csv", index=False)

    component_table = test[["timestamp", *component_targets]].copy()
    for target in component_targets:
        component_table[f"predicted_{target}"] = component_predictions[target].to_numpy()
    component_table.to_csv(output / "v2r_component_holdout_predictions.csv", index=False)
    importance.to_csv(output / "v2r_price_feature_importance_gain.csv", index=False)
    shap_summary.to_csv(output / "v2r_price_shap_summary.csv", index=False)

    _save_figures(
        test,
        price_output,
        component_predictions,
        importance,
        shap_summary,
        output / "figures",
    )

    results = {
        "analysis_revision": "paper-v2r-v2",
        "model_profile": profile,
        "dataset_rows": int(len(frame)),
        "training_and_validation_rows": int(len(pre)),
        "untouched_holdout_rows": int(len(test)),
        "holdout_start_utc": test["timestamp"].min().isoformat(),
        "holdout_end_utc": test["timestamp"].max().isoformat(),
        "transform_selection": {
            "selection_window_rows": int(validation_rows),
            "selection_window_is_pre_holdout": True,
            "candidates": transform_validation,
            "selected": selected_transform,
        },
        "price": price_metrics,
        "probabilistic": prob,
        "components": component_metrics,
        "top_gain_features": importance.head(20).to_dict("records"),
        "top_shap_features": shap_summary.head(20).to_dict("records"),
        "scenario_count": int(scenarios),
        "persistence_definition": "exact timestamp minus 48 hours (fully observable at D-1 issue)",
        "preprocessing_equivalence": "matches gb-v2 train: cyclical time + weather + optional market-regime features",
        "gas_eua_status": "inactive unless point-in-time market_regime.parquet is explicitly supplied",
    }
    (output / "v2r_results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run frozen V2-R manuscript analysis")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--holdout-rows", type=int, default=4320)
    parser.add_argument("--validation-rows", type=int, default=1440)
    parser.add_argument("--time-series-splits", type=int, default=5)
    parser.add_argument("--scenarios", type=int, default=1000)
    args = parser.parse_args()
    result = run_analysis(
        args.dataset,
        args.output,
        args.holdout_rows,
        args.validation_rows,
        args.time_series_splits,
        args.scenarios,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
