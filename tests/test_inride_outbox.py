"""Tests for the durable ride outbox backend: idempotent client d_tags and the
transient-failure (503) classification the offline outbox relies on."""

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


# Same idempotency guarantee for the plain /ride form's retry ("tap Submit to try
# again" after a transient failure): the retry reuses the same client_d_tag input
# unchanged, so it must replace rather than duplicate too, exactly like the in-ride
# tracker's own retries above.
def test_ride_form_retry_with_same_client_d_tag_is_idempotent(client, monkeypatch):
    _CapturingPoster.calls = []
    monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _CapturingPoster)

    form = dict(_FORM, client_d_tag="fixed-uuid-2")
    headers = {"X-Requested-With": "ride-form"}
    r1 = client.post("/ride", data=form, headers=headers)
    r2 = client.post("/ride", data=form, headers=headers)

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.get_json()["ok"] and r2.get_json()["ok"]
    assert r1.get_json()["d_tag"] == r2.get_json()["d_tag"] == "hitchmap-fixed-uuid-2"
    assert _CapturingPoster.calls == ["fixed-uuid-2", "fixed-uuid-2"]


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
