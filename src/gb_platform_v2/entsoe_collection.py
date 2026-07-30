"""Collection orchestration for ENTSO-E neighbouring-market data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .data.entsoe import (
    EntsoeClient,
    combine_directional_flows,
    load_entsoe_config,
    parse_day_ahead_prices,
    parse_physical_flows,
    parse_scheduled_exchanges,
)


def _save(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".csv":
        frame.to_csv(path, index=False)
    else:
        frame.to_parquet(path, index=False)
    return path


def _join_net_imports(frames: list[pd.DataFrame], value_suffix: str) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="timestamp", how="outer")
    value_columns = [column for column in merged if column.endswith(value_suffix)]
    merged[value_columns] = merged[value_columns].fillna(0.0)
    merged["net_import_mw"] = merged[value_columns].sum(axis=1)
    return merged.sort_values("timestamp")


def collect_entsoe_markets(
    config_path: str | Path,
    start: str,
    end: str,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Collect prices, physical flows and scheduled exchanges around GB.

    Physical flows are realised outturns and must not be used contemporaneously
    in a day-ahead forecast. Scheduled exchanges and neighbouring prices need a
    point-in-time publication check before entering training features.
    """
    config = load_entsoe_config(config_path)
    areas = config["areas"]
    products = config.get("products", {})
    gb = areas["GB"]
    client = EntsoeClient()
    output = Path(output_dir)
    saved: dict[str, Path] = {}

    if products.get("neighbouring_day_ahead_prices", True):
        price_frames: list[pd.DataFrame] = []
        for name, border in config["borders"].items():
            if not border.get("enabled", False):
                continue
            neighbour_name = border["neighbour"]
            neighbour_eic = areas[neighbour_name]
            frame = parse_day_ahead_prices(
                client.day_ahead_prices(neighbour_eic, start, end)
            )
            frame = frame[["timestamp", "price_eur_mwh", "published_at_utc"]].rename(
                columns={
                    "price_eur_mwh": f"{name}_day_ahead_price_eur_mwh",
                    "published_at_utc": f"{name}_price_published_at_utc",
                }
            )
            price_frames.append(frame)
        prices = price_frames[0]
        for frame in price_frames[1:]:
            prices = prices.merge(frame, on="timestamp", how="outer")
        saved["prices"] = _save(prices.sort_values("timestamp"), output / "neighbour_prices.parquet")

    if products.get("physical_flows", True):
        border_frames: list[pd.DataFrame] = []
        for name, border in config["borders"].items():
            if not border.get("enabled", False):
                continue
            neighbour = areas[border["neighbour"]]
            inbound = parse_physical_flows(
                client.physical_flow(neighbour, gb, start, end)
            )
            outbound = parse_physical_flows(
                client.physical_flow(gb, neighbour, start, end)
            )
            border_frames.append(combine_directional_flows(inbound, outbound, name))
        flows = _join_net_imports(border_frames, "_net_import_mw")
        saved["physical_flows"] = _save(flows, output / "physical_flows.parquet")

    if products.get("day_ahead_scheduled_exchanges", True):
        schedule_frames: list[pd.DataFrame] = []
        for name, border in config["borders"].items():
            if not border.get("enabled", False):
                continue
            neighbour = areas[border["neighbour"]]
            inbound = parse_scheduled_exchanges(
                client.scheduled_exchange(neighbour, gb, start, end)
            )
            outbound = parse_scheduled_exchanges(
                client.scheduled_exchange(gb, neighbour, start, end)
            )
            schedule_frames.append(
                combine_directional_flows(
                    inbound,
                    outbound,
                    f"{name}_scheduled",
                    import_value="scheduled_exchange_mw",
                    export_value="scheduled_exchange_mw",
                )
            )
        schedules = _join_net_imports(schedule_frames, "_net_import_mw")
        schedules = schedules.rename(columns={"net_import_mw": "scheduled_net_import_mw"})
        saved["scheduled_exchanges"] = _save(
            schedules, output / "scheduled_exchanges.parquet"
        )

    return saved
