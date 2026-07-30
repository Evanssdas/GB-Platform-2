"""ENTSO-E Transparency Platform client and XML parsers.

The token is read from ``ENTSOE_TOKEN`` and is never logged. This module keeps
outturn physical flows separate from point-in-time features: realised flows are
valid actuals or lagged features, while day-ahead scheduled exchanges and
neighbouring auction prices can be used only when their publication timestamp
precedes the configured forecast issue time.
"""

from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
import yaml


DOCUMENT_TYPES = {
    "physical_flow": "A11",
    "scheduled_exchange": "A09",
    "day_ahead_price": "A44",
    "total_load": "A65",
    "actual_generation_per_type": "A75",
}

PROCESS_TYPES = {
    "day_ahead": "A01",
    "realtime": "A16",
}


class EntsoeApiError(RuntimeError):
    """Raised when ENTSO-E returns an acknowledgement/error document."""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_text(element: ET.Element, names: Iterable[str]) -> str | None:
    wanted = set(names)
    for child in element.iter():
        if _local_name(child.tag) in wanted and child.text:
            return child.text.strip()
    return None


def _direct_text(element: ET.Element, names: Iterable[str]) -> str | None:
    wanted = set(names)
    for child in element:
        if _local_name(child.tag) in wanted and child.text:
            return child.text.strip()
    return None


