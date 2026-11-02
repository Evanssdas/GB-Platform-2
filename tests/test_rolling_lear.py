import pandas as pd
import numpy as np
from gb_platform_v2.rolling_lear import issue_for_date, build_design

def test_issue_time_before_delivery_and_dst():
    for day in ("2026-03-29", "2026-10-25", "2026-10-26"):
        issue = issue_for_date(day)
        local = issue.tz_convert("Europe/London")
        assert local.hour == 13
        assert local.date() == (pd.Timestamp(day) - pd.Timedelta(days=1)).date()

def test_features_use_only_observable_lags():
    ts = pd.date_range("2026-10-01", periods=700, freq="30min", tz="UTC")
    f = pd.DataFrame({"timestamp": ts, "price_gbp_mwh": np.arange(len(ts), dtype=float)})
    X = build_design(f)
    for idx in range(400, len(f)):
        day = f.loc[idx, "timestamp"].tz_convert("Europe/London").date()
        issue = issue_for_date(day)
        if f.loc[idx, "timestamp"] - pd.Timedelta(days=2) < ts[0]:
            continue
        # The first historical price anchor is D-2, before the issue.
        assert f.loc[idx, "timestamp"] - pd.Timedelta(days=2) < issue
        assert X.loc[idx, "price_d2"] == f.loc[idx - 96, "price_gbp_mwh"]
