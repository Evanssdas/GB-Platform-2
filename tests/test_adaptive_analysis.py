import numpy as np
import pandas as pd
from gb_platform_v2.adaptive_analysis import calibrate

def test_calibration_same_issue_and_future_outcomes_invisible():
    t=pd.date_range("2026-10-01",periods=2500,freq="30min",tz="UTC")
    frame=pd.DataFrame({"timestamp":t,"actual":100.0,"daily_v2r":80.0})
    out=calibrate(frame,lag_minutes=120)
    day=pd.Timestamp("2026-10-30").date()
    mask=out.day==day
    assert mask.any()
    before=out.loc[mask, "adaptive_p50"].to_numpy()
    changed=frame.copy()
    changed.loc[mask,"actual"]+=10000
    after=calibrate(changed,lag_minutes=120).loc[mask,"adaptive_p50"].to_numpy()
    np.testing.assert_allclose(before,after)
    assert np.nanmean(before)>80

def test_publication_allowance_excludes_last_settlement():
    t=pd.date_range("2026-10-01",periods=2500,freq="30min",tz="UTC")
    frame=pd.DataFrame({"timestamp":t,"actual":100.0,"daily_v2r":80.0})
    a=calibrate(frame,lag_minutes=120)
    b=calibrate(frame,lag_minutes=0)
    day=pd.Timestamp("2026-10-30").date()
    assert a.loc[a.day==day,"adaptive_p50"].notna().all()
    assert b.loc[b.day==day,"adaptive_p50"].notna().all()
