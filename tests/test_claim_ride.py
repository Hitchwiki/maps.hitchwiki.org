"""Claiming an unattributed ride (the 5-tap easter egg) and which sources allow it.

Two rules are under test and they are separate on purpose:
  * a ride with a named hitchhiker can never be taken off them, and
  * a ride is only writable when we could actually replace its Nostr event — our source
    *and* our signing key (see hitch/blueprints/utils/ride_sources.py).
"""

import json

import pytest

import hitch.blueprints.main as main
from hitch.blueprints.utils.ride_sources import ride_is_replaceable
from hitch.extensions import db as _db
from hitch.models import RideEvent, User
from tests.conftest import TEST_PUBKEY

FOREIGN_PUBKEY = "c" * 64
CLAIMER_USERNAME = "claimer"
UNIQUIFIER = "claim-ride-test-uniquifier"


class _StubEvent:
    """Stands in for a signed pynostr Event: only `to_dict()` is used."""

    def __init__(self, raw):
        self._raw = raw

    def to_dict(self):
        return self._raw


class _RecordingPoster:
    """Fake poster: records what would have gone to the relays, publishes nothing."""

    posted = []

    def __init__(self):
        self.last_event = None

    def post(self, ride_record, tags=None, d_tag=None):
        tag = next(t[1] for t in tags if t[0] == "d")
        content = json.loads(ride_record.model_dump_json(exclude_none=True, by_alias=True))
        _RecordingPoster.posted.append({"d": tag, "tags": tags, "content": content})
        self.last_event = _StubEvent(
            {
                "id": "claim-event",
                "kind": 36820,
                "pubkey": TEST_PUBKEY,
                "sig": "s" * 128,
                "created_at": 1_800_000_100,
                "content": json.dumps(content),
                "tags": tags,
            }
        )
        return tag

    def close(self):
        pass


def _make_ride(d_tag, *, source="maps.hitchwiki.org", pubkey=TEST_PUBKEY, hitchhikers=None):
    content = {
        "version": "1.0.0",
        "source": source,
        "comment": "long wait but a great driver",
        "rating": 4,
        "submission_time": "2026-07-02T16:35:00",
        "license": "odbl",
        "hitchhikers": [{"nickname": "Anonymous"}] if hitchhikers is None else hitchhikers,
        "stops": [
            {
                "location": {"latitude": 51.08170, "longitude": 13.73629, "is_exact": True},
                "waiting_duration": "PT12M",
            },
            {"location": {"latitude": 52.51739, "longitude": 13.39513, "is_exact": False}},
        ],
    }
    return RideEvent(
        id="e-" + d_tag,
        kind=36820,
        pubkey=pubkey,
        sig="s" * 128,
        created_at=1_800_000_000,
        content=content,
        source=source,
        rating=4,
        comment=content["comment"],
        hitchhikers=content["hitchhikers"],
        stops=content["stops"],
        d=d_tag,
        tags=[["d", d_tag], ["published_at", "1800000000"]],
    )


@pytest.fixture
def rides(app):
    """One ride per case, wiped around each test."""
    with app.app_context():
        _db.session.query(RideEvent).delete()
        _db.session.add_all(
            [
                _make_ride("maps.hitchwiki.org-anon"),
                _make_ride("hitchmap.com-anon", source="hitchmap.com"),
                _make_ride("hitchmap.com-foreign-key", source="hitchmap.com", pubkey=FOREIGN_PUBKEY),
                _make_ride("triphopping.com-anon", source="triphopping.com", pubkey=FOREIGN_PUBKEY),
                _make_ride("maps.hitchwiki.org-named", hitchhikers=[{"nickname": "someone-else"}]),
                _make_ride(
                    "maps.hitchwiki.org-anon-pair",
                    hitchhikers=[{"nickname": "Anonymous"}, {"nickname": "Anonymous:female"}],
                ),
            ]
        )
        _db.session.commit()
    yield
    with app.app_context():
        _db.session.query(RideEvent).delete()
        _db.session.commit()


@pytest.fixture
def claimer(app, client):
    """Log a user in the way the OAuth flow does — by seeding Flask-Login's session key."""
    with app.app_context():
        user = User(
            username=CLAIMER_USERNAME,
            email="claimer@example.com",
            password="x",
            active=True,
            fs_uniquifier=UNIQUIFIER,
        )
        _db.session.add(user)
        _db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess["_user_id"] = UNIQUIFIER
        sess["_fresh"] = True

    yield user_id

    with client.session_transaction() as sess:
        sess.clear()
    with app.app_context():
        user = _db.session.get(User, user_id)
        if user:
            _db.session.delete(user)
            _db.session.commit()


@pytest.fixture(autouse=True)
def stub_poster(monkeypatch):
    _RecordingPoster.posted = []
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
    return _RecordingPoster


