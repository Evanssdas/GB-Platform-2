import numpy as np
import pandas as pd
import pytest
from gb_platform_v2.paired_robustness import evaluate

def _write(tmp_path, drop=False, bad_actual=False):
    times=pd.date_range("2026-08-02",periods=96,freq="30min",tz="UTC")
    y=100+np.arange(96)/5
    v=pd.DataFrame({"timestamp":times.astype(str),"actual":y,"daily_v2r":y+2,"d2":y+7,"median_d2_d8":y+4})
    l=pd.DataFrame({"timestamp":times.astype(str),"actual":y,"lear_rolling":y+5})
    if drop:
        l=l.iloc[:-1]
    if bad_actual:
        l.loc[0,"actual"]+=1
    vfile=tmp_path/"v.csv"; lfile=tmp_path/"l.csv"
    v.to_csv(vfile,index=False);l.to_csv(lfile,index=False)
    return vfile,lfile

def test_paired_robustness_and_grouping(tmp_path):
    v,l=_write(tmp_path)
    result=evaluate(v,l,tmp_path/"out",draws=50)
    assert result["rows"]==96 and result["days"]==3  # UTC-window spans three GB local dates
    assert abs(result["models"]["daily_v2r"]["mae"]-2)<1e-8
    assert result["comparisons_daily_v2r_minus"]["daily_lear"]["mean_absolute_loss_difference_model_minus_benchmark"]<0
    assert (tmp_path/"out"/"robustness_results.json").exists()

@pytest.mark.parametrize("option",["drop","bad_actual"])
def test_unpaired_evidence_rejected(tmp_path,option):
    v,l=_write(tmp_path,**{option:True})
    with pytest.raises(ValueError):
        evaluate(v,l,tmp_path/"out",draws=5)
