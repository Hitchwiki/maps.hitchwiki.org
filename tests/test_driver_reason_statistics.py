import json

from hitch.blueprints.utils.driver_reason_statistics import summarise_rows


def _occ(*reasons, driver=True):
    return json.dumps([{"was_driver": driver, "reasons_to_pick_up": list(reasons)}])


def test_counts_driver_reasons_once_per_ride():
    rows = [
        ("a", _occ("curiosity", "sympathy")),
        ("b", _occ("curiosity")),
        ("c", _occ("curiosity", driver=False)),  # not the driver
        ("d", _occ("not_a_real_code")),
        ("e", "not json"),
    ]
    out = summarise_rows(rows)
    assert {r["code"]: r["rides"] for r in out["reasons"]} == {"curiosity": 2, "sympathy": 1}
    assert out["coverage"] == {"rides_read": 5, "rides_with_answer": 2}


def test_hidden_rides_are_skipped():
    out = summarise_rows([("a", _occ("curiosity")), ("b", _occ("curiosity"))], hidden={"a"})
    assert out["reasons"] == [{"code": "curiosity", "rides": 1}]
    assert out["coverage"]["rides_read"] == 1
