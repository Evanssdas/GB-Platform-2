"""Historical and live source collection helpers.

Public collection functions use one convention throughout the project:
``start`` is inclusive and ``end`` is exclusive. Source-specific inclusive end
filters are derived internally.
"""

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


def _date(value: str, label: str) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is not None:
        parsed = parsed.tz_convert("UTC").tz_localize(None)
    parsed = parsed.normalize()
    if pd.isna(parsed):
        raise ValueError(f"Invalid {label}: {value}")
    return parsed


def _validate_window(start: str, end: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    first = _date(start, "start date")
    exclusive_end = _date(end, "exclusive end date")
    if exclusive_end <= first:
        raise ValueError(
            f"end must be later than start under the exclusive-end convention: "
            f"start={start}, end={end}"
        )
    return first, exclusive_end


def _date_chunks(
    start: str,
    end: str,
    days: int = 30,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Return non-overlapping ``[start, end)`` date chunks."""
    if days < 1:
        raise ValueError("chunk days must be at least 1")
    first, exclusive_end = _validate_window(start, end)
    chunks: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    cursor = first
    while cursor < exclusive_end:
        chunk_exclusive_end = min(cursor + pd.Timedelta(days=days), exclusive_end)
        chunks.append((cursor, chunk_exclusive_end))
        cursor = chunk_exclusive_end
    return chunks


def _save_frame(frame: pd.DataFrame, path: str | Path) -> Path:
    if frame.empty:
        raise ValueError(f"Refusing to save an empty parsed dataset to {path}")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".csv":
        frame.to_csv(output, index=False)
    else:
        frame.to_parquet(output, index=False)
    return output


def _combine(
    frames: list[pd.DataFrame],
    label: str,
    subset: str | list[str],
) -> pd.DataFrame:
    usable = [frame for frame in frames if not frame.empty]
    if not usable:
        raise ValueError(f"Elexon returned no parsed rows for {label}")
    return (
        pd.concat(usable, ignore_index=True)
        .sort_values(subset if isinstance(subset, str) else subset)
        .drop_duplicates(subset, keep="last")
        .reset_index(drop=True)
    )


def collect_elexon_core(
    start: str,
    end: str,
    output_dir: str | Path,
    chunk_days: int = 30,
) -> dict[str, Path]:
    """Collect APXMIDP, demand, fuel generation and interconnector outturn.

    Parameters use ``[start, end)`` delivery-date semantics. For example,
    ``2025-07-01`` to ``2025-08-01`` collects July 2025 only.
    """
    client = ElexonClient()
    price_frames: list[pd.DataFrame] = []
    demand_frames: list[pd.DataFrame] = []
    fuel_frames: list[pd.DataFrame] = []
    interconnector_frames: list[pd.DataFrame] = []

    for chunk_start, chunk_exclusive_end in _date_chunks(start, end, chunk_days):
        settlement_start = chunk_start.strftime("%Y-%m-%d")
        exclusive_end = chunk_exclusive_end.strftime("%Y-%m-%d")
        inclusive_end = (chunk_exclusive_end - pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        price_frames.append(
            parse_elexon_mid(client.market_index(settlement_start, exclusive_end))
        )
        demand_frames.append(
            parse_elexon_demand(client.national_demand(settlement_start, inclusive_end))
        )
        fuel_frames.append(
            parse_elexon_fuelhh(client.fuel_half_hourly(settlement_start, inclusive_end))
        )
        interconnector_frames.append(
            parse_elexon_interconnectors(
                client.interconnector_outturn(settlement_start, inclusive_end)
            )
        )

    output = Path(output_dir)
    price = _combine(price_frames, "APXMIDP", "timestamp")
    demand = _combine(demand_frames, "national demand", "timestamp")
    fuel = _combine(fuel_frames, "fuel generation", "timestamp")
    interconnectors = _combine(interconnector_frames, "interconnector outturn", "timestamp")

    expected_start = pd.Timestamp(start, tz="UTC")
    expected_end = pd.Timestamp(end, tz="UTC")
    for label, frame in {
        "price": price,
        "demand": demand,
        "fuel": fuel,
        "interconnectors": interconnectors,
    }.items():
        timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        if timestamps.isna().any():
            raise ValueError(f"{label} contains invalid timestamps")
        outside = ~timestamps.between(expected_start, expected_end, inclusive="left")
        if outside.any():
            raise ValueError(
                f"{label} contains {int(outside.sum())} rows outside the requested [start, end) window"
            )

    return {
        "price": _save_frame(price, output / "elexon_mid.parquet"),
        "demand": _save_frame(demand, output / "elexon_demand.parquet"),
        "fuel": _save_frame(fuel, output / "elexon_fuelhh.parquet"),
        "interconnectors": _save_frame(
            interconnectors,
            output / "elexon_interconnectors.parquet",
        ),
    }


def collect_elexon_units(
    start: str,
    end: str,
    output_dir: str | Path,
    chunk_days: int = 30,
) -> dict[str, Path]:
    """Collect B1610 unit generation and BM-unit metadata using ``[start, end)``."""
    client = ElexonClient()
    frames: list[pd.DataFrame] = []
    for chunk_start, chunk_exclusive_end in _date_chunks(start, end, chunk_days):
        frames.append(
            parse_unit_generation(
                client.actual_generation_per_unit(
                    chunk_start.strftime("%Y-%m-%d"),
                    chunk_exclusive_end.strftime("%Y-%m-%d"),
                )
            )
        )
    output = Path(output_dir)
    generation = _combine(frames, "B1610 unit generation", ["timestamp", "bm_unit"])
    reference = parse_bm_unit_reference(client.bm_units())
    return {
        "unit_generation": _save_frame(
            generation,
            output / "elexon_unit_generation.parquet",
        ),
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
    """Collect weather for ``[start, end)`` while adapting to inclusive API dates."""
    first, exclusive_end = _validate_window(start, end)
    api_end_inclusive = (exclusive_end - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    api_start = first.strftime("%Y-%m-%d")

    client = OpenMeteoClient()
    site_frames: list[pd.DataFrame] = []
    for site in sites:
        payload = client.previous_runs(
            float(site["latitude"]),
            float(site["longitude"]),
            variables,
            api_start,
            api_end_inclusive,
        )
        frame = parse_open_meteo_hourly(payload, str(site["name"]))
        if frame.empty:
            raise ValueError(f"Open-Meteo returned no parsed rows for site {site['name']}")
        site_frames.append(frame)

    merged = site_frames[0]
    for frame in site_frames[1:]:
        merged = merged.merge(frame, on="timestamp", how="outer", validate="one_to_one")
    timestamps = pd.to_datetime(merged["timestamp"], utc=True, errors="coerce")
    mask = timestamps.between(
        pd.Timestamp(first, tz="UTC"),
        pd.Timestamp(exclusive_end, tz="UTC"),
        inclusive="left",
    )
    merged = merged.loc[mask].sort_values("timestamp").drop_duplicates("timestamp")
    return _save_frame(merged, output)


def save_raw_payload(payload: object, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return output
