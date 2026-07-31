"""Claiming an unattributed ride (the 5-tap easter egg) and which rides may be rewritten.

Three rules are under test and they are separate on purpose:
  * a ride with a named hitchhiker can never be taken off them,
  * a ride is only writable when its source *and* its signing key are ours — where "ours"
    includes the older key the bulk imports went out under, and
  * rewriting a ride signed by one of those older keys leaves a copy on the relays we can
    never delete, so the coordinate is retired locally (see SupersededRideEvent).
"""

import json

import pytest

import hitch.blueprints.main as main
from hitch.blueprints.utils import ride_sources
from hitch.blueprints.utils.ride_sources import ride_is_replaceable
from hitch.extensions import db as _db
from hitch.models import RideEvent, SupersededRideEvent, User
from tests.conftest import TEST_PUBKEY

# Stands in for the key the hitchmap.com / hitchwiki.org / liftershalte.info imports were
# published under: ours, but not the one we sign with today.
IMPORT_PUBKEY = "d" * 64
# Another platform's key — never ours, whatever the source says.
FOREIGN_PUBKEY = "c" * 64
CLAIMER_USERNAME = "claimer"
UNIQUIFIER = "claim-ride-test-uniquifier"


@pytest.fixture(autouse=True)
def our_keys(monkeypatch):
    """Pin the historical-key allowlist so the tests don't depend on the deployment's."""
    monkeypatch.delenv("OUR_IMPORT_PUBKEYS", raising=False)
    monkeypatch.setattr(ride_sources, "DEFAULT_IMPORT_PUBKEYS", (IMPORT_PUBKEY,))
    ride_sources.our_ride_pubkeys.cache_clear()
    yield
    ride_sources.our_ride_pubkeys.cache_clear()


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
        _db.session.query(SupersededRideEvent).delete()
        _db.session.add_all(
            [
                _make_ride("maps.hitchwiki.org-anon"),
                _make_ride("hitchmap.com-anon", source="hitchmap.com"),
                # The import key: ours, but not the one we sign with now.
                _make_ride("hitchmap.com-imported", source="hitchmap.com", pubkey=IMPORT_PUBKEY),
                _make_ride("hitchwiki.org-imported", source="hitchwiki.org", pubkey=IMPORT_PUBKEY),
                _make_ride("liftershalte.info-imported", source="liftershalte.info", pubkey=IMPORT_PUBKEY),
                # Our source but a stranger's signature — an event we never published.
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
        _db.session.query(SupersededRideEvent).delete()
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
            # Signed by the key the bulk imports went out under — still ours.
            ("hitchmap.com-imported", True),
            ("hitchwiki.org-imported", True),
            ("liftershalte.info-imported", True),
            # Our source, but an event we never published — a stranger's signature.
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

    def test_an_imported_ride_signed_by_our_old_key_can_be_claimed(self, app, client, rides, claimer):
        assert client.post("/claim-ride/hitchmap.com-imported").status_code == 200
        with app.app_context():
            ride = RideEvent.query.filter_by(d="hitchmap.com-imported").first()
            assert ride.content["hitchhikers"] == [{"nickname": CLAIMER_USERNAME}]

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


class TestSupersededEvents:
    """Rewriting a ride signed by an older key of ours leaves a copy we can never delete.

    The relay keeps both versions — the rewrite goes out under the current key, and NIP-09
    would only accept a deletion signed by the key that published the original. So the old
    coordinate is retired locally and both fetch scripts skip it; without that, the weekly
    full re-fetch re-imports the pre-edit copy and the ride is on the map twice.
    """

    def _rows(self, d_tag):
        return RideEvent.query.filter_by(d=d_tag).all()

    def test_claiming_a_ride_under_our_current_key_retires_nothing(self, app, client, rides, claimer):
        assert client.post("/claim-ride/maps.hitchwiki.org-anon").status_code == 200
        with app.app_context():
            # The event was replaced in place on the relays, so there is nothing to filter.
            assert SupersededRideEvent.query.count() == 0
            assert len(self._rows("maps.hitchwiki.org-anon")) == 1

    def test_claiming_an_imported_ride_retires_the_old_coordinate(self, app, client, rides, claimer):
        assert client.post("/claim-ride/hitchmap.com-imported").status_code == 200
        with app.app_context():
            retired = SupersededRideEvent.query.all()
            assert [(r.pubkey, r.d) for r in retired] == [(IMPORT_PUBKEY, "hitchmap.com-imported")]
            assert retired[0].superseded_at is not None

    def test_the_pre_rewrite_row_is_removed_so_the_ride_is_not_shown_twice(self, app, client, rides, claimer):
        assert client.post("/claim-ride/hitchmap.com-imported").status_code == 200
        with app.app_context():
            rows = self._rows("hitchmap.com-imported")
            assert len(rows) == 1
            # What survives is the rewrite, under the key we sign with now.
            assert rows[0].pubkey == TEST_PUBKEY
            assert rows[0].content["hitchhikers"] == [{"nickname": CLAIMER_USERNAME}]

    def test_retiring_the_same_coordinate_twice_is_a_no_op(self, app, rides):
        """The claim path is not the only caller — editing runs it too, on the same ride."""
        with app.app_context():
            main._retire_superseded_event(IMPORT_PUBKEY, "hitchmap.com-imported")
            main._retire_superseded_event(IMPORT_PUBKEY, "hitchmap.com-imported")
            assert SupersededRideEvent.query.count() == 1

    def test_a_ride_still_under_our_current_key_is_never_retired(self, app, rides):
        with app.app_context():
            ours = RideEvent.query.filter_by(d="maps.hitchwiki.org-anon").first()
            imported = RideEvent.query.filter_by(d="hitchmap.com-imported").first()
            assert ride_sources.needs_supersede(ours) is False
            assert ride_sources.needs_supersede(imported) is True
