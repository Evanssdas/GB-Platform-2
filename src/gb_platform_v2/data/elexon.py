"""Dataset-specific Elexon Insights Solution client."""

from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ElexonClient:
    """Small source-aware client for Elexon Insights Solution endpoints.

    Elexon exposes both ordinary dataset routes and optimised ``/stream``
    routes. Not every dataset has a stream endpoint; in particular, INDO must
    be requested from ``/datasets/INDO``.
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
            {"User-Agent": "GB-Power-Market-Platform-V2/0.1"}
        )

    def _get(self, path: str, params: dict[str, object] | None = None) -> Any:
        response = self.session.get(
            f"{self.base_url}/{path.lstrip('/')}",
            params=params or {},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def dataset(self, dataset: str, params: dict[str, object]) -> Any:
        """Request a standard wrapped dataset endpoint."""
        return self._get(f"datasets/{dataset}", params)

    def dataset_stream(self, dataset: str, params: dict[str, object]) -> Any:
        """Request an optimised stream endpoint when one officially exists."""
        return self._get(f"datasets/{dataset}/stream", params)

    def market_index(self, start: str, end: str) -> Any:
        return self.dataset_stream(
            "MID",
            {"from": start, "to": end, "dataProvider": "APXMIDP"},
        )

    def fuel_half_hourly(self, start: str, end: str) -> Any:
        return self.dataset_stream(
            "FUELHH",
            {"settlementDateFrom": start, "settlementDateTo": end},
        )

    def national_demand(self, publish_start: str, publish_end: str) -> Any:
        # INDO has no /stream route in the Elexon API. Its response is a
        # wrapped JSON object containing a ``data`` array, which the parser
        # already supports.
        return self.dataset(
            "INDO",
            {
                "publishDateTimeFrom": publish_start,
                "publishDateTimeTo": publish_end,
            },
        )

    def interconnector_outturn(self, start: str, end: str) -> Any:
        return self._get(
            "generation/outturn/interconnectors",
            {"settlementDateFrom": start, "settlementDateTo": end},
        )

    def actual_generation_per_unit(self, start: str, end: str) -> Any:
        return self.dataset_stream("B1610", {"from": start, "to": end})

    def bm_units(self) -> Any:
        return self._get("reference/bmunits/all")

    def physical_notifications(self, start: str, end: str) -> Any:
        return self.dataset_stream("PN", {"from": start, "to": end})

    def maximum_export_limits(self, start: str, end: str) -> Any:
        return self.dataset_stream("MELS", {"from": start, "to": end})

    def maximum_import_limits(self, start: str, end: str) -> Any:
        return self.dataset_stream("MILS", {"from": start, "to": end})

    def maximum_delivery_bid(self, start: str, end: str) -> Any:
        return self.dataset_stream("MDB", {"from": start, "to": end})

    def maximum_delivery_offer(self, start: str, end: str) -> Any:
        return self.dataset_stream("MDO", {"from": start, "to": end})

    def bid_offer_data(self, start: str, end: str) -> Any:
        return self.dataset_stream("BOD", {"from": start, "to": end})

    def accepted_actions(self, start: str, end: str) -> Any:
        return self.dataset_stream("BOALF", {"from": start, "to": end})
