import csv

import hitch.blueprints.utils.route_feedback_log as rfl


def test_route_feedback_logged(app, tmp_path, monkeypatch):
    path = tmp_path / "route_feedback.csv"
    monkeypatch.setattr(rfl, "ROUTE_FEEDBACK_LOG_PATH", str(path))
    c = app.test_client()
    body = {"slat": 51.05, "slon": 13.74, "dlat": 52.52, "dlon": 13.4, "vote": "down", "text": "too\nmuch  walking"}
    assert c.post("/log-route-feedback", json=body).status_code == 204
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert len(rows) == 1 and rows[0]["vote"] == "down" and rows[0]["text"] == "too much walking"


def test_route_feedback_rejects_bad_vote(app, tmp_path, monkeypatch):
    path = tmp_path / "route_feedback.csv"
    monkeypatch.setattr(rfl, "ROUTE_FEEDBACK_LOG_PATH", str(path))
    c = app.test_client()
    c.post("/log-route-feedback", json={"slat": 1, "slon": 2, "dlat": 3, "dlon": 4, "vote": "x"})
    assert not path.exists()
