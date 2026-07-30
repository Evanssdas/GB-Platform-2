from gb_platform_v2.data.elexon import ElexonClient


def test_national_demand_uses_demand_outturn_stream(monkeypatch):
    client = ElexonClient()
    captured = {}

    def fake_get(path, params=None):
        captured["path"] = path
        captured["params"] = params
        return []

    monkeypatch.setattr(client, "_get", fake_get)

    result = client.national_demand("2024-01-01", "2024-01-07")

    assert result == []
    assert captured["path"] == "demand/outturn/stream"
    assert captured["params"] == {
        "settlementDateFrom": "2024-01-01",
        "settlementDateTo": "2024-01-07",
    }


def test_raw_indo_publications_remain_separate(monkeypatch):
    client = ElexonClient()
    captured = {}

    def fake_get(path, params=None):
        captured["path"] = path
        captured["params"] = params
        return {"data": []}

    monkeypatch.setattr(client, "_get", fake_get)

    result = client.national_demand_publications(
        "2024-01-01T00:00:00Z",
        "2024-01-02T00:00:00Z",
    )

    assert result == {"data": []}
    assert captured["path"] == "datasets/INDO"
    assert captured["params"] == {
        "publishDateTimeFrom": "2024-01-01T00:00:00Z",
        "publishDateTimeTo": "2024-01-02T00:00:00Z",
        "format": "json",
    }
