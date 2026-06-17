"""Integration tests: Nostr relay connectivity and map spot generation pipeline."""

import json
import os
import sys

import pytest
import websocket


@pytest.mark.network
def test_nostr_relays_have_at_least_one_ride_event():
    """At least one hitchhiking ride event (kind 36820) exists on the Nostr relays."""
    relays = [
        "wss://relay.nomadwiki.org",
        "wss://relay.trustroots.org",
        "wss://nos.lol",
    ]

    errors = []
    for relay_url in relays:
        try:
            ws = websocket.create_connection(relay_url, timeout=15)
            req = json.dumps(["REQ", "test-sub", {"kinds": [36820], "limit": 1}])
            ws.send(req)

            for _ in range(20):
                msg = ws.recv()
                data = json.loads(msg)
                if data[0] == "EVENT":
                    event = data[2]
                    assert event["kind"] == 36820
                    content = json.loads(event["content"])
                    assert "stops" in content, "Ride event content missing 'stops' field"
                    ws.send(json.dumps(["CLOSE", "test-sub"]))
                    ws.close()
                    return  # Success — at least one event found
                if data[0] == "EOSE":
                    break

            ws.close()
            errors.append(f"{relay_url}: no events returned before EOSE")
        except Exception as exc:
            errors.append(f"{relay_url}: {exc}")

    pytest.fail(
        f"No ride events (kind 36820) found on any Nostr relay. Details: {'; '.join(errors)}"
    )


def test_at_least_one_spot_on_map(tmp_path):
    """After loading ride data and running show, at least 1 spot appears on the map."""
    os.environ.setdefault("RELAYS", '["wss://relay.example.com"]')
    os.environ.setdefault("NSEC", "test_key")

    from unittest.mock import patch

    import hitch.helpers
    from hitch import create_app
    from hitch.extensions import db as _db
    from hitch.models import RideEvent
    from hitch.settings import TestingConfig, config

    db_path = str(tmp_path / "test.sqlite")
    dist_path = str(tmp_path / "dist")
    os.makedirs(dist_path)

    # Create a config subclass with file-based DB so both SQLAlchemy and raw sqlite3 see the same data
    prefix = "sqlite:///" if sys.platform.startswith("win") else "sqlite:////"

    class _IntegrationConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = prefix + db_path
        DATABASE_URI = db_path
        GENERATE_HEATMAP = False
        FORCE_REGENERATE = True

    config["_integration"] = _IntegrationConfig
    app = create_app("_integration")

    sample_stops = [
        {
            "location": {"latitude": 52.5200, "longitude": 13.4050},
            "waiting_duration": "PT15M",
            "departure_time": "2024-06-15T10:00:00",
        },
        {"location": {"latitude": 51.3397, "longitude": 12.3731}},
    ]

    with app.app_context():
        _db.create_all()
        ride = RideEvent(
            id="test_event_abc123",
            kind=36820,
            pubkey="test_pubkey",
            sig="test_sig",
            content={
                "version": "1.0",
                "stops": sample_stops,
                "hitchhikers": [{"nickname": "TestHiker"}],
                "rating": 4,
                "submission_time": "2024-06-15T12:00:00",
                "source": "maps.hitchwiki.org",
            },
            created_at=1718452800,
            version="1.0",
            stops=sample_stops,
            hitchhikers=[{"nickname": "TestHiker"}],
            rating=4,
            submission_time="2024-06-15T12:00:00",
            source="maps.hitchwiki.org",
            d="test-ride-1",
            tags=[["d", "test-ride-1"]],
        )
        _db.session.add(ride)
        _db.session.commit()

        assert _db.session.query(RideEvent).count() == 1

    # Redirect show.py output to temp dist directory
    fake_dirs = dict(hitch.helpers.get_dirs())
    fake_dirs["dist"] = dist_path
    original_dirs_value = hitch.helpers.dirs

    with app.app_context():
        hitch.helpers.dirs = fake_dirs
        # Remove cached show module so it re-executes with patched dirs
        sys.modules.pop("hitch.scripts.show", None)

        with patch("hitch.helpers.get_dirs", return_value=fake_dirs):
            try:
                runner = app.test_cli_runner()
                result = runner.invoke(args=["generate", "show", "--no-heatmap", "--force"])
            finally:
                hitch.helpers.dirs = original_dirs_value

    spots_path = os.path.join(dist_path, "spots.json")
    assert os.path.exists(spots_path), f"spots.json was not generated. CLI output: {result.output}"

    with open(spots_path) as f:
        spots = json.load(f)

    assert len(spots) >= 1, f"Expected at least 1 spot, got {len(spots)}. CLI output: {result.output}"

    spot = spots[0]
    assert spot["lat"] == pytest.approx(52.52, abs=0.01)
    assert spot["lon"] == pytest.approx(13.405, abs=0.01)
    assert spot["review_count"] >= 1
