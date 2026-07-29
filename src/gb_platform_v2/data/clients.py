"""Thin, explicit clients for public GB and European data services.

These clients deliberately return raw payloads. Source-specific parsers should
validate timestamps, units, revisions and product definitions before training.
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
    def __init__(self, timeout: int = 60):
        super().__init__("https://data.elexon.co.uk/bmrs/api/v1", timeout)

    def market_index(self, from_date: str, to_date: str) -> dict:
        return self.get(
            "balancing/pricing/market-index",
            {"from": from_date, "to": to_date, "dataProviders": "APXMIDP"},
        )

    def fuel_half_hourly(self, from_date: str, to_date: str) -> dict:
        return self.get("generation/outturn/summary", {"startTime": from_date, "endTime": to_date})


class NesoCkanClient(JsonClient):
    def __init__(self, timeout: int = 60):
        super().__init__("https://api.neso.energy/api/3/action", timeout)

    def package_show(self, dataset_id: str) -> dict:
        return self.get("package_show", {"id": dataset_id})

    def datastore_search(self, resource_id: str, limit: int = 1000, offset: int = 0) -> dict:
        return self.get(
            "datastore_search",
            {"resource_id": resource_id, "limit": limit, "offset": offset},
        )


class OpenMeteoClient(JsonClient):
    def __init__(self, timeout: int = 60):
        super().__init__("https://api.open-meteo.com/v1", timeout)

    def forecast(self, latitude: float, longitude: float, hourly: list[str], days: int = 3) -> dict:
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


class EntsoeClient(JsonClient):
    def __init__(self, token: str | None = None, timeout: int = 60):
        super().__init__("https://web-api.tp.entsoe.eu", timeout)
        self.token = token or os.getenv("ENTSOE_TOKEN")

    def query(self, params: dict) -> str:
        if not self.token:
            raise RuntimeError("ENTSOE_TOKEN is required")
        full_params = {"securityToken": self.token, **params}
        response = requests.get(self.base_url, params=full_params, timeout=self.timeout)
        response.raise_for_status()
        return response.text


class JaoClient(JsonClient):
    def __init__(self, timeout: int = 60):
        super().__init__("https://publicationtool.jao.eu", timeout)

    def publication(self, path: str, params: dict | None = None) -> dict:
        """Fetch one explicitly configured JAO publication endpoint.

        JAO products use different schemas; callers must not assume one generic
        border-capacity table.
        """
        return self.get(path, params)
