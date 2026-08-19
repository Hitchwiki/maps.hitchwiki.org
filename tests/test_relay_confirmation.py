from types import SimpleNamespace

import hitch.blueprints.utils.post_hitchhiking_ride_to_nostr as poster_module


class _Pool:
    def __init__(self, notices):
        self.notices = list(notices)

    def has_ok_notices(self):
        return bool(self.notices)

    def get_ok_notice(self):
        return self.notices.pop(0)


def _poster(pending, notices):
    poster = poster_module.HitchhikingDataStandardToNostrPoster.__new__(poster_module.HitchhikingDataStandardToNostrPoster)
    poster.pending_event_ids = set(pending)
    poster.relay_manager = SimpleNamespace(message_pool=_Pool(notices))
    return poster


def _ok(event_id, accepted=True, url="wss://relay.example"):
    return SimpleNamespace(
        event_id=event_id,
        ok=accepted,
        url=url,
        message="saved" if accepted else "rate-limited",
    )


def test_silence_is_not_mistaken_for_acceptance(monkeypatch, caplog):
    monkeypatch.setattr(poster_module.time, "sleep", lambda _seconds: None)
    poster = _poster({"event-a"}, [])

    assert poster.flush() is False
    assert poster.pending_event_ids == set()
    assert "No relay confirmed accepting event event-a" in caplog.text


def test_unrelated_ok_notice_does_not_confirm_pending_event(monkeypatch):
    monkeypatch.setattr(poster_module.time, "sleep", lambda _seconds: None)
    poster = _poster({"event-a"}, [_ok("old-event")])

    assert poster.flush() is False


def test_one_acceptance_confirms_even_if_another_relay_rejects(monkeypatch, caplog):
    monkeypatch.setattr(poster_module.time, "sleep", lambda _seconds: None)
    poster = _poster(
        {"event-a"},
        [_ok("event-a", False, "wss://full.example"), _ok("event-a", True)],
    )

    assert poster.flush() is True
    assert "rate-limited" in caplog.text


def test_batch_requires_acceptance_for_every_event(monkeypatch):
    monkeypatch.setattr(poster_module.time, "sleep", lambda _seconds: None)
    poster = _poster({"event-a", "event-b"}, [_ok("event-a")])

    assert poster.flush() is False
