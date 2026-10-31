import pandas as pd

from gb_platform_v2.features import (
    add_cyclical_time_features,
    add_market_regime_features,
    add_weather_features,
)


def test_paper_preprocessing_matches_training_feature_path():
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z"]
            ),
            "price_gbp_mwh": [50.0, 60.0],
        }
    ).set_index("timestamp", drop=False)

    prepared = add_cyclical_time_features(frame)
    prepared = add_weather_features(prepared)
    prepared = add_market_regime_features(prepared)

    for column in ("hh_sin", "hh_cos", "dow_sin", "dow_cos", "year_sin", "year_cos", "is_weekend", "month"):
        assert column in prepared
