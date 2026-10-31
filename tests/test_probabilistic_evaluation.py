import numpy as np

from gb_platform_v2.evaluation import (
    crps_ensemble,
    interval_score,
    pinball_loss,
    probabilistic_summary,
)


def test_pinball_loss_is_zero_for_exact_quantile():
    actual = np.array([10.0, 20.0, 30.0])
    assert pinball_loss(actual, actual, 0.5) == 0.0


def test_interval_score_rewards_narrow_covering_interval():
    actual = np.array([10.0, 20.0])
    narrow = interval_score(actual, np.array([9.0, 19.0]), np.array([11.0, 21.0]))
    wide = interval_score(actual, np.array([0.0, 10.0]), np.array([20.0, 30.0]))
    assert narrow < wide


def test_crps_deterministic_ensemble_equals_mae():
    actual = np.array([10.0, 20.0, 30.0])
    forecast = np.array([12.0, 18.0, 25.0])
    paths = np.repeat(forecast[None, :], 20, axis=0)
    assert np.isclose(crps_ensemble(actual, paths), np.mean(np.abs(actual - forecast)))


def test_probabilistic_summary_reports_coverage_and_scores():
    actual = np.array([10.0, 20.0, 30.0, 40.0])
    p10 = np.array([5.0, 15.0, 25.0, 35.0])
    p50 = actual.copy()
    p90 = np.array([15.0, 25.0, 35.0, 45.0])
    paths = np.vstack([p10, p50, p90])
    result = probabilistic_summary(actual, p10, p50, p90, paths)
    assert result["p10_p90_coverage"] == 1.0
    assert result["mean_interval_width_gbp_mwh"] == 10.0
    assert result["interval_score_80"] > 0.0
    assert result["crps_ensemble"] >= 0.0
