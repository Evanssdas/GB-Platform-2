"""Illustrative battery schedule-value sensitivity, not trading profit."""
import argparse,json
from pathlib import Path
from math import sqrt
import numpy as np,pandas as pd
from scipy.optimize import milp,Bounds,LinearConstraint

def schedule(prices):
    p=np.asarray(prices,float)
    n=len(p); h=.5; eta=sqrt(.88)
    I=np.eye(n); O=np.zeros((n,n)); L=np.tril(np.ones((n,n)))
    # decision vector: charge, discharge, binary charge-mode
    c=np.r_[h*p,-h*p,np.zeros(n)]
    a=np.hstack([L*eta*h,-L*h/eta,O])
    b=np.r_[np.full(n,eta*h),np.full(n,-h/eta),np.zeros(n)][None,:]
    v=np.r_[np.zeros(n),np.full(n,h),np.zeros(n)][None,:]
    constraints=[
      LinearConstraint(a,-1,1),
      LinearConstraint(b,0,0),
      LinearConstraint(v,0,2),
      LinearConstraint(np.hstack([I,O,-I]),-np.inf,0),
      LinearConstraint(np.hstack([O,I,I]),-np.inf,1)
    ]
    z=milp(c,integrality=np.r_[np.zeros(2*n),np.ones(n)],
           bounds=Bounds(np.zeros(3*n),np.ones(3*n)),
           constraints=constraints,options={"time_limit":40})
    if z.x is None:raise RuntimeError(z.message)
    return z.x[:n],z.x[n:2*n]

def evaluate(csv_path,out_dir):
    f=pd.read_csv(csv_path)
    f=f.loc[f.adaptive_p50.notna()].copy()
    f["day"]=pd.to_datetime(f.timestamp,utc=True).dt.tz_convert("Europe/London").dt.date
    columns={"perfect_foresight":"actual","adaptive_v2":"adaptive_p50",
             "daily_v2r":"daily_v2r","daily_lear":"lear_rolling",
             "d2_d8_median":"median","d2":"d2"}
    rows=[]
    for day,g in f.groupby("day"):
        actual=g.actual.to_numpy(float)
        if not np.isfinite(actual).all():continue
        row={"date":str(day),"periods":len(g)}
        for name,col in columns.items():
            pred=g[col].to_numpy(float)
            if not np.isfinite(pred).all():raise ValueError("missing "+name)
            charge,discharge=schedule(pred)
            row[name]=float(np.sum(actual*(discharge-charge)*.5))
        rows.append(row)
    daily=pd.DataFrame(rows)
    if daily.empty:raise ValueError("no complete value days")
    totals={name:float(daily[name].sum()) for name in columns}
    denominator=totals["perfect_foresight"]
    result={"days":len(daily),"battery":"1MW/2MWh; 88% round-trip; 1 daily cycle; SOC 1MWh start/end",
            "revenue_proxy_gbp_per_mw":totals,
            "fraction_of_perfect_foresight":{k:(v/denominator if denominator else None)
                for k,v in totals.items()},
            "limitations":"APXMIDP is not necessarily executable; excludes bid/ask, fees, degradation and imbalance."}
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    daily.to_csv(out/"battery_daily.csv",index=False)
    (out/"battery_results.json").write_text(json.dumps(result,indent=2))
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--predictions",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    print(json.dumps(evaluate(args.predictions,args.output),indent=2))
