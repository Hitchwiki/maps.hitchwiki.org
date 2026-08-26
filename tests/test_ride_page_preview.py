"""Title and link preview for /ride/<d_tag>, now that the share card links there."""

import json
import os
from datetime import datetime, timezone

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
            # hitch/models.py); the writer (spot_names.py) always supplies them, using a
            # full ISO-8601 UTC timestamp for geocoded_at, which we mirror here.
            _db.session.add(
                SpotName(
                    spot_id=SPOT_ID,
                    name="Bergstraße",
                    latitude=51.08170,
                    longitude=13.73629,
                    geocoded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
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

    def test_an_instant_pickup_is_not_confused_with_no_wait_recorded(self, app, dist):
        # wait=0 is a genuine, good outcome (picked up instantly) and must read
        # differently from wait=None (no waiting time was ever logged) — a truthiness
        # check on `wait` would collapse the two.
        with app.app_context():
            _, zero_wait = main_bp._ride_preview_meta(_ride_view(wait=0), SPOT_ID)
            _, no_wait = main_bp._ride_preview_meta(_ride_view(wait=None), SPOT_ID)
        assert "Waited 0 min." in zero_wait
        assert "Waited" not in no_wait
        assert zero_wait != no_wait

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


class TestWikiContributePrompt:
    """The ride's own author, on a long enough comment, gets a link to fold their
    notes into the nearest Hitchwiki article — nobody else, and only when there is
    somewhere to send them (see the "never write new content ourselves" rule: this
    invites the author to write it, it does not draft anything)."""

    UNIQUIFIER = "wiki-contribute-test-uniquifier"
    USERNAME = "wiki-contribute-author"

    @pytest.fixture
    def author(self, app, client):
        from hitch.models import User

        with app.app_context():
            user = User(
                username=self.USERNAME,
                email="author@example.com",
                password="x",
                active=True,
                fs_uniquifier=self.UNIQUIFIER,
            )
            _db.session.add(user)
            _db.session.commit()
            user_id = user.id
        with client.session_transaction() as sess:
            sess["_user_id"] = self.UNIQUIFIER
            sess["_fresh"] = True
        yield user_id
        with app.app_context():
            _db.session.query(User).filter_by(id=user_id).delete()
            _db.session.commit()

    def _publish(self, app, comment):
        import tests.test_instant_ride_row as fixtures

        with app.app_context():
            main_bp._store_published_ride(fixtures._StubEvent(self._raw_event_as(fixtures, comment)))

    def _raw_event_as(self, fixtures, comment):
        from tests.conftest import TEST_PUBKEY

        raw = fixtures._raw_event(comment=comment)
        raw["pubkey"] = TEST_PUBKEY
        content = json.loads(raw["content"])
        content["hitchhikers"] = [{"nickname": self.USERNAME}]
        raw["content"] = json.dumps(content)
        return raw

    def teardown_ride(self, app):
        with app.app_context():
            from hitch.models import RideEvent

            _db.session.query(RideEvent).delete()
            _db.session.commit()

    def test_a_long_comment_from_the_owner_gets_the_prompt(self, app, client, dist, author):
        _write_spot_file(dist, "Dresden Hauptbahnhof")
        by_spot = dist / "rides" / "by-spot" / f"{SPOT_ID}.json"
        payload = json.loads(by_spot.read_text())
        payload["spot"]["hitchwiki_article"] = "https://hitchwiki.org/en/Dresden"
        by_spot.write_text(json.dumps(payload))

        self._publish(app, "x" * 250)
        try:
            html = client.get("/ride/maps.hitchwiki.org-abc").get_data(as_text=True)
            assert "https://hitchwiki.org/en/Dresden" in html
            assert "Add your notes to the Hitchwiki article" in html
        finally:
            self.teardown_ride(app)

    def test_a_short_comment_gets_no_prompt(self, app, client, dist, author):
        _write_spot_file(dist, "Dresden Hauptbahnhof")
        by_spot = dist / "rides" / "by-spot" / f"{SPOT_ID}.json"
        payload = json.loads(by_spot.read_text())
        payload["spot"]["hitchwiki_article"] = "https://hitchwiki.org/en/Dresden"
        by_spot.write_text(json.dumps(payload))

        self._publish(app, "short")
        try:
            html = client.get("/ride/maps.hitchwiki.org-abc").get_data(as_text=True)
            assert "Add your notes to the Hitchwiki article" not in html
        finally:
            self.teardown_ride(app)

    def test_a_non_owner_never_sees_the_prompt(self, app, client, dist):
        _write_spot_file(dist, "Dresden Hauptbahnhof")
        by_spot = dist / "rides" / "by-spot" / f"{SPOT_ID}.json"
        payload = json.loads(by_spot.read_text())
        payload["spot"]["hitchwiki_article"] = "https://hitchwiki.org/en/Dresden"
        by_spot.write_text(json.dumps(payload))

        import tests.test_instant_ride_row as fixtures

        with app.app_context():
            main_bp._store_published_ride(fixtures._StubEvent(fixtures._raw_event(comment="x" * 250, event_id="e-other")))
        try:
            html = client.get("/ride/maps.hitchwiki.org-abc").get_data(as_text=True)
            assert "Add your notes to the Hitchwiki article" not in html
        finally:
            self.teardown_ride(app)
