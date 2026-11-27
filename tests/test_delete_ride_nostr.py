"""Deleting a ride also sends a NIP-09 deletion request to the relays, when we signed it."""

import pytest

from hitch.blueprints import main
from hitch.blueprints.utils.post_hitchhiking_ride_to_nostr import HitchhikingDataStandardToNostrPoster
from hitch.blueprints.utils.report_ride import OWNER_DELETE_REASON
from hitch.models import RideEvent, RideReport, User
from tests.conftest import TEST_PUBKEY

NAME = "nip09hitcher"
FOREIGN_PUBKEY = "ab" * 32


class _RecordingPoster:
    calls = []

    def delete(self, event_id, d_tag, wait=True):
        _RecordingPoster.calls.append((event_id, d_tag))
        return "del-id"

    def close(self):
        pass


@pytest.fixture
def owner(db, client):
    _RecordingPoster.calls = []
    u = User(username=NAME, email="nip09@example.org", password="x", active=True, fs_uniquifier="uq-nip09")
    db.session.add(u)
    db.session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = u.fs_uniquifier
        sess["_fresh"] = True
    yield u
    db.session.rollback()
    db.session.query(RideReport).delete()
    db.session.query(RideEvent).filter(RideEvent.d.like("nip09-%")).delete(synchronize_session=False)
    db.session.query(User).filter_by(id=u.id).delete()
    db.session.commit()


def _ride(db, d, pubkey):
    db.session.add(
        RideEvent(
            id=f"id-{d}",
            kind=36820,
            pubkey=pubkey,
            sig="s" * 128,
            content={"source": "maps.hitchwiki.org", "hitchhikers": [{"nickname": NAME}]},
            tags=[["d", d], ["published_at", "1"]],
            d=d,
            created_at=1,
        )
    )
    db.session.commit()


@pytest.mark.parametrize("pubkey, sends", [(TEST_PUBKEY, True), (FOREIGN_PUBKEY, False)])
def test_delete_ride_requests_nostr_deletion_only_for_our_events(db, client, owner, monkeypatch, pubkey, sends):
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
    d = f"nip09-{sends}"
    _ride(db, d, pubkey)

    assert client.post(f"/delete-ride/{d}").status_code == 302

    assert _RecordingPoster.calls == ([(f"id-{d}", d)] if sends else [])
    # The local hide happens either way: it is what keeps a ride off the map when a relay
    # ignores the request, or when the event isn't ours to delete.
    assert db.session.query(RideReport).filter_by(ride_d_tag=d, reason=OWNER_DELETE_REASON).count() == 1


def test_a_relay_failure_does_not_fail_the_deletion(db, client, owner, monkeypatch):
    class _Broken(_RecordingPoster):
        def delete(self, event_id, d_tag, wait=True):
            raise ConnectionError("relay down")

    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _Broken)
    _ride(db, "nip09-broken", TEST_PUBKEY)

    assert client.post("/delete-ride/nip09-broken").status_code == 302
    assert db.session.query(RideReport).filter_by(ride_d_tag="nip09-broken").count() == 1


def test_poster_builds_a_signed_nip09_event(monkeypatch):
    sent = []

    class _FakeRelays:
        def add_relay(self, url):
            pass

        def publish_event(self, event):
            sent.append(event)

        def run_sync(self):
            pass

    monkeypatch.setenv("NOSTR_EVENT_KIND", "36820")
    monkeypatch.setattr(
        "hitch.blueprints.utils.post_hitchhiking_ride_to_nostr.RelayManager", lambda timeout=5: _FakeRelays()
    )
    poster = HitchhikingDataStandardToNostrPoster()
    event_id = poster.delete("abc123", "maps.hitchwiki.org-xyz", wait=False)

    (event,) = sent
    assert event.kind == 5 and event.id == event_id and event.pubkey == TEST_PUBKEY
    assert event.verify()
    assert ["e", "abc123"] in event.tags
    assert ["a", f"36820:{TEST_PUBKEY}:maps.hitchwiki.org-xyz"] in event.tags