def _duration_minutes(value: str) -> int:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", value)
    if not match:
        raise ValueError(f"Unsupported ENTSO-E resolution: {value}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    total = hours * 60 + minutes
    if total <= 0:
        raise ValueError(f"Invalid ENTSO-E resolution: {value}")
    return total


def _period_value(timestamp: str | pd.Timestamp) -> str:
    value = pd.Timestamp(timestamp)
    if value.tzinfo is None:
        value = value.tz_localize("UTC")
    else:
        value = value.tz_convert("UTC")
    return value.strftime("%Y%m%d%H%M")


def _acknowledgement_error(root: ET.Element) -> EntsoeApiError:
    codes = [
        child.text.strip()
        for child in root.iter()
        if _local_name(child.tag) == "code" and child.text
    ]
    texts = [
        child.text.strip()
        for child in root.iter()
        if _local_name(child.tag) == "text" and child.text
    ]
    message = "; ".join(texts) or "ENTSO-E returned an acknowledgement document"
    if codes:
        message = f"{','.join(codes)}: {message}"
    return EntsoeApiError(message)


def parse_timeseries_xml(
    xml_text: str,
    value_names: Iterable[str],
    output_value: str,
) -> pd.DataFrame:
    """Parse ENTSO-E MarketDocument time series into timestamped rows."""
    root = ET.fromstring(xml_text)
    if _local_name(root.tag) == "Acknowledgement_MarketDocument":
        raise _acknowledgement_error(root)

    document_created = _first_text(root, {"createdDateTime"})
    rows: list[dict] = []
    wanted_values = set(value_names)

    for series in (node for node in root.iter() if _local_name(node.tag) == "TimeSeries"):
        metadata = {
            "series_id": _direct_text(series, {"mRID"}),
            "business_type": _direct_text(series, {"businessType"}),
            "in_domain": _direct_text(series, {"in_Domain.mRID"}),
            "out_domain": _direct_text(series, {"out_Domain.mRID"}),
            "contract_type": _direct_text(series, {"contract_MarketAgreement.type"}),
            "curve_type": _direct_text(series, {"curveType"}),
            "psr_type": _first_text(series, {"psrType"}),
            "currency": _direct_text(series, {"currency_Unit.name"}),
            "measure_unit": _direct_text(
                series,
                {"price_Measure_Unit.name", "quantity_Measure_Unit.name"},
            ),
        }
        for period in (node for node in series if _local_name(node.tag) == "Period"):
            start_text = _first_text(period, {"start"})
            resolution_text = _direct_text(period, {"resolution"})
            if not start_text or not resolution_text:
                continue
            start = pd.Timestamp(start_text)
            if start.tzinfo is None:
                start = start.tz_localize("UTC")
            else:
                start = start.tz_convert("UTC")
            resolution_minutes = _duration_minutes(resolution_text)

            for point in (node for node in period if _local_name(node.tag) == "Point"):
                position_text = _direct_text(point, {"position"})
                value_text = _direct_text(point, wanted_values)
                if not position_text or value_text is None:
                    continue
                position = int(position_text)
                timestamp = start + pd.Timedelta(
                    minutes=(position - 1) * resolution_minutes
                )
                rows.append(
                    {
                        "timestamp": timestamp,
                        output_value: pd.to_numeric(value_text, errors="coerce"),
                        "resolution_minutes": resolution_minutes,
                        "published_at_utc": pd.to_datetime(
                            document_created, utc=True, errors="coerce"
                        ),
                        **metadata,
                    }
                )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.dropna(subset=["timestamp", output_value]).sort_values("timestamp")


def to_half_hourly(frame: pd.DataFrame, value_column: str) -> pd.DataFrame:
    """Convert 15/30/60-minute ENTSO-E power or price rows to 30 minutes."""
    if frame.empty:
        return frame.copy()
    expanded: list[pd.DataFrame] = []
    for resolution, group in frame.groupby("resolution_minutes", dropna=False):
        minutes = int(resolution)
        group = group.copy()
        if minutes == 30:
            expanded.append(group)
        elif minutes == 60:
            first = group.copy()
            second = group.copy()
            second["timestamp"] = second["timestamp"] + pd.Timedelta(minutes=30)
            expanded.extend([first, second])
        elif minutes == 15:
            group["timestamp"] = group["timestamp"].dt.floor("30min")
            metadata = [
                column
                for column in group.columns
                if column not in {value_column, "resolution_minutes"}
            ]
            aggregations = {value_column: "mean"}
            for column in metadata:
                if column != "timestamp":
                    aggregations[column] = "first"
            grouped = group.groupby("timestamp", as_index=False).agg(aggregations)
            grouped["resolution_minutes"] = 30
            expanded.append(grouped)
        else:
            raise ValueError(
                f"Cannot safely convert ENTSO-E resolution {minutes} minutes to 30 minutes"
            )

    result = pd.concat(expanded, ignore_index=True)
    result["resolution_minutes"] = 30
    return result.sort_values("timestamp").drop_duplicates(
        ["timestamp", "in_domain", "out_domain"], keep="last"
    )


def parse_day_ahead_prices(xml_text: str) -> pd.DataFrame:
    frame = parse_timeseries_xml(xml_text, {"price.amount"}, "price_eur_mwh")
    return to_half_hourly(frame, "price_eur_mwh")


def parse_physical_flows(xml_text: str) -> pd.DataFrame:
    frame = parse_timeseries_xml(xml_text, {"quantity"}, "flow_mw")
    return to_half_hourly(frame, "flow_mw")


def parse_scheduled_exchanges(xml_text: str) -> pd.DataFrame:
    frame = parse_timeseries_xml(xml_text, {"quantity"}, "scheduled_exchange_mw")
    return to_half_hourly(frame, "scheduled_exchange_mw")


def combine_directional_flows(
    imports: pd.DataFrame,
    exports: pd.DataFrame,
    prefix: str,
    import_value: str = "flow_mw",
    export_value: str = "flow_mw",
) -> pd.DataFrame:
    """Combine neighbour-to-GB and GB-to-neighbour series using a clear sign."""
    inbound = imports[["timestamp", import_value]].rename(
        columns={import_value: f"{prefix}_import_mw"}
    )
    outbound = exports[["timestamp", export_value]].rename(
        columns={export_value: f"{prefix}_export_mw"}
    )
    merged = inbound.merge(outbound, on="timestamp", how="outer").sort_values("timestamp")
    for column in (f"{prefix}_import_mw", f"{prefix}_export_mw"):
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    merged[f"{prefix}_net_import_mw"] = (
        merged[f"{prefix}_import_mw"] - merged[f"{prefix}_export_mw"]
    )
    return merged


@dataclass
class EntsoeClient:
    token: str | None = None
    timeout: int = 90
    base_url: str = "https://web-api.tp.entsoe.eu/api"
    retries: int = 3

    def __post_init__(self) -> None:
        self.token = self.token or os.getenv("ENTSOE_TOKEN")

    def query(self, params: dict[str, object]) -> str:
        if not self.token:
            raise RuntimeError("ENTSOE_TOKEN is required")
        full_params = {"securityToken": self.token, **params}
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = requests.get(
                    self.base_url,
                    params=full_params,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.text
            except requests.RequestException as error:
                last_error = error
                if attempt + 1 < self.retries:
                    time.sleep(2**attempt)
        raise RuntimeError("ENTSO-E request failed after retries") from last_error

    def day_ahead_prices(self, area: str, start: str, end: str) -> str:
        return self.query(
            {
                "documentType": DOCUMENT_TYPES["day_ahead_price"],
                "in_Domain": area,
                "out_Domain": area,
                "periodStart": _period_value(start),
                "periodEnd": _period_value(end),
            }
        )

    def physical_flow(self, out_domain: str, in_domain: str, start: str, end: str) -> str:
        return self.query(
            {
                "documentType": DOCUMENT_TYPES["physical_flow"],
                "out_Domain": out_domain,
                "in_Domain": in_domain,
                "periodStart": _period_value(start),
                "periodEnd": _period_value(end),
            }
        )

    def scheduled_exchange(
        self,
        out_domain: str,
        in_domain: str,
        start: str,
        end: str,
    ) -> str:
        return self.query(
            {
                "documentType": DOCUMENT_TYPES["scheduled_exchange"],
                "contract_MarketAgreement.Type": "A01",
                "out_Domain": out_domain,
                "in_Domain": in_domain,
                "periodStart": _period_value(start),
                "periodEnd": _period_value(end),
            }
        )


def load_entsoe_config(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if "areas" not in config or "borders" not in config:
        raise KeyError("ENTSO-E config requires areas and borders")
    return config
