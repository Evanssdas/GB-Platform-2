"""Create auditable storage series from reviewed BM-unit mappings."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_storage_series(
    generation_path: str | Path,
    mapping_path: str | Path,
    output_path: str | Path,
) -> pd.DataFrame:
    generation = pd.read_parquet(generation_path)
    mapping = pd.read_csv(mapping_path)
    required_generation = {"timestamp", "bm_unit", "generation_mw"}
    required_mapping = {"bm_unit", "technology", "sign"}
    if required_generation - set(generation):
        raise KeyError(f"Unit generation missing {sorted(required_generation - set(generation))}")
    if required_mapping - set(mapping):
        raise KeyError(f"Unit mapping missing {sorted(required_mapping - set(mapping))}")
    if mapping["bm_unit"].astype(str).str.startswith("REPLACE_").any():
        raise ValueError("Review and replace placeholder BM-unit mappings before aggregation")

    joined = generation.merge(mapping, on="bm_unit", how="inner")
    joined["signed_mw"] = joined["generation_mw"] * pd.to_numeric(joined["sign"])
    grouped = joined.pivot_table(
        index="timestamp",
        columns="technology",
        values="signed_mw",
        aggfunc="sum",
        fill_value=0.0,
    )
    grouped.columns = [f"{column}_net_mw" for column in grouped.columns]
    grouped = grouped.reset_index()
    if "battery_net_mw" not in grouped:
        raise ValueError("No reviewed battery units were present in the mapping")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    grouped.to_parquet(output, index=False)
    return grouped
