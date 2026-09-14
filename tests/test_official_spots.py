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


def test_registry_survives_missing_generated_files_and_recovers(client, registry):
    path = registry / "rides" / "by-spot" / "50.20003_7.20003.json"
    original = path.read_text()
    path.unlink()
    response = client.get("/official-stops.json")
    assert response.status_code == 200
    assert len(response.json) >= 2
    path.write_text(original)
    assert client.get("/official-stop/910002").location == "/spot/50.20003_7.20003"
