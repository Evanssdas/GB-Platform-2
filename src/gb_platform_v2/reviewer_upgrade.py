"""Reviewer-requested robustness analyses for the GB Platform 2 manuscript.

This module reuses the frozen V2-R point-in-time dataset. It does not recollect
or revise historical inputs. Analyses are separated into:
- primary whole-settlement-day V2-R evaluation;
- stronger observable benchmarks and HAC/DM comparisons;
- secondary issue-time-safe rolling calibration;
- post-hoc mechanism/ablation diagnostics.
"""

from __future__ import annotations

import argparse
import json
from math import erf, sqrt
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LassoCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

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


LONDON_TZ = "Europe/London"


def _prepare(path: str | Path) -> pd.DataFrame:
    frame = pd.read_parquet(path).copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame = frame.sort_values("timestamp").set_index("timestamp", drop=False)
    frame = add_cyclical_time_features(frame)
    frame = add_weather_features(frame)
    frame = add_market_regime_features(frame)
    frame["local_date"] = frame["timestamp"].dt.tz_convert(LONDON_TZ).dt.date
    frame["local_slot"] = (
        frame["timestamp"].dt.tz_convert(LONDON_TZ).dt.hour * 2
        + frame["timestamp"].dt.tz_convert(LONDON_TZ).dt.minute // 30
    )
    return frame.reset_index(drop=True)


def _last_complete_local_days(frame: pd.DataFrame, days: int = 90) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    dates = sorted(frame["local_date"].dropna().unique())
    if len(dates) <= days:
        raise ValueError("Insufficient local settlement days")
    selected = dates[-days:]
    test = frame.loc[frame["local_date"].isin(selected)].copy().reset_index(drop=True)
    pre = frame.loc[frame["local_date"] < selected[0]].copy().reset_index(drop=True)
    if test["local_date"].nunique() != days:
        raise ValueError("Whole-day holdout construction failed")
    return pre, test, selected


def _lag_exact(frame: pd.DataFrame, column: str, timestamps: pd.Series, days: int) -> pd.Series:
    history = pd.Series(
        pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float),
        index=pd.DatetimeIndex(frame["timestamp"]),
    )
    lookup = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True)) - pd.Timedelta(days=days)
    return pd.Series(history.reindex(lookup).to_numpy(dtype=float), index=timestamps.index)


def _median_d2_d8(frame: pd.DataFrame, timestamps: pd.Series, column: str = "price_gbp_mwh") -> pd.Series:
    values = pd.concat(
        [_lag_exact(frame, column, timestamps, days) for days in range(2, 9)],
        axis=1,
    )
    return values.median(axis=1, skipna=False)


def _point_metrics(actual: pd.Series, prediction: pd.Series) -> dict:
    valid = actual.notna() & prediction.notna()
    y = actual.loc[valid].astype(float)
    p = prediction.loc[valid].astype(float)
    return {
        "rows": int(valid.sum()),
        "mae": float(np.mean(np.abs(p - y))),
        "rmse": float(np.sqrt(np.mean((p - y) ** 2))),
        "bias": float(np.mean(p - y)),
    }


def _hac_dm(actual: pd.Series, model: pd.Series, benchmark: pd.Series, lag: int = 47) -> dict:
    valid = actual.notna() & model.notna() & benchmark.notna()
    y = actual.loc[valid].to_numpy(dtype=float)
    m = model.loc[valid].to_numpy(dtype=float)
    b = benchmark.loc[valid].to_numpy(dtype=float)
    d = np.abs(m - y) - np.abs(b - y)
    n = len(d)
    mean_d = float(np.mean(d))
    centered = d - mean_d
    gamma0 = float(np.dot(centered, centered) / n)
    lrv = gamma0
    for k in range(1, min(lag, n - 1) + 1):
        gamma = float(np.dot(centered[k:], centered[:-k]) / n)
        weight = 1.0 - k / (lag + 1.0)
        lrv += 2.0 * weight * gamma
    se = float(np.sqrt(max(lrv, 0.0) / n))
    statistic = mean_d / se if se > 0 else float("nan")
    p_value = 2.0 * (1.0 - 0.5 * (1.0 + erf(abs(statistic) / sqrt(2.0)))) if np.isfinite(statistic) else float("nan")
    return {
        "rows": n,
        "mean_absolute_loss_difference_model_minus_benchmark": mean_d,
        "hac_lag_half_hours": int(lag),
        "statistic": float(statistic),
        "normal_approx_two_sided_p": float(p_value),
        "interpretation": "negative loss difference favours model; positive favours benchmark",
    }


