"""Resilient ENTSO-E collection with safe partial-result handling.

ENTSO-E occasionally returns transient HTTP 429/5xx responses. This module
uses longer backoff, prevents credentials from appearing in raised errors,
isolates individual products/borders, and always writes a status manifest.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Callable

import pandas as pd
import requests

from .data.entsoe import (
    EntsoeApiError,
    EntsoeClient,
    combine_directional_flows,
    load_entsoe_config,
    parse_day_ahead_prices,
    parse_physical_flows,
    parse_scheduled_exchanges,
)


class SafeEntsoeHttpError(RuntimeError):
    """HTTP failure that never contains the request URL or security token."""

    def __init__(self, status_code: int | None, message: str):
        super().__init__(message)
        self.status_code = status_code


def _redact(message: object) -> str:
    text = str(message)
    text = re.sub(r"securityToken=[^&\s]+", "securityToken=***", text, flags=re.I)
    text = re.sub(r"(?i)(token)(\s*[:=]\s*)[^\s&]+", r"\1\2***", text)
    return " ".join(text.split())[:500]


def _retry_delay(response: requests.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(120.0, max(1.0, float(retry_after)))
            except ValueError:
                pass
    return min(60.0, 5.0 * (2**attempt))


class ResilientEntsoeClient(EntsoeClient):
    """ENTSO-E client with safe errors and retry-aware backoff."""

    def query(self, params: dict[str, object]) -> str:
        if not self.token:
            raise SafeEntsoeHttpError(None, "ENTSOE_TOKEN is required")

        full_params = {"securityToken": self.token, **params}
        retryable = {429, 500, 502, 503, 504}
        last_status: int | None = None
        last_kind = "request failure"

        for attempt in range(self.retries):
            response: requests.Response | None = None
            try:
                response = requests.get(
                    self.base_url,
                    params=full_params,
                    headers={"User-Agent": "GB-Power-Market-Platform-V2/0.1"},
                    timeout=self.timeout,
                )
                last_status = response.status_code

                if response.status_code == 200:
                    return response.text

                if response.status_code in {401, 403}:
                    raise SafeEntsoeHttpError(
                        response.status_code,
                        f"ENTSO-E authentication failed with HTTP {response.status_code}",
                    )

                if response.status_code not in retryable:
                    body = _redact(response.text)
                    raise SafeEntsoeHttpError(
                        response.status_code,
                        f"ENTSO-E returned HTTP {response.status_code}: {body}",
                    )

                last_kind = f"HTTP {response.status_code}"
            except SafeEntsoeHttpError:
                raise
            except requests.RequestException as error:
                last_kind = type(error).__name__

            if attempt + 1 < self.retries:
                delay = _retry_delay(response, attempt)
                print(
                    f"ENTSO-E {last_kind}; retrying in {delay:.0f}s "
                    f"(attempt {attempt + 2}/{self.retries})",
                    flush=True,
                )
                time.sleep(delay)

        status_text = f"HTTP {last_status}" if last_status is not None else last_kind
        raise SafeEntsoeHttpError(
            last_status,
            f"ENTSO-E remained unavailable after {self.retries} attempts ({status_text})",
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


def collect_entsoe_markets_resilient(
    config_path: str | Path,
    start: str,
    end: str,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Collect all available ENTSO-E products and preserve partial success."""
    config = load_entsoe_config(config_path)
    areas = config["areas"]
    products = config.get("products", {})
    gb = areas["GB"]
    client = ResilientEntsoeClient(retries=5)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    saved: dict[str, Path] = {}
    items: list[dict[str, object]] = []
    state = {
        "consecutive_server_failures": 0,
        "circuit_open": False,
        "auth_failed": False,
    }

    def run_item(label: str, operation: Callable[[], pd.DataFrame]) -> pd.DataFrame | None:
        if state["auth_failed"]:
            items.append({"item": label, "status": "skipped", "reason": "authentication_failed"})
            return None
        if state["circuit_open"]:
            items.append({"item": label, "status": "skipped", "reason": "service_circuit_open"})
            return None

        try:
            frame = operation()
            if frame.empty:
                items.append({"item": label, "status": "no_rows", "rows": 0})
                state["consecutive_server_failures"] = 0
                return None
            items.append({"item": label, "status": "success", "rows": int(len(frame))})
            state["consecutive_server_failures"] = 0
            time.sleep(0.5)
            return frame
        except SafeEntsoeHttpError as error:
            status = error.status_code
            items.append(
                {
                    "item": label,
                    "status": "failed",
                    "status_code": status,
                    "error_type": type(error).__name__,
                    "message": _redact(error),
                }
            )
            if status in {401, 403}:
                state["auth_failed"] = True
            if status in {500, 502, 503, 504}:
                state["consecutive_server_failures"] += 1
                if state["consecutive_server_failures"] >= 2:
                    state["circuit_open"] = True
            return None
        except EntsoeApiError as error:
            items.append(
                {
                    "item": label,
                    "status": "unavailable",
                    "error_type": type(error).__name__,
                    "message": _redact(error),
                }
            )
            state["consecutive_server_failures"] = 0
            return None
        except Exception as error:  # Parser/schema failures must be visible but isolated.
            items.append(
                {
                    "item": label,
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "message": _redact(error),
                }
            )
            state["consecutive_server_failures"] = 0
            return None

    enabled_borders = [
        (name, border)
        for name, border in config["borders"].items()
        if border.get("enabled", False)
    ]

    if products.get("neighbouring_day_ahead_prices", True):
        price_frames: list[pd.DataFrame] = []
        for name, border in enabled_borders:
            neighbour_eic = areas[border["neighbour"]]
            frame = run_item(
                f"day_ahead_price.{name}",
                lambda eic=neighbour_eic: parse_day_ahead_prices(
                    client.day_ahead_prices(eic, start, end)
                ),
            )
            if frame is not None:
                price_frames.append(
                    frame[["timestamp", "price_eur_mwh", "published_at_utc"]].rename(
                        columns={
                            "price_eur_mwh": f"{name}_day_ahead_price_eur_mwh",
                            "published_at_utc": f"{name}_price_published_at_utc",
                        }
                    )
                )
        if price_frames:
            prices = price_frames[0]
            for frame in price_frames[1:]:
                prices = prices.merge(frame, on="timestamp", how="outer")
            saved["prices"] = _save(
                prices.sort_values("timestamp"), output / "neighbour_prices.parquet"
            )

    if products.get("physical_flows", True):
        border_frames: list[pd.DataFrame] = []
        for name, border in enabled_borders:
            neighbour = areas[border["neighbour"]]

            def physical_operation(
                neighbour_eic: str = neighbour,
                border_name: str = name,
            ) -> pd.DataFrame:
                inbound = parse_physical_flows(
                    client.physical_flow(neighbour_eic, gb, start, end)
                )
                outbound = parse_physical_flows(
                    client.physical_flow(gb, neighbour_eic, start, end)
                )
                return combine_directional_flows(inbound, outbound, border_name)

            frame = run_item(f"physical_flow.{name}", physical_operation)
            if frame is not None:
                border_frames.append(frame)
        flows = _join_net_imports(border_frames, "_net_import_mw")
        if not flows.empty:
            saved["physical_flows"] = _save(flows, output / "physical_flows.parquet")

    if products.get("day_ahead_scheduled_exchanges", True):
        schedule_frames: list[pd.DataFrame] = []
        for name, border in enabled_borders:
            neighbour = areas[border["neighbour"]]

            def schedule_operation(
                neighbour_eic: str = neighbour,
                border_name: str = name,
            ) -> pd.DataFrame:
                inbound = parse_scheduled_exchanges(
                    client.scheduled_exchange(neighbour_eic, gb, start, end)
                )
                outbound = parse_scheduled_exchanges(
                    client.scheduled_exchange(gb, neighbour_eic, start, end)
                )
                return combine_directional_flows(
                    inbound,
                    outbound,
                    f"{border_name}_scheduled",
                    import_value="scheduled_exchange_mw",
                    export_value="scheduled_exchange_mw",
                )

            frame = run_item(f"scheduled_exchange.{name}", schedule_operation)
            if frame is not None:
                schedule_frames.append(frame)
        schedules = _join_net_imports(schedule_frames, "_net_import_mw")
        if not schedules.empty:
            schedules = schedules.rename(columns={"net_import_mw": "scheduled_net_import_mw"})
            saved["scheduled_exchanges"] = _save(
                schedules, output / "scheduled_exchanges.parquet"
            )

    successful_items = sum(item["status"] == "success" for item in items)
    failed_items = sum(item["status"] in {"failed", "unavailable"} for item in items)
    overall = "success" if failed_items == 0 else "partial" if saved else "failed"
    manifest = {
        "source": "ENTSO-E Transparency Platform",
        "requested_start_utc": str(start),
        "requested_end_utc": str(end),
        "overall_status": overall,
        "successful_items": successful_items,
        "failed_or_unavailable_items": failed_items,
        "circuit_opened": bool(state["circuit_open"]),
        "items": items,
        "saved_files": {name: str(path) for name, path in saved.items()},
    }
    manifest_path = output / "collection_status.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    saved["status"] = manifest_path

    if not any(name != "status" for name in saved):
        raise RuntimeError(
            "ENTSO-E returned no usable datasets; collection_status.json contains safe diagnostics"
        )
    return saved
