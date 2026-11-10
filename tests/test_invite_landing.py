import csv

import hitch.blueprints.utils.invite_landing_log as ill


def _rows(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_invite_code_anonymous(app):
    r = app.test_client().get("/api/invite-code")
    assert r.status_code == 200 and r.get_json() == {"code": None, "landings": 0}


def test_landing_logged_and_counted(app, tmp_path, monkeypatch):
    path = tmp_path / "invite_landings.csv"
    monkeypatch.setattr(ill, "INVITE_LANDINGS_LOG_PATH", str(path))
    c = app.test_client()
    assert c.post("/log-invite-landing", json={"code": "abcdef12", "ref": "invite_success"}).status_code == 204
    assert c.post("/log-invite-landing", json={"code": "abcdef12"}).status_code == 204
    assert ill.count_invite_landings("abcdef12") == 2
    assert len(_rows(path)) == 2


def test_landing_rejects_bad_code(app, tmp_path, monkeypatch):
    path = tmp_path / "invite_landings.csv"
    monkeypatch.setattr(ill, "INVITE_LANDINGS_LOG_PATH", str(path))
    c = app.test_client()
    assert c.post("/log-invite-landing", json={"code": "nothex!!"}).status_code == 204
    assert c.post("/log-invite-landing", data="garbage").status_code == 204
    assert not path.exists()