def _component_stack(
    full: pd.DataFrame,
    pre: pd.DataFrame,
    test: pd.DataFrame,
    component_features: list[str],
    targets: list[str],
    time_series_splits: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    stacked_pre = pd.DataFrame(index=pre.index)
    component_errors = pd.DataFrame(index=pre.index)
    predicted_test = pd.DataFrame(index=test.index)
    for target in targets:
        oof = expanding_oof_predictions(
            pre, component_features, target, n_splits=time_series_splits
        )
        stacked_pre[target] = oof
        component_errors[target] = pd.to_numeric(pre[target], errors="coerce") - oof
        fitted = train_regressor(pre, component_features, target)
        pred = pd.Series(fitted.predict(test), index=test.index, dtype=float)
        if target not in SIGNED_COMPONENT_TARGETS:
            pred = pred.clip(lower=0.0)
        predicted_test[target] = pred
    return stacked_pre, component_errors, predicted_test


def _price_frames(
    pre: pd.DataFrame,
    test: pd.DataFrame,
    stacked_pre: pd.DataFrame,
    predicted_test: pd.DataFrame,
    component_features: list[str],
    market_features: list[str],
    targets: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    price_pre = pre.drop(columns=targets, errors="ignore").copy()
    price_test = test.drop(columns=targets, errors="ignore").copy()
    for target in targets:
        price_pre[target] = stacked_pre[target].to_numpy()
        price_test[target] = predicted_test[target].to_numpy()
    price_pre = _add_stacked_balance_features(price_pre)
    price_test = _add_stacked_balance_features(price_test)
    features = list(
        dict.fromkeys(
            [
                *component_features,
                *market_features,
                *targets,
                "total_wind_mw",
                "renewable_mw",
                "residual_before_nuclear_mw",
                "residual_after_nuclear_mw",
                "net_system_short_mw",
            ]
        )
    )
    features = [c for c in features if c in price_pre.columns]
    return price_pre, price_test, features


def _select_transform(price_pre: pd.DataFrame, features: list[str], validation_rows: int) -> tuple[str, dict]:
    scores = {}
    for transform in ("identity", "arcsinh"):
        scores[transform] = chronological_holdout_score(
            price_pre,
            features,
            "price_gbp_mwh",
            validation_rows,
            transform=transform,
            scale=50.0,
        )
    selected = min(scores, key=lambda name: scores[name]["model_mae"])
    return selected, scores


def _lear_style_benchmark(full: pd.DataFrame, pre: pd.DataFrame, test: pd.DataFrame) -> pd.Series:
    """Observable half-hourly LASSO-ARX benchmark inspired by LEAR.

    The standard LEAR benchmark uses LASSO with autoregressive and exogenous
    information. Because a complete D-1 price profile is not observable at the
    study's 13:00 issue time, this adaptation uses only fully observable D-2,
    D-3 and D-7 price/component lags plus calendar variables. One LASSO model is
    estimated per local half-hour slot.
    """
    base_columns = [
        "price_gbp_mwh",
        "demand_mw",
        "embedded_wind_mw",
        "embedded_solar_mw",
        "transmission_wind_mw",
        "nuclear_mw",
        "net_import_mw",
    ]

    def design(rows: pd.DataFrame) -> pd.DataFrame:
        x = pd.DataFrame(index=rows.index)
        for column in base_columns:
            for days in (2, 3, 7):
                x[f"{column}_d{days}"] = _lag_exact(full, column, rows["timestamp"], days)
        x["price_median_d2_d8"] = _median_d2_d8(full, rows["timestamp"])
        x["dow_sin"] = rows["dow_sin"].to_numpy()
        x["dow_cos"] = rows["dow_cos"].to_numpy()
        x["year_sin"] = rows["year_sin"].to_numpy()
        x["year_cos"] = rows["year_cos"].to_numpy()
        return x

    x_pre = design(pre)
    x_test = design(test)
    prediction = pd.Series(np.nan, index=test.index, dtype=float)

    for slot in sorted(test["local_slot"].unique()):
        tr_idx = pre.index[pre["local_slot"].eq(slot)]
        te_idx = test.index[test["local_slot"].eq(slot)]
        if len(te_idx) == 0:
            continue
        Xtr = x_pre.loc[tr_idx]
        ytr = pd.to_numeric(pre.loc[tr_idx, "price_gbp_mwh"], errors="coerce")
        valid = Xtr.notna().all(axis=1) & ytr.notna()
        Xte = x_test.loc[te_idx]
        valid_test = Xte.notna().all(axis=1)
        if valid.sum() < 100 or not valid_test.any():
            continue
        model = make_pipeline(
            StandardScaler(),
            LassoCV(
                alphas=np.logspace(-3, 2, 60),
                cv=5,
                max_iter=20000,
                random_state=42,
            ),
        )
        model.fit(Xtr.loc[valid], ytr.loc[valid])
        prediction.loc[te_idx[valid_test.to_numpy()]] = model.predict(Xte.loc[valid_test])
    return prediction


def _rolling_calibration(
    timestamps: pd.Series,
    actual: pd.Series,
    p10: pd.Series,
    p50: pd.Series,
    p90: pd.Series,
    lookback_days: int = 7,
    min_rows: int = 96,
    target_coverage: float = 0.80,
) -> pd.DataFrame:
    ts = pd.to_datetime(timestamps, utc=True)
    out = pd.DataFrame(
        {
            "timestamp": ts,
            "actual": pd.to_numeric(actual, errors="coerce"),
            "p10": pd.to_numeric(p10, errors="coerce"),
            "p50": pd.to_numeric(p50, errors="coerce"),
            "p90": pd.to_numeric(p90, errors="coerce"),
        }
    )
    out["cal_p10"] = np.nan
    out["cal_p50"] = np.nan
    out["cal_p90"] = np.nan
    out["bias_shift"] = np.nan
    out["dispersion_scale"] = np.nan

    for i, row in out.iterrows():
        # A D-1 forecast is issued at 13:00 Europe/London on the
        # PREVIOUS local calendar date, not at the delivery timestamp.
        # DateOffset preserves the local calendar across DST transitions.
        delivery_local = row["timestamp"].tz_convert(LONDON_TZ)
        issue_local = (
            delivery_local.normalize() - pd.DateOffset(days=1)
            + pd.Timedelta(hours=13)
        )
        issue_utc = issue_local.tz_convert("UTC")
        left = issue_utc - pd.Timedelta(days=lookback_days)
        history = out.loc[
            out["timestamp"].lt(issue_utc)
            & out["timestamp"].ge(left)
            & out["actual"].notna()
        ]
        if len(history) < min_rows:
            continue
        med_error = float(np.nanmedian(history["p50"] - history["actual"]))
        bias = -med_error
        center_hist = history["p50"] + bias
        miss = history["actual"] - center_hist
        lower_w = (history["p50"] - history["p10"]).clip(lower=1e-6)
        upper_w = (history["p90"] - history["p50"]).clip(lower=1e-6)
        required = np.where(
            miss < 0,
            np.abs(miss.to_numpy()) / lower_w.to_numpy(),
            np.abs(miss.to_numpy()) / upper_w.to_numpy(),
        )
        required = required[np.isfinite(required)]
        scale = 1.0
        if len(required) >= min_rows:
            scale = float(np.quantile(required, target_coverage))
            scale = float(np.clip(scale, 1.0, 4.0))
        center = float(row["p50"] + bias)
        out.at[i, "cal_p50"] = center
        out.at[i, "cal_p10"] = center - scale * float(row["p50"] - row["p10"])
        out.at[i, "cal_p90"] = center + scale * float(row["p90"] - row["p50"])
        out.at[i, "bias_shift"] = bias
        out.at[i, "dispersion_scale"] = scale
    return out


def run(
    dataset: str | Path,
    output_dir: str | Path,
    whole_days: int = 90,
    validation_rows: int = 1440,
    time_series_splits: int = 5,
    scenarios: int = 1000,
) -> dict:
    frame = _prepare(dataset)
    pre, test, holdout_dates = _last_complete_local_days(frame, whole_days)
    profile, targets = _component_targets(frame)
    input_features = choose_numeric_features(frame, BASE_NON_FEATURE_COLUMNS | {"local_slot"})
    market_features = [c for c in input_features if _is_price_layer_feature(c)]
    component_features = [
        c for c in input_features
        if c not in market_features and c not in {"local_slot"}
    ]

    stacked_pre, component_errors, component_test = _component_stack(
        frame, pre, test, component_features, targets, time_series_splits
    )
    price_pre, price_test, price_features = _price_frames(
        pre, test, stacked_pre, component_test, component_features, market_features, targets
    )
    selected_transform, transform_scores = _select_transform(
        price_pre, price_features, validation_rows
    )
    price_model = train_regressor(
        price_pre,
        price_features,
        "price_gbp_mwh",
        transform=selected_transform,
        scale=50.0,
    )
    prediction = pd.Series(price_model.predict(price_test), index=test.index, dtype=float)
    actual = pd.to_numeric(test["price_gbp_mwh"], errors="coerce")

    d2 = _lag_exact(frame, "price_gbp_mwh", test["timestamp"], 2)
    d7 = _lag_exact(frame, "price_gbp_mwh", test["timestamp"], 7)
    median7 = _median_d2_d8(frame, test["timestamp"])
    lear = _lear_style_benchmark(frame, pre, test)

    component_metrics = {}
    for target in targets:
        component_actual = pd.to_numeric(test[target], errors="coerce")
        component_pred = component_test[target]
        component_d2 = _lag_exact(frame, target, test["timestamp"], 2)
        component_d7 = _lag_exact(frame, target, test["timestamp"], 7)
        component_metrics[target] = {
            "model": _point_metrics(component_actual, component_pred),
            "d2": _point_metrics(component_actual, component_d2),
            "d7": _point_metrics(component_actual, component_d7),
        }

    point = {
        "v2r": _point_metrics(actual, prediction),
        "d2": _point_metrics(actual, d2),
        "d7": _point_metrics(actual, d7),
        "median_d2_d8": _point_metrics(actual, median7),
        "lear_style_lasso_arx": _point_metrics(actual, lear),
    }
    dm = {
        "v2r_vs_d2": _hac_dm(actual, prediction, d2),
        "v2r_vs_d7": _hac_dm(actual, prediction, d7),
        "v2r_vs_median_d2_d8": _hac_dm(actual, prediction, median7),
        "v2r_vs_lear_style_lasso_arx": _hac_dm(actual, prediction, lear),
    }

    price_oof = expanding_oof_predictions(
        price_pre,
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
        targets,
        scenarios=scenarios,
        random_seed=42,
        price_error_column="price_error_gbp_mwh",
    )
    scenario_result = run_price_monte_carlo(price_test, component_scenarios, price_model)
    prob = probabilistic_summary(
        actual,
        scenario_result.quantiles["p10"],
        scenario_result.quantiles["p50"],
        scenario_result.quantiles["p90"],
        scenario_result.price_paths,
    )
    p10 = scenario_result.quantiles["p10"].reset_index(drop=True)
    p50 = scenario_result.quantiles["p50"].reset_index(drop=True)
    p90 = scenario_result.quantiles["p90"].reset_index(drop=True)
    actual_r = actual.reset_index(drop=True)
    prob["below_p10_rate"] = float(np.mean(actual_r.to_numpy() < p10.to_numpy()))
    prob["above_p90_rate"] = float(np.mean(actual_r.to_numpy() > p90.to_numpy()))
    pit = np.mean(
        scenario_result.price_paths <= actual_r.to_numpy()[None, :], axis=0
    )
    prob["pit_mean"] = float(np.mean(pit))
    prob["pit_std"] = float(np.std(pit))

    calibration = _rolling_calibration(
        test["timestamp"].reset_index(drop=True), actual_r, p10, p50, p90
    )
    eligible = calibration["cal_p50"].notna()
    cal_actual = calibration.loc[eligible, "actual"]
    cal_p50 = calibration.loc[eligible, "cal_p50"]
    cal_d2 = d2.reset_index(drop=True).loc[eligible]
    cal_median = median7.reset_index(drop=True).loc[eligible]
    cal_metrics = {
        "rows": int(eligible.sum()),
        "point": _point_metrics(cal_actual, cal_p50),
        "d2_same_rows": _point_metrics(cal_actual, cal_d2),
        "median_d2_d8_same_rows": _point_metrics(cal_actual, cal_median),
        "coverage": float(
            cal_actual.between(
                calibration.loc[eligible, "cal_p10"],
                calibration.loc[eligible, "cal_p90"],
            ).mean()
        ),
        "mean_dispersion_scale": float(calibration.loc[eligible, "dispersion_scale"].mean()),
        "median_bias_shift": float(calibration.loc[eligible, "bias_shift"].median()),
        "dm_vs_d2": _hac_dm(cal_actual, cal_p50, cal_d2),
        "dm_vs_median_d2_d8": _hac_dm(cal_actual, cal_p50, cal_median),
    }

    # Post-hoc residual-to-anchor ablation.
    delta_pre = price_pre.copy()
    delta_test = price_test.copy()
    delta_pre["price_delta_d2"] = (
        pd.to_numeric(pre["price_gbp_mwh"], errors="coerce").to_numpy()
        - _lag_exact(frame, "price_gbp_mwh", pre["timestamp"], 2).to_numpy()
    )
    delta_model = train_regressor(
        delta_pre.dropna(subset=["price_delta_d2"]),
        price_features,
        "price_delta_d2",
        transform="identity",
    )
    delta_pred = pd.Series(delta_model.predict(delta_test), index=test.index, dtype=float)
    residual_anchor_prediction = d2 + delta_pred
    residual_anchor = {
        "status": "post_hoc_ablation_not_primary",
        **_point_metrics(actual, residual_anchor_prediction),
        "dm_vs_d2": _hac_dm(actual, residual_anchor_prediction, d2),
    }

    # Post-hoc nuclear D-2 hybrid: replace nuclear OOF/test path with observable D-2.
    hybrid_pre_stack = stacked_pre.copy()
    hybrid_test_components = component_test.copy()
    hybrid_pre_stack["nuclear_mw"] = _lag_exact(
        frame, "nuclear_mw", pre["timestamp"], 2
    ).to_numpy()
    hybrid_test_components["nuclear_mw"] = _lag_exact(
        frame, "nuclear_mw", test["timestamp"], 2
    ).to_numpy()
    h_pre, h_test, h_features = _price_frames(
        pre, test, hybrid_pre_stack, hybrid_test_components,
        component_features, market_features, targets
    )
    h_model = train_regressor(
        h_pre.dropna(subset=["nuclear_mw"]),
        h_features,
        "price_gbp_mwh",
        transform=selected_transform,
        scale=50.0,
    )
    h_pred = pd.Series(h_model.predict(h_test), index=test.index, dtype=float)
    nuclear_d2_mae = _point_metrics(
        pd.to_numeric(test["nuclear_mw"], errors="coerce"),
        _lag_exact(frame, "nuclear_mw", test["timestamp"], 2),
    )
    nuclear_d7_mae = _point_metrics(
        pd.to_numeric(test["nuclear_mw"], errors="coerce"),
        _lag_exact(frame, "nuclear_mw", test["timestamp"], 7),
    )
    hybrid = {
        "status": "post_hoc_governance_ablation_not_primary",
        "nuclear_d2": nuclear_d2_mae,
        "nuclear_d7": nuclear_d7_mae,
        "price_with_nuclear_d2_hybrid": _point_metrics(actual, h_pred),
        "dm_price_hybrid_vs_d2": _hac_dm(actual, h_pred, d2),
    }

    train_price = pd.to_numeric(pre["price_gbp_mwh"], errors="coerce").dropna()
    test_price = actual.dropna()
    q_levels = [0.10, 0.50, 0.90, 0.95, 0.99]
    train_q = train_price.quantile(q_levels)
    test_q = test_price.quantile(q_levels)
    distribution_shift = {
        "training_mean": float(train_price.mean()),
        "holdout_mean": float(test_price.mean()),
        "training_min": float(train_price.min()),
        "training_max": float(train_price.max()),
        "holdout_min": float(test_price.min()),
        "holdout_max": float(test_price.max()),
        "training_quantiles": {str(q): float(train_q.loc[q]) for q in q_levels},
        "holdout_quantiles": {str(q): float(test_q.loc[q]) for q in q_levels},
        "holdout_fraction_above_training_p90": float(np.mean(test_price > train_q.loc[0.90])),
        "holdout_fraction_above_training_p95": float(np.mean(test_price > train_q.loc[0.95])),
        "holdout_fraction_above_training_max": float(np.mean(test_price > train_price.max())),
        "prediction_min": float(prediction.min()),
        "prediction_max": float(prediction.max()),
        "prediction_fraction_above_training_max": float(np.mean(prediction > train_price.max())),
    }

    output = Path(output_dir)
    (output / "figures").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "timestamp": test["timestamp"],
            "actual": actual,
            "v2r": prediction,
            "d2": d2,
            "d7": d7,
            "median_d2_d8": median7,
            "lear_style_lasso_arx": lear,
            "residual_anchor_post_hoc": residual_anchor_prediction,
            "nuclear_d2_hybrid_post_hoc": h_pred,
            "p10": p10.to_numpy(),
            "p50": p50.to_numpy(),
            "p90": p90.to_numpy(),
            "pit": pit,
        }
    ).to_csv(output / "reviewer_holdout_predictions.csv", index=False)
    calibration.to_csv(output / "reviewer_rolling_calibration.csv", index=False)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.hist(pit, bins=np.linspace(0, 1, 11), edgecolor="black")
    ax.axhline(len(pit) / 10.0, linestyle="--", label="Uniform expectation")
    ax.set_xlabel("PIT")
    ax.set_ylabel("Settlement periods")
    ax.set_title("V2-R PIT histogram on 90 complete settlement days")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output / "figures" / "pit_histogram.png", dpi=200)
    plt.close(fig)

    labels = ["V2-R", "D-2", "D-7", "D2-D8 median", "LEAR-style"]
    values = [
        point["v2r"]["mae"], point["d2"]["mae"], point["d7"]["mae"],
        point["median_d2_d8"]["mae"], point["lear_style_lasso_arx"]["mae"],
    ]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(labels, values)
    ax.set_ylabel("MAE (GBP/MWh)")
    ax.set_title("Competitive point-forecast benchmarks on 90 complete settlement days")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(output / "figures" / "competitive_benchmarks.png", dpi=200)
    plt.close(fig)

    results = {
        "analysis_revision": "reviewer-upgrade-v2-issue-time-correction",
        "model_profile": profile,
        "holdout_definition": "last 90 complete Europe/London settlement dates",
        "holdout_local_start": str(holdout_dates[0]),
        "holdout_local_end": str(holdout_dates[-1]),
        "holdout_rows": int(len(test)),
        "holdout_period_counts": {
            str(k): int(v)
            for k, v in test.groupby("local_date").size().value_counts().sort_index().items()
        },
        "selected_transform": selected_transform,
        "transform_validation": transform_scores,
        "point_benchmarks": point,
        "component_benchmarks": component_metrics,
        "dm_hac_tests": dm,
        "probabilistic_raw": prob,
        "rolling_calibration_secondary": cal_metrics,
        "residual_to_d2_post_hoc": residual_anchor,
        "nuclear_fallback_post_hoc": hybrid,
        "target_distribution_shift": distribution_shift,
        "lear_note": (
            "LEAR-style observable LASSO-ARX benchmark, adapted to the 13:00 issue-time "
            "constraint by excluding unobservable D-1 full-profile prices."
        ),
    }
    (output / "reviewer_upgrade_results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--whole-days", type=int, default=90)
    parser.add_argument("--validation-rows", type=int, default=1440)
    parser.add_argument("--time-series-splits", type=int, default=5)
    parser.add_argument("--scenarios", type=int, default=1000)
    args = parser.parse_args()
    print(json.dumps(run(
        args.dataset, args.output, args.whole_days, args.validation_rows,
        args.time_series_splits, args.scenarios
    ), indent=2, default=str))


if __name__ == "__main__":
    main()
