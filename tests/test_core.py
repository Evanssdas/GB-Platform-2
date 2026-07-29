import numpy as np
import pandas as pd

from gb_platform_v2.features import add_cyclical_time_features
from gb_platform_v2.risk import scenario_risk
from gb_platform_v2.timebase import settlement_periods_for_day
from gb_platform_v2.transforms import arcsinh_transform, inverse_arcsinh


def test_arcsinh_round_trip_supports_negative_prices():
    values = np.array([-250.0, -1.0, 0.0, 50.0, 500.0])
    restored = inverse_arcsinh(arcsinh_transform(values, 50.0), 50.0)
    assert np.allclose(restored, values)


def test_gb_dst_settlement_days():
    assert len(settlement_periods_for_day("2026-03-29")) == 46
    assert len(settlement_periods_for_day("2026-10-25")) == 50
    assert len(settlement_periods_for_day("2026-07-15")) == 48


def test_cyclical_features_are_bounded():
    frame = pd.DataFrame({"timestamp": pd.date_range("2026-01-01", periods=100, freq="30min", tz="UTC")})
    output = add_cyclical_time_features(frame)
    for column in ["hh_sin", "hh_cos", "dow_sin", "dow_cos", "year_sin", "year_cos"]:
        assert output[column].between(-1, 1).all()


def test_scenario_risk_uses_half_hour_energy():
    scenarios = np.array([[60.0, 60.0], [40.0, 40.0]])
    reference = np.array([50.0, 50.0])
    result = scenario_risk(scenarios, reference, position_mwh=10.0, confidence=0.5)
    assert result["worst_loss"] == 100.0
    assert result["best_profit"] == 100.0
