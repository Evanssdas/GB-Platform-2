import json
from pathlib import Path

import pandas as pd

from gb_platform_v2.history_artifacts import _combine_weather


def test_weather_artifact_seam_uses_declared_half_open_windows(tmp_path):
    a = tmp_path / "A"
    b = tmp_path / "B"
    (a / "weather").mkdir(parents=True)
    (b / "weather").mkdir(parents=True)

    # A includes a boundary spill at 2026-01-01 00:00 with one value.
    a_frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2025-12-31T23:00:00Z", "2026-01-01T00:00:00Z"]
            ),
            "London_temperature_2m_previous_day1": [5.0, 5.5],
        }
    )
    # B legitimately owns the seam timestamp and has a different archived value.
    b_frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"]
            ),
            "London_temperature_2m_previous_day1": [6.0, 6.5],
        }
    )
    a_frame.to_parquet(a / "weather" / "demand.parquet", index=False)
    b_frame.to_parquet(b / "weather" / "demand.parquet", index=False)

    artifacts = [
        {"root": a, "start": "2025-12-31", "end": "2026-01-01"},
        {"root": b, "start": "2026-01-01", "end": "2026-01-02"},
    ]
    expected = pd.date_range(
        pd.Timestamp("2025-12-31").tz_localize("Europe/London").tz_convert("UTC"),
        pd.Timestamp("2026-01-02").tz_localize("Europe/London").tz_convert("UTC"),
        freq="1h",
        inclusive="left",
    )

    # Add the remaining hours so the helper sees a complete expected clock.
    full_a = pd.DataFrame(
        {
            "timestamp": expected[expected < pd.Timestamp("2026-01-01T00:00:00Z")],
            "London_temperature_2m_previous_day1": 5.0,
        }
    )
    full_a = pd.concat(
        [full_a, a_frame.tail(1)], ignore_index=True
    ).drop_duplicates("timestamp", keep="last")
    full_b = pd.DataFrame(
        {
            "timestamp": expected[expected >= pd.Timestamp("2026-01-01T00:00:00Z")],
            "London_temperature_2m_previous_day1": 6.0,
        }
    )
    full_a.to_parquet(a / "weather" / "demand.parquet", index=False)
    full_b.to_parquet(b / "weather" / "demand.parquet", index=False)

    result = _combine_weather(
        artifacts,
        "demand",
        expected,
        pd.Timestamp("2026-01-02").tz_localize("Europe/London").tz_convert("UTC"),
    )

    seam = result.loc[
        result["timestamp"].eq(pd.Timestamp("2026-01-01T00:00:00Z"))
    ]
    assert len(seam) == 1
    assert seam.iloc[0]["weather_demand_London_temperature_2m_previous_day1"] == 6.0
