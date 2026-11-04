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

def test_unequal_windows_are_evaluated_on_common_periods(tmp_path):
    from gb_platform_v2.adaptive_analysis import analyse
    import numpy as np
    import pandas as pd
    t = pd.date_range("2026-01-01", periods=48 * 20, freq="30min", tz="UTC")
    rng = np.random.default_rng(1)
    actual = 100 + rng.normal(0, 5, len(t))
    v = pd.DataFrame({"timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "actual": actual,
                      "daily_v2r": actual-20, "d2": actual+3, "median_d2_d8": actual+1})
    l = v[["timestamp", "actual"]].assign(lear_rolling=actual-5).iloc[48*3:]
    v.to_csv(tmp_path/"v.csv", index=False)
    l.to_csv(tmp_path/"l.csv", index=False)
    result = analyse(tmp_path/"v.csv", tmp_path/"l.csv", tmp_path/"out")
    assert result["unpaired_dropped"]["v2r_only_periods"] == 48*3
    assert result["unpaired_dropped"]["lear_only_periods"] == 0
    assert result["eligible_periods"] > 0
