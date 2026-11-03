"""Retrospective daily-V2R calibration with D-1 issue and publication allowance."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .rolling_lear import issue_for_date
from .paired_robustness import evaluate as paired_evaluate
from .reviewer_upgrade import _point_metrics, _hac_dm

def calibrate(frame, lag_minutes=120, lookback=7, min_history=96):
    d=frame.copy()
    d["timestamp"]=pd.to_datetime(d["timestamp"],utc=True)
    d=d.sort_values("timestamp").reset_index(drop=True)
    d["day"]=d.timestamp.dt.tz_convert("Europe/London").dt.date
    for col in ("adaptive_p10","adaptive_p50","adaptive_p90","bias_shift"):
        d[col]=np.nan
    residual=d.actual-d.daily_v2r
    for day, indices in d.groupby("day").groups.items():
        cutoff=issue_for_date(day)
        oldest=cutoff-pd.Timedelta(days=lookback)
        last=cutoff-pd.Timedelta(minutes=30+lag_minutes)
        history=(d.timestamp>=oldest)&(d.timestamp<=last)&residual.notna()
        if history.sum()<min_history:
            continue
        values=residual.loc[history].to_numpy(float)
        shift=float(np.median(values))
        lo,hi=np.quantile(values-shift,[.1,.9])
        point=d.loc[indices,"daily_v2r"].to_numpy(float)+shift
        d.loc[indices,"adaptive_p10"]=point+lo
        d.loc[indices,"adaptive_p50"]=point
        d.loc[indices,"adaptive_p90"]=point+hi
        d.loc[indices,"bias_shift"]=shift
    return d

def analyse(v2r,lear,output,lag_minutes=120):
    v=pd.read_csv(v2r)
    l=pd.read_csv(lear)
    m="median_d2_d8" if "median_d2_d8" in v.columns else "d2_d8_median"
    d=v[["timestamp","actual","daily_v2r","d2",m]].merge(
        l[["timestamp","actual","lear_rolling"]],on="timestamp",
        suffixes=("","_lear"),validate="one_to_one")
    if len(d)!=len(v) or len(d)!=len(l):
        raise ValueError("Incomplete paired prediction windows")
    if not np.allclose(d.actual,d.actual_lear,atol=1e-6):
        raise ValueError("Actual prices do not match")
    d=d.drop(columns="actual_lear").rename(columns={m:"median"})
    d=calibrate(d,lag_minutes)
    e=d.loc[d.adaptive_p50.notna()].copy()
    if e.empty:
        raise ValueError("No eligible post-warmup forecasts")
    models={"adaptive_v2":"adaptive_p50","daily_v2r":"daily_v2r",
            "daily_lear":"lear_rolling","d2":"d2","median":"median"}
    scores={name:_point_metrics(e.actual,e[col]) for name,col in models.items()}
    tests={name:_hac_dm(e.actual,e.adaptive_p50,e[col])
           for name,col in models.items() if name!="adaptive_v2"}
    low=e.adaptive_p10.to_numpy(float)
    high=e.adaptive_p90.to_numpy(float)
    actual=e.actual.to_numpy(float)
    interval={"coverage":float(np.mean((actual>=low)&(actual<=high))),
              "below_p10":float(np.mean(actual<low)),
              "above_p90":float(np.mean(actual>high)),
              "mean_width":float(np.mean(high-low))}
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    d.to_csv(out/"adaptive_predictions.csv",index=False)
    result={"protocol":"retrospective only","lag_minutes":lag_minutes,
            "eligible_periods":len(e),"days":int(e.day.nunique()),
            "scores_identical_periods":scores,"tests_hac47":tests,
            "interval":interval,"median_shift":float(e.bias_shift.median())}
    (out/"adaptive_results.json").write_text(json.dumps(result,indent=2))
    return result

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--v2r",required=True);ap.add_argument("--lear",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--publication-lag-minutes",type=int,default=120)
    args=ap.parse_args()
    print(json.dumps(analyse(args.v2r,args.lear,args.output,
                            args.publication_lag_minutes),indent=2))
