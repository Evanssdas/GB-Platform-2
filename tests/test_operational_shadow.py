import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from gb_platform_v2.deployment_gate import evaluate_deployment_gate
from gb_platform_v2.operational_bundle import prepare_operational_bundle
from gb_platform_v2.shadow_features import build_shadow_features


def test_operational_bundle_selects_observable_d7_when_it_beats_model(tmp_path):
    timestamps = pd.date_range("2025-01-01", periods=48 * 40, freq="30min", tz="UTC")
    daily_pattern = np.tile(np.arange(48, dtype=float), 40)
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "demand_mw": 30000.0 + daily_pattern,
            "nuclear_mw": 6000.0 + daily_pattern * 0.1,
        }
    )
    dataset = tmp_path / "dataset.parquet"
    frame.to_parquet(dataset, index=False)

    model_dir = tmp_path / "models"
    model_dir.mkdir()
    metadata = {
        "model_profile": "core_without_battery",
        "component_targets": ["demand_mw", "nuclear_mw"],
        "metrics": {
            "demand_mw": {"model_mae": 1000.0},
            "nuclear_mw": {"model_mae": 500.0},
        },
    }
    (model_dir / "metadata.json").write_text(json.dumps(metadata))
    errors = pd.DataFrame(
        {"demand_mw": 1000.0, "nuclear_mw": 500.0}, index=timestamps
    )
    errors.to_parquet(model_dir / "historical_component_errors.parquet")

    summary = prepare_operational_bundle(dataset, model_dir, holdout_rows=48 * 10)

    assert summary["component_strategy"]["demand_mw"]["source"] == "fallback_d7"
    assert summary["component_strategy"]["nuclear_mw"]["source"] == "fallback_d7"
    operational_errors = pd.read_parquet(
        model_dir / "operational_component_errors.parquet"
    )
    assert len(operational_errors) >= 48 * 30
    updated = json.loads((model_dir / "metadata.json").read_text())
    assert updated["operational_bundle_ready"] is True
    assert updated["component_error_file"] == "operational_component_errors.parquet"


@pytest.mark.parametrize(
    ("delivery_date", "expected_periods"),
    [("2026-03-29", 46), ("2026-10-25", 50)],
)
def test_shadow_features_follow_gb_dst_clock(
    tmp_path, monkeypatch, delivery_date, expected_periods
):
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    features = [
        "hh_sin",
        "hh_cos",
        "dow_sin",
        "dow_cos",
        "year_sin",
        "year_cos",
        "is_weekend",
        "month",
    ]
    metadata = {
        "operational_bundle_ready": True,
        "model_profile": "core_without_battery",
        "features": features,
        "operational_component_strategy": {
            "demand_mw": {"source": "model"},
            "nuclear_mw": {"source": "model"},
        },
    }
    (model_dir / "metadata.json").write_text(json.dumps(metadata))
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {"weather_sites": {"demand": [], "wind": [], "solar": []}}
        )
    )

    def fake_weather_group(sites, group, periods_utc):
        return pd.DataFrame(
            {f"weather_{group}_dummy_previous_day1": 1.0}, index=periods_utc
        )

    monkeypatch.setattr(
        "gb_platform_v2.shadow_features._weather_group", fake_weather_group
    )
    delivery = pd.Timestamp(delivery_date)
    issue = (
        delivery.tz_localize("Europe/London") - pd.Timedelta(hours=12)
    ).tz_convert("UTC")
    output = tmp_path / "features.parquet"
    summary = build_shadow_features(
        delivery_date,
        issue.isoformat(),
        config,
        model_dir,
        output,
        tmp_path / "recent",
    )

    result = pd.read_parquet(output)
    assert summary["period_count"] == expected_periods
    assert len(result) == expected_periods
    assert not result[features].isna().any().any()


def test_deployment_gate_passes_complete_improving_thirty_day_shadow(tmp_path):
    timestamps = pd.date_range("2026-01-01", periods=48 * 30, freq="30min", tz="UTC")
    issue_times = []
    for timestamp in timestamps:
        local_day = timestamp.tz_convert("Europe/London").normalize()
        issue_times.append((local_day - pd.Timedelta(hours=12)).tz_convert("UTC"))
    coverage = np.array(([True] * 4 + [False]) * (len(timestamps) // 5))
    scores = pd.DataFrame(
        {
            "model_version": "core-12m-operational-v1",
            "issue_time_utc": issue_times,
            "delivery_time_utc": timestamps,
            "absolute_error": 8.0,
            "persistence_absolute_error": 10.0,
            "p10_p90_covered": coverage,
        }
    )
    path = tmp_path / "scores.csv"
    scores.to_csv(path, index=False)
    output = tmp_path / "gate.json"

    report = evaluate_deployment_gate(
        path,
        "core-12m-operational-v1",
        output,
        min_days=30,
        min_improvement_percent=5.0,
    )

    assert report["deployment_ready"] is True
    assert report["metrics"]["improvement_percent"] == pytest.approx(20.0)
    assert report["metrics"]["p10_p90_coverage"] == pytest.approx(0.8)
    assert all(value["passed"] for value in report["gates"].values())
