import numpy as np
import pandas as pd

from gb_platform_v2.evaluation import crps_ensemble, interval_score, pinball_loss
from gb_platform_v2.pipeline import _component_targets


def test_paper_profile_excludes_inertia_without_fabrication():
    frame = pd.DataFrame(
        {
            "model_profile": ["core_without_battery_or_inertia"] * 2,
            "demand_mw": [1.0, 2.0],
            "embedded_wind_mw": [1.0, 2.0],
            "embedded_solar_mw": [1.0, 2.0],
            "transmission_wind_mw": [1.0, 2.0],
            "nuclear_mw": [1.0, 2.0],
            "net_import_mw": [1.0, 2.0],
        }
    )
    profile, targets = _component_targets(frame)
    assert profile == "core_without_battery_or_inertia"
    assert "inertia_gvas" not in targets
    assert targets == [
        "demand_mw",
        "embedded_wind_mw",
        "embedded_solar_mw",
        "transmission_wind_mw",
        "nuclear_mw",
        "net_import_mw",
    ]


def test_probabilistic_scores_are_finite_and_reward_sharp_correct_forecast():
    actual = np.array([10.0, 20.0])
    lower = np.array([9.0, 19.0])
    median = np.array([10.0, 20.0])
    upper = np.array([11.0, 21.0])
    paths = np.array(
        [
            [9.0, 19.0],
            [10.0, 20.0],
            [11.0, 21.0],
        ]
    )

    assert pinball_loss(actual, median, 0.5) == 0.0
    assert interval_score(actual, lower, upper, alpha=0.2) == 2.0
    assert np.isfinite(crps_ensemble(actual, paths))
