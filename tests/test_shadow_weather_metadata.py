import numpy as np
import pandas as pd
import gb_platform_v2.shadow_features as sf

def test_weather_group_ignores_text_provenance_columns(monkeypatch):
    day = "2026-11-04"
    start = pd.Timestamp(day).tz_localize("Europe/London").tz_convert("UTC")
    periods = pd.date_range(start, periods=48, freq="30min")
    hourly = pd.date_range(start - pd.Timedelta(hours=1), periods=27, freq="h")
    def fake_exact(sites, delivery):
        frame = pd.DataFrame({
            "timestamp": hourly,
            "site_temperature_2m": np.linspace(5, 12, len(hourly)),
            "site_wind_speed_100m": np.linspace(3, 9, len(hourly)),
        })
        frame["weather_run_utc"] = pd.Timestamp("2026-11-03 00:00", tz="UTC")
        frame["weather_model"] = "ecmwf_ifs"
        frame["weather_vintage_source"] = pd.array(
            ["single_run_d1_00utc"] * len(hourly), dtype="string"
        )
        return frame
    monkeypatch.setattr(sf, "exact_issue_weather_day", fake_exact)
    out = sf._weather_group([{"name": "site"}], "demand", periods)
    assert len(out) == 48
    assert not out.isna().any().any()
    assert all(pd.api.types.is_numeric_dtype(out[c]) for c in out.columns)
    assert not any("vintage_source" in c for c in out.columns)
