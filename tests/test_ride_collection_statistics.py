import json

from hitch.blueprints.utils.ride_collection_statistics import summarise_collection


def test_collection_series_are_weekly_gap_free_and_split_by_source():
    rows = [
        ("2026-08-03T12:00:00Z", "hitchmap.com", "{}"),
        ("2026-08-09T18:00:00+00:00", "ignored.example", json.dumps({"source": "hitchwiki.org"})),
        ("2026-08-17T09:00:00Z", None, None),
        ("not-a-date", "hitchmap.com", None),
    ]

    result = summarise_collection(rows, generated_at="now")

    assert result["series"]["All sources"] == [
        ["2026-08-03", 2],
        ["2026-08-10", 0],
        ["2026-08-17", 1],
    ]
    assert result["series"]["hitchmap.com"] == [
        ["2026-08-03", 1],
        ["2026-08-10", 0],
        ["2026-08-17", 0],
    ]
    assert result["series"]["hitchwiki.org"][0] == ["2026-08-03", 1]
    assert result["coverage"] == {"rides_used": 3, "invalid_timestamps": 1}


def test_statistics_routes(client, monkeypatch, tmp_path):
    payload = {
        "generated_at": "2026-08-24T07:25:00Z",
        "coverage": {"rides_used": 2},
        "series": {"All sources": [["2026-08-17", 2]], "hitchmap.com": [["2026-08-17", 2]]},
    }
    (tmp_path / "ride_collection_statistics.json").write_text(json.dumps(payload))
    monkeypatch.setattr("hitch.blueprints.main.get_dirs", lambda: {"dist": str(tmp_path)})

    assert b"Ride collection" in client.get("/statistics").data
    response = client.get("/statistics/ride-collection")
    assert response.status_code == 200
    assert b"hitchmap.com" in response.data
    assert client.get("/pl/statistics/ride-collection").status_code == 200
    assert client.get("/dashboard.html").status_code == 301
