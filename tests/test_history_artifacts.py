import json
from pathlib import Path

import pandas as pd

from gb_platform_v2.history_artifacts import prepare_historical_artifacts


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _artifact(root: Path, start: str, end: str, run_id: str) -> None:
    start_utc = pd.Timestamp(start).tz_localize("Europe/London").tz_convert("UTC")
    end_utc = pd.Timestamp(end).tz_localize("Europe/London").tz_convert("UTC")
    half_hours = pd.date_range(start_utc, end_utc, freq="30min", inclusive="left")
    hours = pd.date_range(start_utc, end_utc, freq="1h", inclusive="left")

    _write_json(
        root / "workflow_context.json",
        {
            "workflow_revision": "historical-v4",
            "run_id": run_id,
            "start_date_inclusive": start,
            "end_date_exclusive": end,
        },
    )
    _write_json(
        root / "workflow_status.json",
        {
            "input_validation": "success",
            "install_test": "success",
            "elexon_core": "success",
            "neso_embedded": "success",
            "neso_inertia": "success",
            "weather_demand": "success",
            "weather_wind": "success",
            "weather_solar": "success",
            "audit": "success",
        },
    )
    _write_json(root / "data_audit.json", {"errors": []})

    source_frames = {
        "elexon/elexon_mid.parquet": pd.DataFrame(
            {"timestamp": half_hours, "price_gbp_mwh": range(len(half_hours))}
        ),
        "elexon/elexon_demand.parquet": pd.DataFrame(
            {"timestamp": half_hours, "demand_mw": 30000.0}
        ),
        "elexon/elexon_fuelhh.parquet": pd.DataFrame(
            {
                "timestamp": half_hours,
                "fuel_wind_mw": 5000.0,
                "fuel_nuclear_mw": 6000.0,
            }
        ),
        "elexon/elexon_interconnectors.parquet": pd.DataFrame(
            {"timestamp": half_hours, "net_import_mw": 1000.0}
        ),
        "neso/inertia.parquet": pd.DataFrame(
            {"timestamp": half_hours, "outturn_inertia_gvas": 150.0}
        ),
    }
    for relative, frame in source_frames.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)

    issue = (
        half_hours.tz_convert("Europe/London").normalize()
        - pd.Timedelta(days=1)
        + pd.Timedelta(hours=13)
    ).tz_convert("UTC")
    embedded = pd.concat(
        [
            pd.DataFrame(
                {
                    "timestamp": half_hours,
                    "embedded_wind_mw": 2000.0,
                    "embedded_solar_mw": 1000.0,
                    "published_at_utc": issue - pd.Timedelta(hours=1),
                }
            ),
            pd.DataFrame(
                {
                    "timestamp": half_hours,
                    "embedded_wind_mw": 9999.0,
                    "embedded_solar_mw": 9999.0,
                    "published_at_utc": issue + pd.Timedelta(hours=1),
                }
            ),
        ],
        ignore_index=True,
    )
    path = root / "neso/embedded.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    embedded.to_parquet(path, index=False)

    for group in ("demand", "wind", "solar"):
        path = root / f"weather/{group}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"timestamp": hours, "site_temperature": 10.0}).to_parquet(
            path, index=False
        )


def test_prepare_historical_artifacts_is_contiguous_and_point_in_time_safe(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    output = tmp_path / "combined"
    _artifact(first, "2025-04-01", "2025-04-02", "1")
    _artifact(second, "2025-04-02", "2025-04-03", "2")

    summary = prepare_historical_artifacts(
        [second, first],
        output,
        "2025-04-01",
        "2025-04-03",
    )

    expected_rows = 96
    assert summary["expected_half_hour_rows"] == expected_rows
    assert summary["artifact_run_ids"] == ["1", "2"]
    embedded = pd.read_parquet(output / "neso/embedded.parquet")
    assert len(embedded) == expected_rows
    assert embedded["embedded_wind_mw"].eq(2000.0).all()
    assert (
        pd.to_datetime(embedded["published_at_utc"], utc=True)
        <= pd.to_datetime(embedded["selected_issue_time_utc"], utc=True)
    ).all()
    weather = pd.read_parquet(output / "weather/demand.parquet")
    assert len(weather) == 49
    assert "weather_demand_site_temperature" in weather
