import json

from hitch.blueprints.utils.driver_reason_statistics import summarise_rows


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
    }
    (tmp_path / "driver_reason_statistics.json").write_text(json.dumps(payload))
    monkeypatch.setattr("hitch.blueprints.main.get_dirs", lambda: {"dist": str(tmp_path)})
    assert b"Why drivers stopped" in client.get("/statistics").data
    response = client.get("/statistics/driver-reasons")
    assert response.status_code == 200
    assert b"50%" in response.data
