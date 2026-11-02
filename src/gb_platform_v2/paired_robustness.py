"""Paired forecast robustness on immutable GitHub Actions prediction artifacts."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .reviewer_upgrade import _hac_dm, _point_metrics

def evaluate(v2_file, lear_file, output, *, draws=2000, seed=20261102):
    v=pd.read_csv(v2_file)
    l=pd.read_csv(lear_file)
    if v["timestamp"].duplicated().any() or l["timestamp"].duplicated().any():
        raise ValueError("Duplicate forecast timestamps")
    # Accept the respective frozen output column names, never merge by row number.
    vcol=next(c for c in ("daily_v2r","prediction") if c in v)
    lcol=next(c for c in ("lear_rolling","prediction") if c in l)
    joined=v[["timestamp","actual",vcol,"d2","d2_d8_median" if "d2_d8_median" in v else "median_d2_d8"]].merge(
        l[["timestamp","actual",lcol]],on="timestamp",how="inner",suffixes=("_v2r","_lear"),validate="one_to_one")
    if len(joined)!=len(v) or len(joined)!=len(l):
        raise ValueError("Prediction windows differ; cannot compare unpaired samples")
    if not np.allclose(joined["actual_v2r"],joined["actual_lear"],atol=1e-6):
        raise ValueError("Mismatched actual prices")
    joined["timestamp"]=pd.to_datetime(joined["timestamp"],utc=True)
    joined=joined.sort_values("timestamp").reset_index(drop=True)
    joined["delivery_date"]=joined["timestamp"].dt.tz_convert("Europe/London").dt.date.astype(str)
    joined["month"]=joined["timestamp"].dt.tz_convert("Europe/London").dt.strftime("%Y-%m")
    median_col="d2_d8_median" if "d2_d8_median" in joined else "median_d2_d8"
    actual=joined["actual_v2r"]
    models={"daily_v2r":joined[vcol],"daily_lear":joined[lcol],"d2":joined["d2"],"d2_d8_median":joined[median_col]}
    for name,values in models.items():
        if values.isna().any() or not np.isfinite(values).all():
            raise ValueError(f"Missing prediction: {name}")
    comparisons={}
    rng=np.random.default_rng(seed)
    days=[g for _,g in joined.groupby("delivery_date",sort=True)]
    for rival in ("daily_lear","d2","d2_d8_median"):
        a=np.abs(models["daily_v2r"]-actual)
        b=np.abs(models[rival]-actual)
        comparison=_hac_dm(actual,models["daily_v2r"],models[rival])
        day_diffs=[(np.abs(g[vcol]-g["actual_v2r"])-np.abs(g[lcol if rival=="daily_lear" else rival if rival=="d2" else median_col]-g["actual_v2r"])).to_numpy() for g in days]
        samples=np.empty(draws)
        for k in range(draws):
            choices=rng.integers(0,len(days),len(days))
            vals=np.concatenate([day_diffs[j] for j in choices])
            samples[k]=vals.mean()
        comparison["day_block_bootstrap_95ci"]=np.quantile(samples,[.025,.975]).tolist()
        comparison["bootstrap_days"]=len(days)
        comparisons[rival]=comparison
    monthly=[]
    for month,g in joined.groupby("month"):
        row={"month":month,"rows":len(g)}
        for label,pred in models.items():
            row[f"{label}_mae"]=float(np.mean(np.abs(pred.loc[g.index]-actual.loc[g.index])))
        monthly.append(row)
    q90=float(actual.quantile(.9))
    negative=actual.lt(0)
    high=actual.ge(q90)
    regimes={}
    for label,mask in (("negative_price",negative),("top_10pct_actual_price",high),("other",~(negative|high))):
        regimes[label]={"rows":int(mask.sum()),"definition":"actual outcome subgroup, not ex-ante tradable signal"}
        for name,pred in models.items():
            regimes[label][name]=_point_metrics(actual.loc[mask],pred.loc[mask])
    metrics={"protocol":"paired retrospective; 90-day block bootstrap and HAC(47); actual-defined regime diagnostics are post-hoc",
             "rows":len(joined),"days":len(days),"period_start":joined["timestamp"].min().isoformat(),
             "period_end":joined["timestamp"].max().isoformat(),"models":{n:_point_metrics(actual,p) for n,p in models.items()},
             "comparisons_daily_v2r_minus":comparisons,"month":monthly,"regimes":regimes,"high_price_threshold":q90}
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    joined.to_csv(out/"paired_predictions.csv",index=False)
    pd.DataFrame(monthly).to_csv(out/"monthly_metrics.csv",index=False)
    (out/"robustness_results.json").write_text(json.dumps(metrics,indent=2))
    return metrics

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--v2r",required=True);parser.add_argument("--lear",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    print(json.dumps(evaluate(args.v2r,args.lear,args.output),indent=2))
if __name__=="__main__":
    main()
