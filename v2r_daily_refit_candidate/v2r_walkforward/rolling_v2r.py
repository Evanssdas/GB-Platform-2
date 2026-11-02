"""Daily-refitted retrospective V2-R. Use as gb_platform_v2.rolling_v2r.

No inference of prospective independence. Uses a preselected identity transform,
chronological out-of-fold physical predictions, and local D-1 13:00 cutoffs.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .reviewer_upgrade import _prepare, _lag_exact, _median_d2_d8, _point_metrics
from .rolling_lear import issue_for_date
from .models import train_regressor
from .validation import expanding_oof_predictions
from .features import choose_numeric_features
from .pipeline import BASE_NON_FEATURE_COLUMNS, SIGNED_COMPONENT_TARGETS, _add_stacked_balance_features, _component_targets, _is_price_layer_feature


def run(dataset, output, start="2026-08-02", end="2026-10-30", lookback_days=365, min_train_rows=6000, splits=5):
    frame = _prepare(dataset)
    _, targets = _component_targets(frame)
    features = choose_numeric_features(frame, BASE_NON_FEATURE_COLUMNS | {"local_slot"})
    physical = [c for c in features if not _is_price_layer_feature(c)]
    market = [c for c in features if _is_price_layer_feature(c)]
    if not physical:
        raise ValueError("Missing physical inputs")
    # Out-of-fold historical component forecasts ensure that the price model
    # never sees in-sample component estimates.
    stacked = frame.drop(columns=targets, errors="ignore").copy()
    for target in targets:
        pred = expanding_oof_predictions(frame, physical, target, n_splits=splits)
        if target not in SIGNED_COMPONENT_TARGETS:
            pred = pred.clip(lower=0)
        stacked[target] = pred
    stacked = _add_stacked_balance_features(stacked)
    balance = ["total_wind_mw", "renewable_mw", "residual_before_nuclear_mw", "residual_after_nuclear_mw", "net_system_short_mw"]
    price_features = list(dict.fromkeys(c for c in physical + market + targets + balance if c in stacked))
    days = sorted(d for d in frame.local_date.unique() if pd.Timestamp(start).date() <= d <= pd.Timestamp(end).date())
    predictions, daily = [], []
    for day in days:
        issue = issue_for_date(day)
        train = (frame.timestamp < issue) & (frame.timestamp >= issue - pd.Timedelta(days=lookback_days))
        price_train = train & stacked[targets].notna().all(axis=1) & frame.price_gbp_mwh.notna()
        test = frame.local_date == day
        if price_train.sum() < min_train_rows or not test.any():
            daily.append(dict(delivery_date=str(day), status="insufficient_history", rows=int(price_train.sum())))
            continue
        assert frame.loc[train, "timestamp"].max() < issue
        assert frame.loc[price_train, "timestamp"].max() < issue
        future = frame.loc[test].drop(columns=targets, errors="ignore").copy()
        for target in targets:
            tr = frame.loc[train & frame[target].notna()]
            model = train_regressor(tr, physical, target)
            values = model.predict(frame.loc[test])
            if target not in SIGNED_COMPONENT_TARGETS:
                values = np.maximum(values, 0)
            future[target] = values
        future = _add_stacked_balance_features(future)
        price_model = train_regressor(stacked.loc[price_train], price_features, "price_gbp_mwh", transform="identity")
        pred = price_model.predict(future)
        d2 = _lag_exact(frame, "price_gbp_mwh", frame.loc[test, "timestamp"], 2)
        med = _median_d2_d8(frame, frame.loc[test, "timestamp"])
        for idx, p, b, m in zip(frame.index[test], pred, d2, med):
            predictions.append(dict(timestamp=frame.at[idx, "timestamp"].isoformat(), delivery_date=str(day), issue_utc=issue.isoformat(), actual=float(frame.at[idx, "price_gbp_mwh"]), daily_v2r=float(p), d2=float(b), median_d2_d8=float(m)))
        daily.append(dict(delivery_date=str(day), status="evaluated", issue_utc=issue.isoformat(), price_train_rows=int(price_train.sum()), periods=int(test.sum())))
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    result = pd.DataFrame(predictions)
    result.to_csv(out / "daily_v2r_predictions.csv", index=False)
    pd.DataFrame(daily).to_csv(out / "daily_v2r_manifest.csv", index=False)
    if result.empty:
        raise ValueError("No eligible daily predictions")
    metrics = dict(protocol="retrospective daily-refit V2-R", prospective=False, evaluated_days=int(result.delivery_date.nunique()), evaluated_periods=len(result), daily_v2r=_point_metrics(result.actual, result.daily_v2r), d2=_point_metrics(result.actual, result.d2), d2_d8_median=_point_metrics(result.actual, result.median_d2_d8))
    (out / "daily_v2r_results.json").write_text(json.dumps(metrics, indent=2))
    return metrics

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--start", default="2026-08-02")
    p.add_argument("--end", default="2026-10-30")
    args = p.parse_args()
    print(json.dumps(run(args.dataset, args.output, args.start, args.end), indent=2))
