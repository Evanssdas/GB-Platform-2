from datetime import date
import json

import pandas as pd

from gb_platform_v2.data_audit import audit_directory


def test_audit_serialises_python_date_values(tmp_path):
    input_dir = tmp_path / "parsed"
    input_dir.mkdir()
    source = input_dir / "sample.parquet"
    output = input_dir / "data_audit.json"

    pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-07-01", periods=2, freq="30min", tz="UTC"),
            "settlement_date": [date(2025, 7, 1), date(2025, 7, 1)],
            "value": [1.0, 2.0],
        }
    ).to_parquet(source, index=False)

    report = audit_directory(input_dir, output)
    decoded = json.loads(output.read_text(encoding="utf-8"))

    assert report["dataset_count"] == 1
    assert decoded["datasets"][0]["sample"][0]["settlement_date"] == "2025-07-01"
    assert decoded["datasets"][0]["sample"][0]["timestamp"].startswith("2025-07-01T00:00:00")
