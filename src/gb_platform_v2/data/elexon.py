"""Dataset-specific Elexon Insights Solution client."""

from __future__ import annotations

from typing import Any

import requests


class ElexonClient:
    def __init__(self, timeout: int = 60):
        self.base_url = "https://data.elexon.co.uk/bmrs/api/v1"
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, object] | None = None) -> Any:
        response = requests.get(
            f"{self.base_url}/{path.lstrip('/')}",
            params=params or {},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def dataset_stream(self, dataset: str, params: dict[str, object]) -> Any:
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
        return self.dataset_stream(
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
