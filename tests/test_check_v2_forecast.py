from datetime import date
from pathlib import Path
import pandas as pd
from scripts.check_v2_forecast import check, expected_periods

def test_uk_settlement_day_lengths():
    assert expected_periods(date(2026, 3, 29)) == 46
    assert expected_periods(date(2026, 10, 25)) == 50
    assert expected_periods(date(2026, 11, 4)) == 48

def test_full_forecast_and_missing_period(tmp_path):
    day = date(2026, 11, 4)
    start = pd.Timestamp(day).tz_localize("Europe/London").tz_convert("UTC")
    ts = pd.date_range(start, periods=48, freq="30min")
    file = tmp_path / "forecasts.csv"
    df = pd.DataFrame({"delivery_time_utc": ts.astype(str),
                       "model_version": "core-regime-operational-v2"})
    df.to_csv(file, index=False)
    assert check(file, "core-regime-operational-v2", day)[0]
    df.iloc[:-1].to_csv(file, index=False)
    assert not check(file, "core-regime-operational-v2", day)[0]
