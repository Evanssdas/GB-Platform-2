"""Dataset-specific Elexon Insights Solution client."""

from __future__ import annotations

import json
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ElexonApiError(RuntimeError):
    """Safe, source-specific Elexon HTTP or response error."""

    def __init__(self, status_code: int | None, path: str, detail: str):
        self.status_code = status_code
        self.path = path
        self.detail = detail
        status = f"HTTP {status_code}" if status_code is not None else "request failure"
        super().__init__(f"Elexon {status} for /{path.lstrip('/')}: {detail}")


def _response_detail(response: requests.Response) -> str:
    """Return a compact diagnostic without echoing a complete request URL."""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            for key in ("message", "detail", "title", "error", "errors"):
                if key in payload:
                    return " ".join(str(payload[key]).split())[:800]
        return " ".join(json.dumps(payload, default=str).split())[:800]
    except (ValueError, TypeError):
        return " ".join(response.text.split())[:800] or "No response body"


class ElexonClient:
    """Small source-aware client for Elexon Insights Solution endpoints.

    Dataset publication endpoints, optimised dataset streams and opinionated
    market endpoints have different parameter contracts. Each public method
    below binds one verified route to its matching filters rather than treating
    every Elexon product as a generic ``datasets/<name>/stream`` request.
    """

    def __init__(self, timeout: int = 60, retries: int = 4):
        self.base_url = "https://data.elexon.co.uk/bmrs/api/v1"
        self.timeout = timeout
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(
            {
                "User-Agent": "GB-Power-Market-Platform-V2/0.1",
                "Accept": "application/json",
            }
        )

    def _get(self, path: str, params: dict[str, object] | None = None) -> Any:
        try:
            response = self.session.get(
                f"{self.base_url}/{path.lstrip('/')}",
                params=params or {},
                timeout=self.timeout,
            )
        except requests.RequestException as error:
            raise ElexonApiError(None, path, type(error).__name__) from error

        if response.status_code >= 400:
            raise ElexonApiError(
                response.status_code,
                path,
                _response_detail(response),
            )
        try:
            return response.json()
        except ValueError as error:
            raise ElexonApiError(
                response.status_code,
                path,
                "Response was not valid JSON",
            ) from error

    def dataset(self, dataset: str, params: dict[str, object]) -> Any:
        """Request a standard wrapped publication dataset endpoint."""
        return self._get(f"datasets/{dataset}", params)

    def dataset_stream(self, dataset: str, params: dict[str, object]) -> Any:
        """Request an optimised dataset stream when one officially exists."""
        return self._get(f"datasets/{dataset}/stream", params)

    def market_index(self, start: str, end_exclusive: str) -> Any:
        return self.dataset_stream(
            "MID",
            {"from": start, "to": end_exclusive, "dataProvider": "APXMIDP"},
        )

    def fuel_half_hourly(self, start: str, end_inclusive: str) -> Any:
        return self.dataset_stream(
            "FUELHH",
            {
                "settlementDateFrom": start,
                "settlementDateTo": end_inclusive,
            },
        )

    def national_demand(self, start: str, end_inclusive: str) -> Any:
        """Retrieve half-hourly INDO/ITSDO outturn by settlement date.

        This deliberately uses the dedicated historical outturn stream. The raw
        ``datasets/INDO`` route is publication-time oriented and remains
        available separately for revision-aware ingestion.
        """
        return self._get(
            "demand/outturn/stream",
            {
                "settlementDateFrom": start,
                "settlementDateTo": end_inclusive,
            },
        )

    def national_demand_publications(
        self,
        publish_start: str,
        publish_end: str,
    ) -> Any:
        """Retrieve raw INDO publications when revision history is required."""
        return self.dataset(
            "INDO",
            {
                "publishDateTimeFrom": publish_start,
                "publishDateTimeTo": publish_end,
                "format": "json",
            },
        )

    def interconnector_outturn(self, start: str, end_inclusive: str) -> Any:
        return self._get(
            "generation/outturn/interconnectors",
            {
                "settlementDateFrom": start,
                "settlementDateTo": end_inclusive,
            },
        )

    def actual_generation_per_unit(self, start: str, end_exclusive: str) -> Any:
        return self.dataset_stream("B1610", {"from": start, "to": end_exclusive})

    def bm_units(self) -> Any:
        return self._get("reference/bmunits/all")

    def physical_notifications(self, start: str, end_exclusive: str) -> Any:
        return self.dataset_stream("PN", {"from": start, "to": end_exclusive})

    def maximum_export_limits(self, start: str, end_exclusive: str) -> Any:
        return self.dataset_stream("MELS", {"from": start, "to": end_exclusive})

    def maximum_import_limits(self, start: str, end_exclusive: str) -> Any:
        return self.dataset_stream("MILS", {"from": start, "to": end_exclusive})

    def maximum_delivery_bid(self, start: str, end_exclusive: str) -> Any:
        return self.dataset_stream("MDB", {"from": start, "to": end_exclusive})

    def maximum_delivery_offer(self, start: str, end_exclusive: str) -> Any:
        return self.dataset_stream("MDO", {"from": start, "to": end_exclusive})

    def bid_offer_data(self, start: str, end_exclusive: str) -> Any:
        return self.dataset_stream("BOD", {"from": start, "to": end_exclusive})

    def accepted_actions(self, start: str, end_exclusive: str) -> Any:
        return self.dataset_stream("BOALF", {"from": start, "to": end_exclusive})
