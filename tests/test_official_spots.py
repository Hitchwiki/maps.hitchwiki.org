import json

import pytest

from hitch.blueprints import official_spots
from hitch.models import OsmHitchhikingSpot


@pytest.fixture
def registry(db, tmp_path, monkeypatch):
    monkeypatch.setattr(official_spots, "get_dirs", lambda: {"dist": str(tmp_path)})
    official_spots._reviewed_links.cache_clear()
    db.session.add_all(
        [
            OsmHitchhikingSpot(id=910001, latitude=50.1, longitude=7.1, tags={"name": "Unreviewed bench"}),
            OsmHitchhikingSpot(id=910002, latitude=50.2, longitude=7.2, tags={"name": "Reviewed bench"}),
        ]
    )
    db.session.commit()
    (tmp_path / "spots.json").write_text(json.dumps([{"lat": 50.20003, "lon": 7.20003, "osm": True}]))
    details = tmp_path / "rides" / "by-spot"
    details.mkdir(parents=True)
    (details / "50.20003_7.20003.json").write_text(json.dumps({"spot": {"osm_id": 910002}}))
    yield tmp_path
    db.session.query(OsmHitchhikingSpot).filter(OsmHitchhikingSpot.id.in_([910001, 910002])).delete()
    db.session.commit()


def test_registry_includes_unreviewed_stops_without_inventing_ratings(client, registry):
    rows = {r["osm_id"]: r for r in client.get("/official-stops.json").json}
    empty = rows[910001]
    assert empty["name"] == "Unreviewed bench"
    assert empty["rating"] is None
    assert empty["review_count"] == 0
    assert empty["osm"] is True
    assert empty["map_spot_id"] == "50.10000_7.10000"
    assert rows[910002]["map_spot_id"] == "50.20003_7.20003"


def test_stable_links_open_the_existing_marker_or_the_unreviewed_stop(client, registry):
    assert client.get("/official-stop/910001").location == "/spot/50.10000_7.10000"
    assert client.get("/official-stop/910002").location == "/spot/50.20003_7.20003"
    assert client.get("/official-stop/999999999999").status_code == 404
    assert client.get("/official-stop/910001?ref=bench_koris&x=1").location == "/spot/50.10000_7.10000?ref=bench_koris"


def test_registry_survives_missing_generated_files_and_recovers(client, registry):
    path = registry / "rides" / "by-spot" / "50.20003_7.20003.json"
    original = path.read_text()
    path.unlink()
    response = client.get("/official-stops.json")
    assert response.status_code == 200
    assert len(response.json) >= 2
    path.write_text(original)
    assert client.get("/official-stop/910002").location == "/spot/50.20003_7.20003"


def test_bench_town_page_renders_and_unknown_slug_404s(client):
    r = client.get("/mitfahrbank/moringen-de")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Mitfahrbänke in Moringen" in body
    assert "/official-stop/" in body and "ref=bench-town" in body
    assert "Arrêt" in client.get("/mitfahrbank/la-hague-fr").get_data(as_text=True)
    assert client.get("/mitfahrbank/nowhere-xx").status_code == 404


def test_bench_town_language_follows_country(client):
    be = client.get("/mitfahrbank/eupen-be").get_data(as_text=True)
    assert "Mitfahrbänke in Eupen" in be and "Rezo Pouce" not in be
    assert '<html lang="de"' in be
    fr = client.get("/mitfahrbank/la-hague-fr").get_data(as_text=True)
    assert "Rezo Pouce" in fr and '<html lang="fr"' in fr


def test_bench_town_lists_street_when_known(client, monkeypatch):
    from hitch.blueprints import official_spots as os_

    osm_id = os_.bench_towns()["eupen-be"]["stops"][0][0]
    monkeypatch.setattr(os_, "bench_streets", lambda: {str(osm_id): "Testgasse"})
    html = client.get("/mitfahrbank/eupen-be").get_data(as_text=True)
    assert "Mitfahrhalt 1 — Testgasse" in html


def test_bench_town_ride_count_only_when_rides_exist(client, monkeypatch):
    from hitch.blueprints import official_spots as os_

    monkeypatch.setattr(os_, "bench_rides", lambda: {"eupen-be": {"rides": 3, "stops": 1}})
    html = client.get("/mitfahrbank/eupen-be").get_data(as_text=True)
    assert "3 Fahrten im Umkreis von 100 m" in html
    assert "bench-ride-count" not in client.get("/mitfahrbank/moringen-de").get_data(as_text=True)


def test_bench_town_index_lists_towns_and_town_pages_link_back(client):
    body = client.get("/mitfahrbank/").get_data(as_text=True)
    assert "/mitfahrbank/moringen-de" in body
    assert 'href="/mitfahrbank/"' in client.get("/mitfahrbank/moringen-de").get_data(as_text=True)


def test_bench_town_nl_dk_us_not_german(client):
    nl = client.get("/mitfahrbank/utrecht-nl").get_data(as_text=True)
    assert '<html lang="nl"' in nl and "Liftplekken in" in nl and "Mitfahrh" not in nl
    dk = client.get("/mitfahrbank/aarhus-dk").get_data(as_text=True)
    assert '<html lang="da"' in dk and "Blafferpladser i" in dk
    us = client.get("/mitfahrbank/berkeley-us").get_data(as_text=True)
    assert '<html lang="en"' in us and "Hitchhiking spots in" in us and "Mitfahrh" not in us


def test_bench_town_shows_would_ride_again_line_in_page_language(client):
    de = client.get("/mitfahrbank/moringen-de").get_data(as_text=True)
    assert 'id="bench-proof"' in de and "mehr als 9 von 10" in de and "616" in de
    fr = client.get("/mitfahrbank/la-hague-fr").get_data(as_text=True)
    assert "plus de 9 sur 10" in fr
