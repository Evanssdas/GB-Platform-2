from gb_platform_v2.data.elexon import ElexonClient


def test_national_demand_uses_standard_indo_endpoint(monkeypatch):
    client = ElexonClient()
    captured = {}

    def fake_get(path, params=None):
        captured["path"] = path
        captured["params"] = params
        return {"data": []}

    monkeypatch.setattr(client, "_get", fake_get)

    result = client.national_demand(
        "2024-01-01T00:00:00Z",
        "2024-01-02T00:00:00Z",
    )

    assert result == {"data": []}
    assert captured["path"] == "datasets/INDO"
    assert captured["params"] == {
        "publishDateTimeFrom": "2024-01-01T00:00:00Z",
        "publishDateTimeTo": "2024-01-02T00:00:00Z",
    }
