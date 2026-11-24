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


def test_route_label_logged_and_validated(app, tmp_path, monkeypatch):
    path = tmp_path / "route_labels.csv"
    monkeypatch.setattr(rfl, "ROUTE_LABEL_LOG_PATH", str(path))
    c = app.test_client()
    base = {"slat": 51.05, "slon": 13.74, "dlat": 52.52, "dlon": 13.4, "aspect": "label"}
    assert c.post("/log-route-feedback", json={**base, "source": "trip", "answer": "partly", "reason": "elsewhere"}).status_code == 204
    c.post("/log-route-feedback", json={**base, "source": "result", "answer": "down", "reason": "walking"})
    # Outside the fixed sets: dropped.
    c.post("/log-route-feedback", json={**base, "source": "trip", "answer": "meh", "reason": ""})
    c.post("/log-route-feedback", json={**base, "source": "result", "answer": "down", "reason": "<script>"})
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [(r["source"], r["answer"], r["reason"]) for r in rows] == [("trip", "partly", "elsewhere"), ("result", "down", "walking")]


def test_route_label_does_not_touch_vote_file(app, tmp_path, monkeypatch):
    vote_path = tmp_path / "route_feedback.csv"
    label_path = tmp_path / "route_labels.csv"
    monkeypatch.setattr(rfl, "ROUTE_FEEDBACK_LOG_PATH", str(vote_path))
    monkeypatch.setattr(rfl, "ROUTE_LABEL_LOG_PATH", str(label_path))
    c = app.test_client()
    c.post("/log-route-feedback", json={"slat": 1, "slon": 2, "dlat": 3, "dlon": 4, "aspect": "label", "source": "trip", "answer": "up"})
    assert label_path.exists() and not vote_path.exists()


def test_summarise_route_labels_counts_only():
    from hitch.blueprints.utils.route_demand import summarise_route_labels

    rows = [
        {"source": "trip", "answer": "down", "reason": "", "auto": "0"},
        {"source": "trip", "answer": "down", "reason": "first_spot", "auto": "0"},
        {"source": "trip", "answer": "down", "reason": "text", "text": "secret", "auto": "0"},
        {"source": "result", "answer": "down", "reason": "walking", "auto": "1"},
    ]
    out = summarise_route_labels(rows)
    assert out == {"answers": {"trip": {"down": 1}}, "reasons": {"trip": {"first_spot": 1}}, "with_text": 1, "excluded_auto": 1}
    assert "secret" not in str(out)
