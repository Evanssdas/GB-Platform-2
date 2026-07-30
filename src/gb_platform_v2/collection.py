"""Historical and live source collection helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .data.clients import NesoCkanClient, OpenMeteoClient
from .data.elexon import ElexonClient
from .data.neso import NESO_RESOURCES, parse_embedded_forecasts, parse_inertia
from .data.parsers import (
    parse_elexon_demand,
    parse_elexon_fuelhh,
    parse_elexon_interconnectors,
    parse_elexon_mid,
    parse_neso_records,
    parse_open_meteo_hourly,
)
from .data.unit_generation import parse_bm_unit_reference, parse_unit_generation


def _date_chunks(start: str, end: str, days: int = 30) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    first = pd.Timestamp(start)
    last = pd.Timestamp(end)
    chunks: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    cursor = first
    while cursor <= last:
        chunk_end = min(cursor + pd.Timedelta(days=days - 1), last)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + pd.Timedelta(days=1)
    return chunks


def _save_frame(frame: pd.DataFrame, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".csv":
        frame.to_csv(output, index=False)
    else:
        frame.to_parquet(output, index=False)
    return output


def collect_elexon_core(
    start: str,
    end: str,
    output_dir: str | Path,
    chunk_days: int = 30,
) -> dict[str, Path]:
    """Collect APXMIDP, demand, fuel generation and interconnector outturn."""
    client = ElexonClient()
    price_frames: list[pd.DataFrame] = []
    demand_frames: list[pd.DataFrame] = []
    fuel_frames: list[pd.DataFrame] = []
    interconnector_frames: list[pd.DataFrame] = []

    for chunk_start, chunk_end in _date_chunks(start, end, chunk_days):
        settlement_start = chunk_start.strftime("%Y-%m-%d")
        settlement_end = chunk_end.strftime("%Y-%m-%d")
        exclusive_end = (chunk_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        publish_start = f"{settlement_start}T00:00:00Z"
        publish_end = f"{exclusive_end}T00:00:00Z"

        price_frames.append(
            parse_elexon_mid(client.market_index(settlement_start, exclusive_end))
        )
        demand_frames.append(
            parse_elexon_demand(client.national_demand(publish_start, publish_end))
        )
        fuel_frames.append(
            parse_elexon_fuelhh(client.fuel_half_hourly(settlement_start, settlement_end))
        )
        interconnector_frames.append(
            parse_elexon_interconnectors(
                client.interconnector_outturn(settlement_start, settlement_end)
            )
        )

    output = Path(output_dir)
    paths = {
        "price": _save_frame(
            pd.concat(price_frames, ignore_index=True).drop_duplicates("timestamp", keep="last"),
            output / "elexon_mid.parquet",
        ),
        "demand": _save_frame(
            pd.concat(demand_frames, ignore_index=True).drop_duplicates("timestamp", keep="last"),
            output / "elexon_demand.parquet",
        ),
        "fuel": _save_frame(
            pd.concat(fuel_frames, ignore_index=True).drop_duplicates("timestamp", keep="last"),
            output / "elexon_fuelhh.parquet",
        ),
        "interconnectors": _save_frame(
            pd.concat(interconnector_frames, ignore_index=True).drop_duplicates(
                "timestamp", keep="last"
            ),
            output / "elexon_interconnectors.parquet",
        ),
    }
    return paths


def collect_elexon_units(
    start: str,
    end: str,
    output_dir: str | Path,
    chunk_days: int = 30,
) -> dict[str, Path]:
    """Collect B1610 unit generation and BM-unit reference metadata."""
    client = ElexonClient()
    frames: list[pd.DataFrame] = []
    for chunk_start, chunk_end in _date_chunks(start, end, chunk_days):
        start_text = chunk_start.strftime("%Y-%m-%d")
        exclusive_end = (chunk_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        frames.append(
            parse_unit_generation(client.actual_generation_per_unit(start_text, exclusive_end))
        )
    output = Path(output_dir)
    generation = pd.concat(frames, ignore_index=True).drop_duplicates(
        ["timestamp", "bm_unit"], keep="last"
    )
    reference = parse_bm_unit_reference(client.bm_units())
    return {
        "unit_generation": _save_frame(generation, output / "elexon_unit_generation.parquet"),
        "bm_units": _save_frame(reference, output / "elexon_bm_units.parquet"),
    }


def collect_neso_resource(
    resource_id: str,
    output: str | Path,
) -> Path:
    client = NesoCkanClient()
    records = client.all_records(resource_id)
    frame = parse_neso_records(records)
    return _save_frame(frame, output)


def collect_neso_preset(name: str, output: str | Path) -> Path:
    """Collect and parse a known NESO resource by stable project name."""
    if name not in NESO_RESOURCES:
        raise KeyError(f"Unknown NESO preset {name}; choose from {sorted(NESO_RESOURCES)}")
    records = NesoCkanClient().all_records(NESO_RESOURCES[name])
    if name.startswith("embedded_"):
        frame = parse_embedded_forecasts(records)
    elif name.startswith("inertia_") and name != "inertia_cost":
        frame = parse_inertia(records)
    else:
        frame = parse_neso_records(records)
    return _save_frame(frame, output)


def collect_previous_run_weather(
    sites: list[dict],
    variables: list[str],
    start: str,
    end: str,
    output: str | Path,
) -> Path:
    client = OpenMeteoClient()
    site_frames: list[pd.DataFrame] = []
    for site in sites:
        payload = client.previous_runs(
            float(site["latitude"]),
            float(site["longitude"]),
            variables,
            start,
            end,
        )
        site_frames.append(parse_open_meteo_hourly(payload, str(site["name"])))

    merged = site_frames[0]
    for frame in site_frames[1:]:
        merged = merged.merge(frame, on="timestamp", how="outer")
    return _save_frame(merged.sort_values("timestamp"), output)


def save_raw_payload(payload: object, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return output
