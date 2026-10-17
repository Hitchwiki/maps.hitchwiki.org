import json

from hitch.blueprints.utils.driver_reason_statistics import summarise_rows, summarise_season_waits


def _occ(*reasons, driver=True):
    return json.dumps([{"was_driver": driver, "reasons_to_pick_up": list(reasons)}])


def test_counts_each_reason_once_per_answering_ride_and_skips_unanswered():
    rows = [
        (_occ("curiosity", "was_hitchhiker"), 0),
        (_occ("curiosity"), 0),
        (_occ(), 0),
        (_occ("sympathy", driver=False), 0),
        (_occ("environmental"), 1),
        (None, 0),
    ]
    result = summarise_rows(rows)
    assert result["reasons"][0] == {"reason": "curiosity", "rides": 2}
    assert {"reason": "was_hitchhiker", "rides": 1} in result["reasons"]
    assert all(r["reason"] not in ("sympathy", "environmental") for r in result["reasons"])
    assert result["coverage"] == {"rides_total": 6, "rides_answered": 2}


def test_driver_reasons_route(client, monkeypatch, tmp_path):
    payload = {
        "generated_at": "2026-10-17T07:00:00Z",
        "coverage": {"rides_total": 10, "rides_answered": 4},
        "reasons": [{"reason": "curiosity", "rides": 2}],
        "season_waits": [{"region": "Europe", "seasons": [{"season": "winter", "rides": 301, "median": 20.0}]}],
    }
    (tmp_path / "driver_reason_statistics.json").write_text(json.dumps(payload))
    monkeypatch.setattr("hitch.blueprints.main.get_dirs", lambda: {"dist": str(tmp_path)})
    assert b"Why drivers stopped" in client.get("/statistics").data
    response = client.get("/statistics/driver-reasons")
    assert response.status_code == 200
    assert b"50%" in response.data
    assert b"20 min median" in response.data and b"301 rides" in response.data


def test_trip_purposes_counted_over_answering_rides_only():
    rows = [
        (_occ("curiosity"), 0, json.dumps({"reasons": ["commute", "errands"]})),
        (_occ("curiosity"), 0, {"reasons": ["commute"]}),
        (_occ(), 0, {"reasons": ["holiday"]}),
        (_occ("curiosity"), 0, "not json"),
    ]
    result = summarise_rows(rows)
    assert result["trip_purposes"] == [{"reason": "commute", "rides": 2}, {"reason": "errands", "rides": 1}]


def _stop(month, wait, lat=50.0, lon=8.0):
    return [{"departure_time": f"2025-{month:02d}-10T10:00:00", "waiting_duration": f"PT{wait}M",
             "location": {"latitude": lat, "longitude": lon}}]  # fmt: skip


def test_season_waits_need_enough_rides_in_winter_and_summer():
    rows = [_stop(1, 20)] * 300 + [_stop(7, 20)] * 300 + [_stop(7, 10, lat=-30, lon=150)] * 500
    result = summarise_season_waits(rows)
    assert [r["region"] for r in result] == ["Europe"]
    assert {s["season"]: s["median"] for s in result[0]["seasons"]} == {"winter": 20, "summer": 20}
    assert summarise_season_waits(rows[:299] + rows[300:]) == []
