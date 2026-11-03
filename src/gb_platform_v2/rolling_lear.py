"""Issue-time-audited rolling-origin LEAR-style benchmark (not canonical LEAR).

Each delivery day's model is fitted only to settlement outcomes with delivery
timestamps strictly before the previous local day's 13:00 forecast issue.
All test covariates are historical same-period D-2/D-3/D-7 prices, the D2-D8
median, and known calendar variables. Model-selection periods use past-only
TimeSeriesSplit rather than shuffled folds.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LassoCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .reviewer_upgrade import _prepare, _lag_exact, _median_d2_d8, _point_metrics

TZ = "Europe/London"


def issue_for_date(day: object) -> pd.Timestamp:
    # Build the prior *calendar* day's 13:00 wall-clock time before
    # localizing; timezone-aware midnight arithmetic shifts an hour at DST.
    issue_wall = pd.Timestamp(day) - pd.Timedelta(days=1) + pd.Timedelta(hours=13)
    return issue_wall.tz_localize(TZ).tz_convert("UTC")


def build_design(frame: pd.DataFrame) -> pd.DataFrame:
    """All predictors are known by the D-1 13:00 issue instant."""
    ts = frame["timestamp"]
    result = pd.DataFrame(index=frame.index)
    for days in (2, 3, 7):
        result[f"price_d{days}"] = _lag_exact(frame, "price_gbp_mwh", ts, days)
    result["price_median_d2_d8"] = _median_d2_d8(frame, ts)
    local = ts.dt.tz_convert(TZ)
    hour = local.dt.hour + local.dt.minute / 60
    dow = local.dt.dayofweek
    result["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    result["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    result["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    result["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    doy = local.dt.dayofyear
    result["year_sin"] = np.sin(2 * np.pi * doy / 365.25)
    result["year_cos"] = np.cos(2 * np.pi * doy / 365.25)
    return result


def run(dataset: str | Path, output: str | Path, *, start: str, end: str,
        lookback_days: int = 365, min_train_rows: int = 6000,
        alpha_grid: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0), publication_lag_minutes: int = 120) -> dict:
    frame = _prepare(dataset)
    X = build_design(frame)
    y = pd.to_numeric(frame["price_gbp_mwh"], errors="coerce")
    start_day, end_day = pd.Timestamp(start).date(), pd.Timestamp(end).date()
    dates = sorted(d for d in frame["local_date"].unique() if start_day <= d <= end_day)
    if not dates:
        raise ValueError("No delivery days in requested interval")
    records = []
    daily = []
    for day in dates:
        issue = issue_for_date(day)
        # Both the training target and the training features must exist.
        cutoff = issue - pd.Timedelta(days=lookback_days)
        latest_start = issue - pd.Timedelta(minutes=30 + publication_lag_minutes)
        tr = (frame["timestamp"] <= latest_start) & (frame["timestamp"] >= cutoff)
        tr &= y.notna() & X.notna().all(axis=1)
        te = (frame["local_date"] == day) & X.notna().all(axis=1)
        if int(tr.sum()) < min_train_rows:
            daily.append({"delivery_date": str(day), "status": "insufficient_history",
                          "train_rows": int(tr.sum()), "issue_utc": issue.isoformat()})
            continue
        if not te.any():
            daily.append({"delivery_date": str(day), "status": "missing_features",
                          "train_rows": int(tr.sum()), "issue_utc": issue.isoformat()})
            continue
        train_timestamps = frame.loc[tr, "timestamp"]
        assert train_timestamps.max() < issue
        model = make_pipeline(
            StandardScaler(),
            LassoCV(alphas=np.asarray(alpha_grid), cv=TimeSeriesSplit(n_splits=3),
                    max_iter=15000, random_state=42, n_jobs=1),
        )
        model.fit(X.loc[tr], y.loc[tr])
        pred = model.predict(X.loc[te])
        for index, forecast in zip(frame.index[te], pred):
            records.append({
                "timestamp": frame.at[index, "timestamp"].isoformat(),
                "delivery_date": str(day),
                "issue_utc": issue.isoformat(),
                "actual": float(y.loc[index]),
                "lear_rolling": float(forecast),
                "d2": float(X.at[index, "price_d2"]),
                "median_d2_d8": float(X.at[index, "price_median_d2_d8"]),
            })
        daily.append({"delivery_date": str(day), "status": "evaluated",
                      "train_rows": int(tr.sum()), "issue_utc": issue.isoformat(),
                      "evaluated_periods": int(te.sum()),
                      "selected_alpha": float(model[-1].alpha_)})
    predictions = pd.DataFrame(records)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(out / "rolling_lear_predictions.csv", index=False)
    pd.DataFrame(daily).to_csv(out / "rolling_lear_daily_manifest.csv", index=False)
    if predictions.empty:
        raise ValueError("No forecasts produced; check training warm-up and date range")
    metrics = {
        "protocol": "retrospective issue-time-safe, daily refit, adapted LEAR-style LASSO",
        "not_claimed_as": "canonical LEAR, prospective shadow, or adaptive V2-R",
        "lookback_days": lookback_days,
        "delivery_start": str(start_day),
        "delivery_end": str(end_day),
        "evaluated_days": int(predictions["delivery_date"].nunique()),
        "evaluated_periods": int(len(predictions)),
        "model": _point_metrics(predictions["actual"], predictions["lear_rolling"]),
        "d2_same_periods": _point_metrics(predictions["actual"], predictions["d2"]),
        "median_same_periods": _point_metrics(predictions["actual"], predictions["median_d2_d8"]),
    }
    (out / "rolling_lear_results.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--start", default="2026-08-02")
    p.add_argument("--end", default="2026-10-30")
    p.add_argument("--lookback-days", type=int, default=365)
    p.add_argument("--min-train-rows", type=int, default=6000)
    p.add_argument("--publication-lag-minutes", type=int, default=120)
    args = p.parse_args()
    print(json.dumps(run(args.dataset, args.output, start=args.start, end=args.end,
                         lookback_days=args.lookback_days,
                         min_train_rows=args.min_train_rows,
                         publication_lag_minutes=args.publication_lag_minutes), indent=2))


if __name__ == "__main__":
    main()
