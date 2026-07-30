import pandas as pd
import pytest

from gb_platform_v2.collection import _date_chunks, _validate_window


def test_date_chunks_are_non_overlapping_and_end_exclusive():
    chunks = _date_chunks("2025-07-01", "2025-08-01", days=15)

    assert chunks == [
        (pd.Timestamp("2025-07-01"), pd.Timestamp("2025-07-16")),
        (pd.Timestamp("2025-07-16"), pd.Timestamp("2025-07-31")),
        (pd.Timestamp("2025-07-31"), pd.Timestamp("2025-08-01")),
    ]
    assert chunks[0][0] == pd.Timestamp("2025-07-01")
    assert chunks[-1][1] == pd.Timestamp("2025-08-01")
    assert all(previous[1] == current[0] for previous, current in zip(chunks, chunks[1:]))


def test_window_requires_end_after_start():
    with pytest.raises(ValueError, match="end must be later than start"):
        _validate_window("2025-07-01", "2025-07-01")


def test_chunk_days_must_be_positive():
    with pytest.raises(ValueError, match="at least 1"):
        _date_chunks("2025-07-01", "2025-08-01", days=0)
