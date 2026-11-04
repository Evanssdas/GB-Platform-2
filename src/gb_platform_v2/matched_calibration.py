"""Matched 2 x 2: frozen vs daily-refit V2, each with and without the same calibration.

Applies one calibration rule (adaptive_analysis.calibrate: 7-day issue-time
history, publication allowance lag_minutes, median location shift and
empirical 10th/90th residual quantiles) to frozen V2 and daily-refit V2, and
scores the four variants on exactly the same settlement periods.
Retrospective only, with no prospective performance claims.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

from .adaptive_analysis import calibrate
from .battery_analysis import schedule
from .reviewer_upgrade import _hac_dm, _point_metrics


def _calibrated(frame: pd.DataFrame, column: str, lag_minutes: int) -> pd.DataFrame:
    base = frame[["timestamp", "actual", column]].rename(columns={column: "daily_v2r"})
    out = calibrate(base, lag_minutes)
    return out[["timestamp", "adaptive_p10", "adaptive_p50", "adaptive_p90"]].rename(columns={
        "adaptive_p10": f"{column}_cal_p10",
        "adaptive_p50": f"{column}_cal",
        "adaptive_p90": f"{column}_cal_p90",
    })


def _interval(actual, low, high) -> dict:
    y, lo, hi = (np.asarray(v, float) for v in (actual, low, high))
    below, above = y < lo, y > hi
    score = (hi - lo) + 10 * (lo - y) * below + 10 * (y - hi) * above
    return {"coverage": float(np.mean(~below & ~above)),
            "below_p10": float(np.mean(below)),
            "above_p90": float(np.mean(above)),
            "mean_width": float(np.mean(hi - lo)),
            "interval_score_80": float(np.mean(score))}


def analyse(frozen_csv, daily_csv, output, lag_minutes: int = 120, battery: bool = True) -> dict:
    frozen = pd.read_csv(frozen_csv)[["timestamp", "actual", "v2r", "d2", "median_d2_d8"]].rename(
        columns={"v2r": "frozen"})
    daily = pd.read_csv(daily_csv)[["timestamp", "actual", "daily_v2r"]].rename(
        columns={"daily_v2r": "daily"})
    for f in (frozen, daily):
        f["timestamp"] = pd.to_datetime(f["timestamp"], utc=True)
    d = frozen.merge(daily, on="timestamp", how="inner",
                     suffixes=("", "_daily"), validate="one_to_one")
    if not np.allclose(d["actual"], d["actual_daily"], atol=1e-6):
        raise ValueError("Actual prices differ between frozen and daily artefacts")
    d = d.drop(columns="actual_daily").sort_values("timestamp").reset_index(drop=True)
    for column in ("frozen", "daily"):
        d = d.merge(_calibrated(d, column, lag_minutes), on="timestamp",
                    how="left", validate="one_to_one")
    forecasts = ["frozen", "frozen_cal", "daily", "daily_cal", "median_d2_d8", "d2"]
    e = d.loc[d[forecasts].notna().all(axis=1)].copy()
    if e.empty:
        raise ValueError("No matched periods after calibration warm-up")
    e["day"] = e["timestamp"].dt.tz_convert("Europe/London").dt.date

    result = {
        "protocol": "retrospective matched 2x2; identical calibration rule and identical periods",
        "lag_minutes": int(lag_minutes),
        "matched_periods": int(len(e)),
        "days": int(e["day"].nunique()),
        "point": {f: _point_metrics(e["actual"], e[f]) for f in forecasts},
        "interval": {
            "frozen_cal": _interval(e["actual"], e["frozen_cal_p10"], e["frozen_cal_p90"]),
            "daily_cal": _interval(e["actual"], e["daily_cal_p10"], e["daily_cal_p90"]),
        },
        "tests_hac47": {
            "daily_cal_vs_frozen_cal": _hac_dm(e["actual"], e["daily_cal"], e["frozen_cal"]),
            "daily_vs_frozen": _hac_dm(e["actual"], e["daily"], e["frozen"]),
            "frozen_cal_vs_frozen": _hac_dm(e["actual"], e["frozen_cal"], e["frozen"]),
            "daily_cal_vs_daily": _hac_dm(e["actual"], e["daily_cal"], e["daily"]),
            "frozen_cal_vs_median": _hac_dm(e["actual"], e["frozen_cal"], e["median_d2_d8"]),
            "daily_cal_vs_median": _hac_dm(e["actual"], e["daily_cal"], e["median_d2_d8"]),
        },
    }
    if battery:
        rows = []
        for day, g in e.groupby("day"):
            actual = g["actual"].to_numpy(float)
            row = {"date": str(day)}
            for name in ["actual", *forecasts]:
                c, dis = schedule(g[name].to_numpy(float))
                row[name] = float(np.sum(actual * (dis - c) * 0.5))
            rows.append(row)
        daily_value = pd.DataFrame(rows).rename(columns={"actual": "perfect_foresight"})
        totals = {k: float(daily_value[k].sum()) for k in daily_value.columns if k != "date"}
        pf = totals["perfect_foresight"]
        result["battery_share_of_perfect_foresight"] = {k: v / pf for k, v in totals.items()}
        result["battery_revenue_proxy_gbp_per_mw"] = totals
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    e.to_csv(out / "matched_predictions.csv", index=False)
    (out / "matched_results.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen", required=True, help="reviewer_holdout_predictions.csv")
    ap.add_argument("--daily", required=True, help="daily_v2r_predictions.csv")
    ap.add_argument("--output", required=True)
    ap.add_argument("--publication-lag-minutes", type=int, default=120)
    ap.add_argument("--no-battery", action="store_true")
    a = ap.parse_args()
    res = analyse(a.frozen, a.daily, a.output, a.publication_lag_minutes,
                  battery=not a.no_battery)
    print("MATCHED_RESULTS_JSON_BEGIN")
    print(json.dumps(res, indent=2))
    print("MATCHED_RESULTS_JSON_END")
