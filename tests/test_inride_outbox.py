"""Tests for the durable ride outbox backend: idempotent client d_tags and the
transient-failure (503) classification the offline outbox relies on."""

import json

import hitch.blueprints.main as main
from hitch.blueprints.utils.post_hitchhiking_ride_to_nostr import build_ride_d_tag

# Minimal valid in-ride form (relay is stubbed per-test). Destination present = a Finish.
_FORM = {
    "rate": "4",
    "wait": "10",
    "signal": "",
    "comment": "",
    "vehicle_kind": "",
    "pickup_lat": "52.0",
    "pickup_lon": "13.0",
    "destination_lat": "52.1",
    "destination_lon": "13.1",
    "datetime_ride": "2026-07-08T10:00",
    "arrival_datetime": "2026-07-08T10:20",
}
_HEADERS = {"X-Requested-With": "inride"}


# ── Pure d_tag construction ───────────────────────────────────────────────────
# A retry reuses the client d_tag so the replaceable event (kind 36820) is replaced,
# not duplicated. The source prefix must stay server-side.
def test_build_ride_d_tag_uses_client_id():
    assert build_ride_d_tag("hitchmap", None, "abc-123") == "hitchmap-abc-123"


def test_build_ride_d_tag_reuses_existing_tags_on_edit():
    tags = [["d", "hitchmap-original"], ["published_at", "123"]]
    assert build_ride_d_tag("hitchmap", tags, "ignored-because-edit") == "hitchmap-original"


def test_build_ride_d_tag_mints_uuid_when_nothing_supplied():
    d = build_ride_d_tag("hitchmap", None, None)
    assert d.startswith("hitchmap-") and len(d) > len("hitchmap-")


def test_build_ride_d_tag_falls_back_when_tags_lack_d_tag():
    # An empty or malformed tags list (no ["d", ...] entry) must not raise
    # StopIteration — fall through to client_d_tag / uuid instead.
    assert build_ride_d_tag("hitchmap", [], "abc-123") == "hitchmap-abc-123"
    assert build_ride_d_tag("hitchmap", [["published_at", "123"]], "abc-123") == "hitchmap-abc-123"
    minted = build_ride_d_tag("hitchmap", [], None)
    assert minted.startswith("hitchmap-") and len(minted) > len("hitchmap-")


# ── Endpoint wiring + idempotency ─────────────────────────────────────────────
class _CapturingPoster:
    """Stub poster that records the d_tag it was called with and echoes the real
    construction, so two POSTs with the same client_d_tag yield the same server d."""

    calls = []
    last_event = None

    def post(self, ride_record, tags=None, d_tag=None):
        result = build_ride_d_tag("hitchmap", tags, d_tag)
        _CapturingPoster.calls.append(d_tag)
        return result

    def close(self):
        pass


def test_ride_post_is_idempotent_on_client_d_tag(client, monkeypatch):
    _CapturingPoster.calls = []
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _CapturingPoster)

    form = dict(_FORM, client_d_tag="fixed-uuid-1")
    r1 = client.post("/ride", data=form, headers=_HEADERS)
    r2 = client.post("/ride", data=form, headers=_HEADERS)

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.get_json()["ok"] and r2.get_json()["ok"]
    # Same client id in → same server d out (a retry replaces, never duplicates).
    assert r1.get_json()["d_tag"] == r2.get_json()["d_tag"] == "hitchmap-fixed-uuid-1"
    # And the endpoint actually forwarded the client id to the poster both times.
    assert _CapturingPoster.calls == ["fixed-uuid-1", "fixed-uuid-1"]


# ── Transient failure classification ──────────────────────────────────────────
class _BoomPoster:
    """Poster whose publish fails as if the relay were unreachable."""

    def post(self, ride_record, tags=None, d_tag=None):
        raise ConnectionError("relay unreachable")

    def close(self):
        pass


def test_ride_post_relay_failure_is_transient_503(client, monkeypatch):
    # A dead relay must NOT look like a validation error: the client treats 400 as
    # permanent (flag for manual retry) and 5xx/503 as transient (auto-retry). If relay
    # outages returned 400, queued rides would be wrongly flagged as failed forever.
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _BoomPoster)

    r = client.post("/ride", data=dict(_FORM, client_d_tag="x1"), headers=_HEADERS)

    assert r.status_code == 503
    body = r.get_json()
    assert body["ok"] is False and body["transient"] is True


# ── Intermediate stops end to end (form POST -> create_record_from_custom_object) ──
class _RecordingPoster:
    """Stub poster that captures the built ride_record so a test can inspect its stops."""

    last_record = None
    last_event = None  # _store_published_ride reads this after every post()

    def post(self, ride_record, tags=None, d_tag=None):
        _RecordingPoster.last_record = ride_record
        return build_ride_d_tag("hitchmap", tags, d_tag)

    def close(self):
        pass


def test_ride_stops_form_field_reaches_the_published_record(client, monkeypatch):
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)

    form = dict(_FORM, client_d_tag="stops-1", ride_stops=json.dumps(["onsen", "grandparents' house"]))
    r = client.post("/ride", data=form, headers=_HEADERS)

    assert r.status_code == 200 and r.get_json()["ok"]
    labels = [s.label for s in _RecordingPoster.last_record.stops[1:-1]]
    assert labels == ["onsen", "grandparents' house"]


def test_too_many_ride_stops_is_a_400_not_silently_truncated(client, monkeypatch):
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)

    form = dict(_FORM, client_d_tag="stops-2", ride_stops=json.dumps([f"stop {i}" for i in range(21)]))
    r = client.post("/ride", data=form, headers=_HEADERS)

    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_malformed_ride_stops_json_is_treated_as_no_stops(client, monkeypatch):
    """A tampered or corrupted hidden field must not 500 -- degrade to "no stops"."""
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)

    form = dict(_FORM, client_d_tag="stops-3", ride_stops="not json")
    r = client.post("/ride", data=form, headers=_HEADERS)

    assert r.status_code == 200 and r.get_json()["ok"]
    assert _RecordingPoster.last_record.stops[1:-1] == []
