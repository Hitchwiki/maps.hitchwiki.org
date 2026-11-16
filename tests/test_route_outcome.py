import csv

import hitch.blueprints.utils.route_outcome_log as rol


def test_route_outcome_logged(app, tmp_path, monkeypatch):
    path = tmp_path / "route_outcomes.csv"
    monkeypatch.setattr(rol, "ROUTE_OUTCOME_LOG_PATH", str(path))
    c = app.test_client()
    assert c.post("/log-route-outcome", json={"outcome": "found", "graph": "oneoff", "options": 3}).status_code == 204
    assert c.post("/log-route-outcome", json={"outcome": "none", "reason": "dest-uncovered", "auto": 1}).status_code == 204
    assert c.post("/log-route-outcome", json={"outcome": "bogus"}).status_code == 204
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["outcome"] for r in rows] == ["found", "none"]
    assert rows[0]["options"] == "3" and rows[1]["auto"] == "1"
