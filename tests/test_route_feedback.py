import csv

import hitch.blueprints.utils.route_feedback_log as rfl


def test_route_feedback_logged(app, tmp_path, monkeypatch):
    path = tmp_path / "route_feedback.csv"
    monkeypatch.setattr(rfl, "ROUTE_FEEDBACK_LOG_PATH", str(path))
    c = app.test_client()
    body = {"slat": 51.05, "slon": 13.74, "dlat": 52.52, "dlon": 13.4, "vote": "down", "text": "too\nmuch  walking"}
    assert c.post("/log-route-feedback", json=body).status_code == 204
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1 and rows[0]["vote"] == "down" and rows[0]["text"] == "too much walking"


def test_route_feedback_rejects_bad_vote(app, tmp_path, monkeypatch):
    path = tmp_path / "route_feedback.csv"
    monkeypatch.setattr(rfl, "ROUTE_FEEDBACK_LOG_PATH", str(path))
    c = app.test_client()
    c.post("/log-route-feedback", json={"slat": 1, "slon": 2, "dlat": 3, "dlon": 4, "vote": "x"})
    assert not path.exists()


def test_presentation_feedback_goes_to_its_own_file(app, tmp_path, monkeypatch):
    route_path = tmp_path / "route_feedback.csv"
    ui_path = tmp_path / "route_presentation_feedback.csv"
    monkeypatch.setattr(rfl, "ROUTE_FEEDBACK_LOG_PATH", str(route_path))
    monkeypatch.setattr(rfl, "ROUTE_PRESENTATION_FEEDBACK_LOG_PATH", str(ui_path))
    c = app.test_client()
    body = {"slat": 51.05, "slon": 13.74, "dlat": 52.52, "dlon": 13.4, "vote": "up", "aspect": "presentation"}
    assert c.post("/log-route-feedback", json=body).status_code == 204
    assert not route_path.exists()
    with open(ui_path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1 and rows[0]["vote"] == "up"


def test_unknown_aspect_counts_as_route(app, tmp_path, monkeypatch):
    route_path = tmp_path / "route_feedback.csv"
    ui_path = tmp_path / "route_presentation_feedback.csv"
    monkeypatch.setattr(rfl, "ROUTE_FEEDBACK_LOG_PATH", str(route_path))
    monkeypatch.setattr(rfl, "ROUTE_PRESENTATION_FEEDBACK_LOG_PATH", str(ui_path))
    c = app.test_client()
    c.post("/log-route-feedback", json={"slat": 1, "slon": 2, "dlat": 3, "dlon": 4, "vote": "down", "aspect": "x"})
    assert route_path.exists() and not ui_path.exists()