class TestWhichRidesAreWritable:
    """ride_is_replaceable — the source list and the signing key, both required."""

    @pytest.mark.parametrize(
        "d_tag,expected",
        [
            ("maps.hitchwiki.org-anon", True),
            # An import we published ourselves: another platform's name, our key.
            ("hitchmap.com-anon", True),
            # Same source, but this copy was signed by someone else — republishing would
            # fork the ride rather than replace it.
            ("hitchmap.com-foreign-key", False),
            ("triphopping.com-anon", False),
        ],
    )
    def test_source_and_key_both_decide(self, app, rides, d_tag, expected):
        with app.app_context():
            ride = RideEvent.query.filter_by(d=d_tag).first()
            assert ride_is_replaceable(ride) is expected

    @pytest.mark.parametrize("tags", [None, [], [["published_at", "1800000000"]], [["d", "something-else"]]])
    def test_a_ride_without_usable_tags_is_read_only(self, app, rides, tags):
        """Republishing reuses the `d` tag; a row missing it would mint a new one and so
        put a second copy of the same ride on the map."""
        with app.app_context():
            ride = RideEvent.query.filter_by(d="maps.hitchwiki.org-anon").first()
            ride.tags = tags
            assert ride_is_replaceable(ride) is False


class TestClaimEndpoint:
    def test_an_anonymous_visitor_cannot_claim(self, client, rides):
        resp = client.post("/claim-ride/maps.hitchwiki.org-anon")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "not_logged_in"

    def test_a_missing_ride_is_a_404(self, client, rides, claimer):
        assert client.post("/claim-ride/nope").status_code == 404

    def test_claiming_puts_the_user_on_the_ride(self, app, client, rides, claimer, stub_poster):
        resp = client.post("/claim-ride/maps.hitchwiki.org-anon")
        assert resp.status_code == 200
        assert resp.get_json()["hitchhiker_name"] == CLAIMER_USERNAME

        posted = stub_poster.posted[0]
        assert posted["content"]["hitchhikers"] == [{"nickname": CLAIMER_USERNAME}]
        # The republish has to land on the same ride, not next to it.
        assert posted["d"] == "maps.hitchwiki.org-anon"
        assert ["published_at", "1800000000"] in posted["tags"]

        with app.app_context():
            ride = RideEvent.query.filter_by(d="maps.hitchwiki.org-anon").first()
            assert ride.content["hitchhikers"] == [{"nickname": CLAIMER_USERNAME}]
            # Owning it is the point: the ride is now editable by its claimer.
            assert main._user_is_hitchhiker(ride, _db.session.get(User, claimer))

    def test_an_imported_hitchmap_ride_keeps_its_source(self, app, client, rides, claimer, stub_poster):
        assert client.post("/claim-ride/hitchmap.com-anon").status_code == 200
        # Claiming records who hitched it; it does not pretend the ride was logged here.
        assert stub_poster.posted[0]["content"]["source"] == "hitchmap.com"
        with app.app_context():
            assert RideEvent.query.filter_by(d="hitchmap.com-anon").first().content["source"] == "hitchmap.com"

    def test_another_platforms_ride_cannot_be_claimed(self, client, rides, claimer, stub_poster):
        resp = client.post("/claim-ride/triphopping.com-anon")
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "foreign_source"
        # The error names the platform so the UI can say where to edit it instead.
        assert resp.get_json()["source"] == "triphopping.com"
        assert stub_poster.posted == []

    def test_a_ride_we_did_not_sign_cannot_be_claimed(self, client, rides, claimer, stub_poster):
        assert client.post("/claim-ride/hitchmap.com-foreign-key").status_code == 403
        assert stub_poster.posted == []

    def test_a_ride_with_a_name_on_it_cannot_be_taken(self, app, client, rides, claimer, stub_poster):
        resp = client.post("/claim-ride/maps.hitchwiki.org-named")
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "already_claimed"
        assert stub_poster.posted == []
        with app.app_context():
            ride = RideEvent.query.filter_by(d="maps.hitchwiki.org-named").first()
            assert ride.content["hitchhikers"] == [{"nickname": "someone-else"}]

    def test_anonymous_co_hitchhikers_survive_the_claim(self, client, rides, claimer, stub_poster):
        """A ride hitched by two people still had two people in the car afterwards."""
        assert client.post("/claim-ride/maps.hitchwiki.org-anon-pair").status_code == 200
        assert stub_poster.posted[0]["content"]["hitchhikers"] == [
            {"nickname": CLAIMER_USERNAME},
            {"nickname": "Anonymous:female"},
        ]

    def test_claiming_twice_is_refused_the_second_time(self, client, rides, claimer, stub_poster):
        assert client.post("/claim-ride/maps.hitchwiki.org-anon").status_code == 200
        second = client.post("/claim-ride/maps.hitchwiki.org-anon")
        assert second.status_code == 409
        assert len(stub_poster.posted) == 1
