"""Explicit clients for public GB and European data services.

Clients return raw payloads. Parsers must validate timestamps, units, revisions,
sign conventions and product definitions before modelling.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import requests


@dataclass
class JsonClient:
    base_url: str
    timeout: int = 60

    def get(self, path: str, params: dict | None = None) -> dict:
        response = requests.get(
            f"{self.base_url.rstrip('/')}/{path.lstrip('/')}",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Expected a JSON object")
        return payload


class ElexonClient(JsonClient):
    """Elexon Insights Solution API client using raw dataset streams."""

    def __init__(self, timeout: int = 60):
        super().__init__("https://data.elexon.co.uk/bmrs/api/v1", timeout)

    def dataset_stream(
        self,
        dataset: str,
        from_date: str,
        to_date: str,
        **parameters: object,
    ) -> dict:
        params = {"from": from_date, "to": to_date, **parameters}
        return self.get(f"datasets/{dataset}/stream", params)

    def market_index(self, from_date: str, to_date: str) -> dict:
        return self.dataset_stream(
            "MID",
            from_date,
            to_date,
            dataProviders="APXMIDP",
        )

    def fuel_half_hourly(self, from_date: str, to_date: str) -> dict:
        return self.dataset_stream("FUELHH", from_date, to_date)

    def national_demand(self, from_date: str, to_date: str) -> dict:
        return self.dataset_stream("INDO", from_date, to_date)

    def actual_generation_per_type(self, from_date: str, to_date: str) -> dict:
        return self.dataset_stream("AGPT", from_date, to_date)

    def physical_notifications(self, from_date: str, to_date: str) -> dict:
        return self.dataset_stream("PN", from_date, to_date)

    def maximum_export_limits(self, from_date: str, to_date: str) -> dict:
        return self.dataset_stream("MELS", from_date, to_date)

    def bid_offer_data(self, from_date: str, to_date: str) -> dict:
        return self.dataset_stream("BOD", from_date, to_date)

    def accepted_actions(self, from_date: str, to_date: str) -> dict:
        return self.dataset_stream("BOALF", from_date, to_date)

    def remit(self, from_date: str, to_date: str) -> dict:
        return self.dataset_stream("REMIT", from_date, to_date)


class NesoCkanClient(JsonClient):
    def __init__(self, timeout: int = 60):
        super().__init__("https://api.neso.energy/api/3/action", timeout)

    def package_show(self, dataset_id: str) -> dict:
        return self.get("package_show", {"id": dataset_id})

    def datastore_search(
        self,
        resource_id: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        return self.get(
            "datastore_search",
            {"resource_id": resource_id, "limit": limit, "offset": offset},
        )

    def all_records(self, resource_id: str, page_size: int = 5000) -> list[dict]:
        records: list[dict] = []
        offset = 0
        while True:
            payload = self.datastore_search(resource_id, page_size, offset)
            result = payload.get("result", {})
            page = result.get("records", [])
            if not page:
                break
            records.extend(page)
            offset += len(page)
            total = int(result.get("total", len(records)))
            if len(records) >= total:
                break
        return records


class OpenMeteoClient(JsonClient):
    def __init__(self, timeout: int = 60):
        super().__init__("https://api.open-meteo.com/v1", timeout)

    def forecast(
        self,
        latitude: float,
        longitude: float,
        hourly: list[str],
        days: int = 3,
    ) -> dict:
        return self.get(
            "forecast",
            {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": ",".join(hourly),
                "timezone": "Europe/London",
                "forecast_days": days,
            },
        )

    def previous_runs(
        self,
        latitude: float,
        longitude: float,
        hourly: list[str],
        start_date: str,
        end_date: str,
    ) -> dict:
        client = JsonClient("https://previous-runs-api.open-meteo.com/v1", self.timeout)
        return client.get(
            "forecast",
            {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": ",".join(hourly),
                "start_date": start_date,
                "end_date": end_date,
                "timezone": "UTC",
            },
        )

    def ensemble(
        self,
        latitude: float,
        longitude: float,
        hourly: list[str],
        days: int = 3,
    ) -> dict:
        client = JsonClient("https://ensemble-api.open-meteo.com/v1", self.timeout)
        return client.get(
            "ensemble",
            {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": ",".join(hourly),
                "forecast_days": days,
                "timezone": "UTC",
            },
        )


class EntsoeClient:
    """ENTSO-E XML API client. Disabled until ``ENTSOE_TOKEN`` is supplied."""

    def __init__(self, token: str | None = None, timeout: int = 60):
        self.base_url = "https://web-api.tp.entsoe.eu/api"
        self.timeout = timeout
        self.token = token or os.getenv("ENTSOE_TOKEN")

    def query(self, params: dict) -> str:
        if not self.token:
            raise RuntimeError("ENTSOE_TOKEN is required")
        full_params = {"securityToken": self.token, **params}
        response = requests.get(
            self.base_url,
            params=full_params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.text


class JaoClient(JsonClient):
    def __init__(self, timeout: int = 60):
        super().__init__("https://publicationtool.jao.eu", timeout)

    def publication(self, path: str, params: dict | None = None) -> dict:
        """Fetch one configured JAO publication endpoint.

        JAO products use different schemas; callers must not assume one generic
        border-capacity table.
        """
        return self.get(path, params)
