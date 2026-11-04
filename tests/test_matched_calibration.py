import numpy as np
import pandas as pd
from gb_platform_v2.matched_calibration import analyse

def test_matched_two_by_two_uses_identical_periods(tmp_path):
    t = pd.date_range("2026-08-01", periods=48 * 16, freq="30min", tz="UTC")
    rng = np.random.default_rng(2)
    actual = 130 + rng.normal(0, 8, len(t))
    frozen = pd.DataFrame({
        "timestamp": t, "actual": actual,
        "v2r": actual - 38 + rng.normal(0, 6, len(t)),
        "d2": actual + rng.normal(0, 20, len(t)),
        "median_d2_d8": actual + rng.normal(0, 12, len(t))})
    daily = pd.DataFrame({
        "timestamp": t[48:], "actual": actual[48:],
        "daily_v2r": actual[48:] - 20 + rng.normal(0, 5, len(t) - 48)})
    frozen.to_csv(tmp_path / "f.csv", index=False)
    daily.to_csv(tmp_path / "d.csv", index=False)
    result = analyse(tmp_path / "f.csv", tmp_path / "d.csv", tmp_path / "out",
                     lag_minutes=120, battery=False)
    rows = {v["rows"] for v in result["point"].values()}
    assert rows == {result["matched_periods"]}
    assert abs(result["point"]["frozen_cal"]["bias"]) < 5
    assert result["point"]["frozen"]["bias"] < -30
    assert "daily_cal_vs_frozen_cal" in result["tests_hac47"]
