"""Explicit clients for public GB and European data services.

Clients return raw payloads. Parsers must validate timestamps, units, revisions,
sign conventions and product definitions before modelling.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class JsonClient:
    base_url: str
    timeout: int = 60
    retries: int = 3

    def __post_init__(self) -> None:
        retry = Retry(
            total=self.retries,
            connect=self.retries,
            read=self.retries,
            status=self.retries,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(
            {"User-Agent": "GB-Power-Market-Platform-V2/0.1", "Accept": "application/json"}
        )

    def get(self, path: str, params: dict | None = None) -> dict:
        response = self.session.get(
            f"{self.base_url.rstrip('/')}/{path.lstrip('/')}",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("Expected a JSON object")
        if payload.get("success") is False:
            raise RuntimeError(f"Source API reported failure: {payload.get('error')}")
        return payload


class ElexonClient(JsonClient):
    """Legacy generic Elexon client; source-aware code uses data.elexon.ElexonClient."""

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

    def datastore_search_sql(self, sql: str) -> dict:
        return self.get("datastore_search_sql", {"sql": sql})

    def resource_fields(self, resource_id: str) -> list[str]:
        payload = self.datastore_search(resource_id, limit=1, offset=0)
        fields = payload.get("result", {}).get("fields", [])
        names = [str(field.get("id")) for field in fields if field.get("id")]
        if not names:
            raise RuntimeError(f"NESO resource {resource_id} returned no field metadata")
        return names

    @staticmethod
    def _normalise_field(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")

    def resolve_field(self, resource_id: str, aliases: list[str]) -> str:
        fields = self.resource_fields(resource_id)
        normalised = {self._normalise_field(field): field for field in fields}
        for alias in aliases:
            candidate = normalised.get(self._normalise_field(alias))
            if candidate:
                return candidate
        raise KeyError(
            f"NESO resource {resource_id} has no matching field for {aliases}; fields={fields}"
        )

    @staticmethod
    def _quote_identifier(value: str) -> str:
        return '"' + str(value).replace('"', '""') + '"'

    @staticmethod
    def _quote_literal(value: str) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    def records_for_date_window(
        self,
        resource_id: str,
        start: str,
        end_exclusive: str,
        date_aliases: list[str] | None = None,
        page_size: int = 5000,
        max_pages: int = 100,
    ) -> list[dict]:
        """Fetch only records inside ``[start, end)`` using CKAN SQL.

        Annual embedded and inertia resources can contain many revisions. A
        bounded SQL query avoids downloading the entire annual archive for a
        one-month validation run.
        """
        aliases = date_aliases or ["settlement_date", "settlement date", "date"]
        date_field = self.resolve_field(resource_id, aliases)
        resource = self._quote_identifier(resource_id)
        field = self._quote_identifier(date_field)
        start_literal = self._quote_literal(start)
        end_literal = self._quote_literal(end_exclusive)

        records: list[dict] = []
        for page_number in range(max_pages):
            offset = page_number * page_size
            sql = (
                f"SELECT * FROM {resource} "
                f"WHERE {field} >= {start_literal} AND {field} < {end_literal} "
                f"ORDER BY {field} ASC LIMIT {int(page_size)} OFFSET {int(offset)}"
            )
            payload = self.datastore_search_sql(sql)
            page = payload.get("result", {}).get("records", [])
            if not isinstance(page, list):
                raise TypeError("NESO SQL result.records is not a list")
            records.extend(page)
            if len(page) < page_size:
                return records
        raise RuntimeError(
            f"NESO date-window query exceeded {max_pages} pages for {resource_id}; "
            "reduce the requested window or increase the explicit bound"
        )

    def all_records(
        self,
        resource_id: str,
        page_size: int = 5000,
        max_pages: int = 500,
    ) -> list[dict]:
        records: list[dict] = []
        offset = 0
        for _ in range(max_pages):
            payload = self.datastore_search(resource_id, page_size, offset)
            result = payload.get("result", {})
            page = result.get("records", [])
            if not page:
                return records
            records.extend(page)
            offset += len(page)
            total = int(result.get("total", len(records)))
            if len(records) >= total:
                return records
        raise RuntimeError(
            f"NESO resource {resource_id} exceeded the explicit {max_pages}-page bound"
        )


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
    """ENTSO-E XML API client using ``ENTSOE_TOKEN``."""

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
        """Fetch one configured JAO publication endpoint."""
        return self.get(path, params)
