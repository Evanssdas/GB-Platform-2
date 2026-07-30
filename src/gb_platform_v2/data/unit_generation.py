"""Unit-level generation parsing and explicit storage aggregation."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .parsers import _column, _records, _timestamp_from_source_or_period


def parse_unit_generation(payload: Any) -> pd.DataFrame:
    """Parse B1610 metered energy and convert half-hour MWh to average MW."""
    frame = pd.DataFrame(_records(payload))
    date = _column(frame, ["settlementDate", "settlement_date"], "settlement date")
    period = _column(frame, ["settlementPeriod", "settlement_period"], "settlement period")
    unit = _column(frame, ["bmUnit", "bm_unit"], "BM unit")
    quantity = _column(frame, ["quantity", "meteredVolume", "metered_volume"], "quantity")
    out = pd.DataFrame(
        {
            "timestamp": _timestamp_from_source_or_period(frame, date, period),
            "bm_unit": frame[unit].astype(str),
            "generation_mwh": pd.to_numeric(frame[quantity], errors="coerce"),
        }
    )
    out["generation_mw"] = out["generation_mwh"] * 2.0
    return out.dropna(subset=["timestamp", "generation_mw"]).sort_values(
        ["timestamp", "bm_unit"]
    )


def parse_bm_unit_reference(payload: Any) -> pd.DataFrame:
    frame = pd.DataFrame(_records(payload))
    unit = _column(frame, ["bmUnit", "bm_unit", "elexonBmUnit"], "BM unit")
    result = pd.DataFrame({"bm_unit": frame[unit].astype(str)})
    aliases = {
        "fuel_type": ["fuelType", "fuel_type"],
        "lead_party": ["leadPartyName", "lead_party_name"],
        "name": ["name", "bmUnitName", "bm_unit_name"],
        "generation_capacity_mw": ["generationCapacity", "generation_capacity"],
    }
    for target, candidates in aliases.items():
        try:
            source = _column(frame, candidates, target)
        except KeyError:
            continue
        result[target] = frame[source]
    return result.drop_duplicates("bm_unit", keep="last")


def aggregate_units(
    generation: pd.DataFrame,
    unit_mapping: pd.DataFrame,
    technology: str,
    sign: float = 1.0,
) -> pd.DataFrame:
    """Aggregate only units explicitly labelled in a user-reviewed mapping file."""
    required = {"bm_unit", "technology"}
    missing = required - set(unit_mapping)
    if missing:
        raise KeyError(f"Unit mapping is missing columns: {sorted(missing)}")
    selected = unit_mapping.loc[
        unit_mapping["technology"].astype(str).str.lower().eq(technology.lower()),
        ["bm_unit"],
    ]
    if selected.empty:
        raise ValueError(f"No BM units are explicitly mapped to {technology}")
    joined = generation.merge(selected, on="bm_unit", how="inner")
    output = joined.groupby("timestamp", as_index=False)["generation_mw"].sum()
    output["generation_mw"] *= float(sign)
    return output
