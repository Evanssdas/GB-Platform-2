"""Historical and live source collection helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .data.clients import ElexonClient, NesoCkanClient, OpenMeteoClient
from .data.parsers import (
    parse_elexon_demand,
    parse_elexon_fuelhh,
    parse_elexon_mid,
    parse_neso_records,
    parse_open_meteo_hourly,
)


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
    """Collect and parse APXMIDP, national demand and fuel-type generation."""
    client = ElexonClient()
    price_frames: list[pd.DataFrame] = []
    demand_frames: list[pd.DataFrame] = []
    fuel_frames: list[pd.DataFrame] = []

    for chunk_start, chunk_end in _date_chunks(start, end, chunk_days):
        start_text = chunk_start.strftime("%Y-%m-%d")
        end_text = (chunk_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        price_frames.append(parse_elexon_mid(client.market_index(start_text, end_text)))
        demand_frames.append(parse_elexon_demand(client.national_demand(start_text, end_text)))
        fuel_frames.append(parse_elexon_fuelhh(client.fuel_half_hourly(start_text, end_text)))

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
    }
    return paths


def collect_neso_resource(
    resource_id: str,
    output: str | Path,
) -> Path:
    client = NesoCkanClient()
    records = client.all_records(resource_id)
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
