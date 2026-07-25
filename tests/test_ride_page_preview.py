"""Title and link preview for /ride/<d_tag>, now that the share card links there."""

import json
import os

import pytest

from hitch.blueprints import main as main_bp
from hitch.extensions import db as _db
from hitch.models import SpotName

SPOT_ID = "51.08170_13.73629"


@pytest.fixture
def dist(app, tmp_path, monkeypatch):
    monkeypatch.setattr(main_bp, "get_dirs", lambda: {"dist": str(tmp_path)})
    with app.app_context():
        _db.session.query(SpotName).delete()
        _db.session.commit()
    yield tmp_path
    with app.app_context():
        _db.session.query(SpotName).delete()
        _db.session.commit()


def _write_spot_file(dist, name):
    by_spot = dist / "rides" / "by-spot"
    os.makedirs(by_spot, exist_ok=True)
    (by_spot / f"{SPOT_ID}.json").write_text(json.dumps({"spot": {"name": name}, "rides": [{"rating": 4}]}))


def _ride_view(**over):
    view = {"rating": 4, "wait": 12, "distance_km": 166.0, "comment": "Lovely driver, coffee included."}
    view.update(over)
    return view


class TestRidePreview:
    def test_names_the_place_the_ride_started(self, app, dist):
        _write_spot_file(dist, "Dresden Hauptbahnhof")
        with app.app_context():
            title, description = main_bp._ride_preview_meta(_ride_view(), SPOT_ID)
        assert "Dresden Hauptbahnhof" in title
        assert "166 km" in title

    def test_falls_back_to_the_cached_spot_name(self, app, dist):
        # A brand-new spot has no per-spot file yet — that is exactly the ride whose
        # link someone shares seconds after logging it.
        with app.app_context():
            # latitude/longitude/geocoded_at are NOT NULL columns on SpotName (see
            # hitch/models.py); the writer (spot_names.py) always supplies them.
            _db.session.add(
                SpotName(spot_id=SPOT_ID, name="Bergstraße", latitude=51.08170, longitude=13.73629, geocoded_at="2026-01-01")
            )
            _db.session.commit()
            title, _ = main_bp._ride_preview_meta(_ride_view(), SPOT_ID)
        assert "Bergstraße" in title

    def test_an_unnamed_spot_still_gets_a_usable_title(self, app, dist):
        with app.app_context():
            title, _ = main_bp._ride_preview_meta(_ride_view(), SPOT_ID)
        assert title
        assert "None" not in title

    def test_the_description_carries_the_facts_that_exist(self, app, dist):
        with app.app_context():
            _, description = main_bp._ride_preview_meta(_ride_view(), SPOT_ID)
        assert "4/5" in description
        assert "12 min" in description
        assert "Lovely driver" in description

    def test_a_bare_ride_still_says_something(self, app, dist):
        with app.app_context():
            _, description = main_bp._ride_preview_meta(
                _ride_view(rating=None, wait=None, distance_km=None, comment=None), SPOT_ID
            )
        assert description

    def test_a_long_comment_is_trimmed(self, app, dist):
        with app.app_context():
            _, description = main_bp._ride_preview_meta(_ride_view(comment="x" * 500), SPOT_ID)
        assert len(description) < 320

    def test_a_ride_with_no_pickup_has_no_spot_to_name(self, app, dist):
        with app.app_context():
            title, description = main_bp._ride_preview_meta(_ride_view(), None)
        assert title
        assert description


class TestRidePageRendersThem:
    def test_the_page_carries_the_tags(self, app, client, dist, monkeypatch):
        # Guards the template wiring: the route can compute a perfect title and still
        # render base.html's generic one if the blocks are not overridden.
        import tests.test_instant_ride_row as fixtures

        with app.app_context():
            main_bp._store_published_ride(fixtures._StubEvent(fixtures._raw_event()))
        html = client.get("/ride/maps.hitchwiki.org-abc").get_data(as_text=True)
        assert 'property="og:title"' in html
        assert "Hitchhiking ride" in html
        with app.app_context():
            from hitch.models import RideEvent

            _db.session.query(RideEvent).delete()
            _db.session.commit()
