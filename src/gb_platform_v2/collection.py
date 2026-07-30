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


def _settlement_window_utc(start: str, end: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Convert GB settlement-date boundaries to UTC.

    Settlement dates are Europe/London calendar dates. During BST, local
    midnight is 23:00 UTC on the preceding civil day, so validating against UTC
    midnight would wrongly reject valid settlement periods.
    """
    first, exclusive_end = _validate_window(start, end)
    start_utc = first.tz_localize("Europe/London").tz_convert("UTC")
    end_utc = exclusive_end.tz_localize("Europe/London").tz_convert("UTC")
    return start_utc, end_utc


def _trim_timestamp_window(
    frame: pd.DataFrame,
    label: str,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    *,
    spill_tolerance: pd.Timedelta = pd.Timedelta(days=1),
) -> pd.DataFrame:
    """Keep ``[start_utc, end_utc)`` rows and tolerate API boundary spill.

    Several Elexon endpoints treat their upper bound as inclusive and may return
    the first row at the next boundary. A small adjacent spill is trimmed, while
    rows far from the requested interval still fail loudly.
    """
    if "timestamp" not in frame:
        raise KeyError(f"{label} is missing timestamp")
    out = frame.copy()
    timestamps = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    if timestamps.isna().any():
        raise ValueError(f"{label} contains invalid timestamps")
    out["timestamp"] = timestamps

    inside = timestamps.between(start_utc, end_utc, inclusive="left")
    if (~inside).any():
        outside = timestamps.loc[~inside]
        too_early = outside < (start_utc - spill_tolerance)
        too_late = outside >= (end_utc + spill_tolerance)
        if too_early.any() or too_late.any():
            raise ValueError(
                f"{label} contains rows materially outside the requested settlement window: "
                f"min={outside.min().isoformat()}, max={outside.max().isoformat()}"
            )
        print(
            f"Trimmed {int((~inside).sum())} {label} boundary row(s) outside "
            f"[{start_utc.isoformat()}, {end_utc.isoformat()})",
            flush=True,
        )
        out = out.loc[inside].copy()

    if out.empty:
        raise ValueError(f"{label} has no rows inside the requested settlement window")
    return out.sort_values("timestamp").reset_index(drop=True)


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
    """Collect APXMIDP, demand, fuel generation and interconnector outturn."""
    client = ElexonClient()
    price_frames: list[pd.DataFrame] = []
    demand_frames: list[pd.DataFrame] = []
    fuel_frames: list[pd.DataFrame] = []
    interconnector_frames: list[pd.DataFrame] = []

    for chunk_start, chunk_exclusive_end in _date_chunks(start, end, chunk_days):
        settlement_start = chunk_start.strftime("%Y-%m-%d")
        exclusive_end = chunk_exclusive_end.strftime("%Y-%m-%d")
        inclusive_end = (chunk_exclusive_end - pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        price_frames.append(parse_elexon_mid(client.market_index(settlement_start, exclusive_end)))
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
    start_utc, end_utc = _settlement_window_utc(start, end)
    price = _trim_timestamp_window(
        _combine(price_frames, "APXMIDP", "timestamp"),
        "price",
        start_utc,
        end_utc,
    )
    demand = _trim_timestamp_window(
        _combine(demand_frames, "national demand", "timestamp"),
        "demand",
        start_utc,
        end_utc,
    )
    fuel = _trim_timestamp_window(
        _combine(fuel_frames, "fuel generation", "timestamp"),
        "fuel",
        start_utc,
        end_utc,
    )
    interconnectors = _trim_timestamp_window(
        _combine(interconnector_frames, "interconnector outturn", "timestamp"),
        "interconnectors",
        start_utc,
        end_utc,
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
    start_utc, end_utc = _settlement_window_utc(start, end)
    generation = _trim_timestamp_window(
        _combine(frames, "B1610 unit generation", ["timestamp", "bm_unit"]),
        "B1610 unit generation",
        start_utc,
        end_utc,
    )
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


def _parse_neso_preset(name: str, records: list[dict]) -> pd.DataFrame:
    if name.startswith("embedded_"):
        return parse_embedded_forecasts(records)
    if name.startswith("inertia_") and name != "inertia_cost":
        return parse_inertia(records)
    return parse_neso_records(records)


def collect_neso_preset(
    name: str,
    output: str | Path,
    start: str | None = None,
    end: str | None = None,
) -> Path:
    """Collect and parse a known NESO resource.

    When ``start`` and ``end`` are supplied, only the requested delivery-date
    window is fetched through bounded CKAN SQL pagination.
    """
    if name not in NESO_RESOURCES:
        raise KeyError(f"Unknown NESO preset {name}; choose from {sorted(NESO_RESOURCES)}")
    client = NesoCkanClient()
    resource_id = NESO_RESOURCES[name]
    if (start is None) != (end is None):
        raise ValueError("NESO preset collection requires both start and end, or neither")
    if start is not None and end is not None:
        first, exclusive_end = _validate_window(start, end)
        records = client.records_for_date_window(
            resource_id,
            first.strftime("%Y-%m-%d"),
            exclusive_end.strftime("%Y-%m-%d"),
        )
    else:
        records = client.all_records(resource_id)
    if not records:
        raise ValueError(f"NESO returned no records for preset {name}")
    frame = _parse_neso_preset(name, records)
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
