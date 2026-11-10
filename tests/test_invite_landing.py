import csv

import hitch.blueprints.utils.invite_landing_log as ill


def _rows(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_invite_code_anonymous(app):
    r = app.test_client().get("/api/invite-code")
    assert r.status_code == 200 and r.get_json() == {"code": None, "landings": 0, "joins": 0}


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


def test_landing_remembers_code_in_session_and_join_counts(app, tmp_path, monkeypatch):
    monkeypatch.setattr(ill, "INVITE_LANDINGS_LOG_PATH", str(tmp_path / "l.csv"))
    monkeypatch.setattr(ill, "INVITE_JOINS_LOG_PATH", str(tmp_path / "j.csv"))
    c = app.test_client()
    assert c.post("/log-invite-landing", json={"code": "abcdef12"}).status_code == 204
    with c.session_transaction() as s:
        assert s["inv"] == "abcdef12"
    c2 = app.test_client()
    c2.post("/log-invite-landing", json={"code": "zz"})
    with c2.session_transaction() as s:
        assert "inv" not in s
    ill.log_invite_join("abcdef12")
    ill.log_invite_join("bad!")
    assert ill.count_invite_joins("abcdef12") == 1
    assert ill.count_invite_joins("12345678") == 0
    assert len(_rows(tmp_path / "j.csv")) == 1
