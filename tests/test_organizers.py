import csv
import io
import json
from datetime import datetime, timezone

import pytest

from hitch.blueprints import organizers
from hitch.models import OsmHitchhikingSpot


def stamp(day):
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() * 1000


@pytest.fixture
def evidence(tmp_path, monkeypatch, db):
    monkeypatch.setattr(organizers, "get_dirs", lambda: {"dist": str(tmp_path)})
    organizers.load_evidence.cache_clear()
    for ident, lon in [(900001, 7.1), (900002, 7.2), (900003, 8.5)]:
        db.session.add(OsmHitchhikingSpot(id=ident, latitude=50.1, longitude=lon, tags={"name": "Testbank"}))
    db.session.commit()
    spots = [{"lat": 50.1, "lon": 7.1, "osm": True}, {"lat": 50.1, "lon": 8.5, "osm": True}]
    (tmp_path / "spots.json").write_text(json.dumps(spots))
    details = tmp_path / "rides" / "by-spot"
    details.mkdir(parents=True)
    for sid, ident in [("50.10000_7.10000", 900001), ("50.10000_8.50000", 900003)]:
        (details / f"{sid}.json").write_text(json.dumps({"spot": {"osm_id": ident}, "rides": [{"id": "g", "no_ride": True}]}))
    rides = [
        {"id": "a", "sid": "50.10000_7.10000", "w": 0, "rd": stamp("2026-06-01")},
        {"id": "b", "sid": "50.10000_7.10000", "w": 20, "rd": stamp("2026-06-30")},
        {"id": "c", "sid": "50.10000_7.10000", "w": 99, "rd": None, "t": stamp("2026-06-15")},
        {"id": "d", "sid": "50.10000_7.10000", "w": 40, "rd": stamp("2026-05-31")},
        {"id": "e", "sid": "50.10000_8.50000", "w": 999, "rd": stamp("2026-06-15")},
        {"id": "f", "sid": "50.11000_7.11000", "w": 100, "rd": stamp("2026-06-15")},
        {"id": "g", "sid": "50.10000_7.10000", "w": 500, "rd": stamp("2026-06-15")},
    ]
    rides.append(rides[0])  # A repeated record must not inflate the policy report.
    (tmp_path / "rides_index.json").write_text(json.dumps(rides))
    yield tmp_path
    for ident in (900001, 900002, 900003):
        db.session.query(OsmHitchhikingSpot).filter_by(id=ident).delete()
    db.session.commit()


URL = "/mitfahrbaenke/bericht?bbox=7,50,7.5,50.5"


def test_report_scopes_official_nodes_and_keeps_empty_stops(client, evidence):
    response = client.get(URL + "&format=csv")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.data.decode("utf-8-sig"))))
    assert [r["osm_node"] for r in rows] == ["900001", "900002"]
    assert [r["documented_rides"] for r in rows] == ["4", "0"]
    assert rows[0]["median_wait_minutes"] == "30.0"
    assert rows[1]["median_wait_minutes"] == ""


def test_comparison_uses_ride_dates_and_equal_previous_period(client, evidence):
    response = client.get(URL + "&von=2026-06-01&bis=2026-06-30&format=csv")
    row = next(csv.DictReader(io.StringIO(response.data.decode("utf-8-sig"))))
    assert row["documented_rides"] == "2"
    assert row["documented_unsuccessful_attempts"] == "1"
    assert row["median_wait_minutes"] == "10.0"
    assert row["previous_period_rides"] == "1"
    assert row["latest_ride_date"] == "2026-06-30"
    html = client.get(URL + "&von=2026-06-01&bis=2026-06-30").data.decode()
    assert "2026-05-02 bis 2026-05-31" in html
    assert "aus beiden Zeiträumen ausgeschlossen" in html


def test_landing_and_shareable_report_render(client, evidence):
    landing = client.get("/mitfahrbaenke")
    assert landing.status_code == 200
    assert b'<html lang="de"' in landing.data
    assert b'name="robots" content="noindex"' not in landing.data
    assert b"hreflang=" not in landing.data
    response = client.get(URL)
    assert response.status_code == 200
    assert b'name="robots" content="noindex"' in response.data
    assert b"hreflang=" not in response.data
    assert b'id="website-link"' in response.data
    assert b"50.10000_7.10000" in response.data


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?bbox=nan,50,7,51",
        "?bbox=7,51,7,52",
        "?bbox=0,0,100,80",
        "?bbox=7,50,8,51&von=2026-06-01",
        "?bbox=7,50,8,51&von=2026-06-01&bis=2025-06-01",
    ],
)
def test_invalid_area_and_dates(client, query):
    assert client.get("/mitfahrbaenke/bericht" + query).status_code == 400


def test_unavailable_data_does_not_look_like_zero_usage(client, evidence):
    (evidence / "rides_index.json").unlink()
    assert client.get(URL).status_code == 503


def test_report_escapes_osm_names(client, evidence, db):
    row = db.session.get(OsmHitchhikingSpot, 900001)
    row.tags = {"name": '<script>alert("x")</script>'}
    db.session.commit()
    html = client.get(URL).data.decode()
    assert '<script>alert("x")</script>' not in html
    assert "&lt;script&gt;" in html
