"""Regression tests: D-1 calibration may use only already-delivered observations."""
import numpy as np
import pandas as pd

from gb_platform_v2.reviewer_upgrade import _rolling_calibration


def test_calibration_is_identical_for_all_periods_issued_together():
    # Earlier settlements on delivery day must never change the correction
    # for later settlements from the same D-1 13:00 forecast issuance.
    timestamps = pd.Series(pd.date_range("2026-10-15", "2026-10-30", freq="30min", tz="UTC"))
    local = timestamps.dt.tz_convert("Europe/London")
    actual = pd.Series(np.asarray(local.dt.date.map(lambda d: float(d.day)), dtype=float))
    p50 = pd.Series(np.zeros(len(timestamps)))
    calibrated = _rolling_calibration(timestamps, actual, p50 - 10, p50, p50 + 10)
    # Even across the autumn clock change, all periods of each local
    # delivery day share one issue instant and one calibration history.
    for delivery_date in local.dt.date.unique():
        rows = calibrated.loc[local.dt.date.eq(delivery_date) & calibrated["cal_p50"].notna()]
        if not rows.empty:
            assert rows["bias_shift"].nunique() == 1
            assert rows["dispersion_scale"].nunique() == 1


def test_calibration_does_not_use_observations_after_issue():
    timestamps = pd.Series(pd.date_range("2026-10-15", "2026-10-27", freq="30min", tz="UTC"))
    actual = pd.Series(np.zeros(len(timestamps)))
    p50 = pd.Series(np.zeros(len(timestamps)))
    initial = _rolling_calibration(timestamps, actual, p50 - 1, p50, p50 + 1)
    # Change all outturns for 26 October, unavailable at the 25 October
    # 13:00 local issue for 26 October. The 26 October calibration must not move.
    perturbed = actual.copy()
    delivery_day = timestamps.dt.tz_convert("Europe/London").dt.date.eq(pd.Timestamp("2026-10-26").date())
    perturbed.loc[delivery_day] = 10000.0
    revised = _rolling_calibration(timestamps, perturbed, p50 - 1, p50, p50 + 1)
    assert np.allclose(initial.loc[delivery_day, "cal_p50"], revised.loc[delivery_day, "cal_p50"], equal_nan=True)
