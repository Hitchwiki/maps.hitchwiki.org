# Instant Ride Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A ride is viewable at `/ride/<d_tag>` and visible on the map the instant its submit POST returns, instead of up to 15 minutes later.

**Architecture:** Three independent shortcuts, each superseded by the normal cron data rather than competing with it. (1) After publishing to Nostr, parse our own signed event with the same function the fetch crons use and upsert it into `ride_event`. (2) A `/pending_rides.json` endpoint serves rides newer than the snapshot `show.py` last read, which `map.js` merges into markers and into the spot pane. (3) The share card links to the ride's own permalink, which now resolves, and that page gets OpenGraph tags.

**Tech Stack:** Flask + SQLAlchemy (SQLite), pynostr, vanilla JS + Leaflet, pytest, `node --test`.

**Design doc:** `docs/superpowers/specs/2026-07-25-instant-ride-visibility-design.md`

## Global Constraints

- **Never `git add -A` / `git add .`** — other agents edit this checkout concurrently. Stage the exact paths listed in each task. Never `git checkout --`, `git restore`, `git reset --hard`, `git clean`, or `git stash`. Commit straight to `main`; no feature branches, no PRs.
- **Re-read a file before editing it** — another session may have changed it since this plan was written. Line numbers in this plan are from 2026-07-25 and may have drifted; match on content.
- **No headless browser on this host** (prod server). Frontend logic is verified with `node --test` against pure modules, and by reading code. Ask the user to check the browser behaviour.
- **Requirement comments:** every non-obvious block gets a comment explaining the *why*, not the *what*. This is a project convention, enforced in review.
- **Lint:** `ruff check` and `ruff format` (line length 130) must pass before every commit.
- **Python tests run in the container, not the host venv.** This is the prod server: the host `.venv` has pytest but *not* Flask, so a host `pytest` dies on `import hitch`. `hitch/blueprints/`, `hitch/scripts/` and `tests/` are baked into the image rather than bind-mounted, so the container runs a stale copy until the edited files are pushed in. Use the helper, which does both and takes pytest arguments:
  `.superpowers/sdd/2026-07-25-instant-ride-visibility/run-tests.sh -v`
  (single file: `… /run-tests.sh tests/test_ride_facts.py -v`). Wherever a task step below says `source .venv/bin/activate && python -m pytest …`, run it through this helper instead. `ruff` needs no app import and runs fine on the host.
- **JS tests:** `node --test tests/` from the project root.
- **The spot id format is `f"{round(lat, 5):.5f}_{round(lon, 5):.5f}"`** — it must match `generate_spot_id` in `hitch/scripts/show.py:708` exactly, or per-spot lookups 404.
- **A ride's `id` in map data is its Nostr `d` tag, not the event id.** `show.py:1096` sets `"id": ride["d"]`, and `renderRideCards` links to `/ride/${r.id}`. Every new payload and every dedupe key follows that.
- **`hitch/scripts/` is not bind-mounted into the container** — changes there need an image rebuild. `hitch/static/` and `dist/` are live. `hitch/templates/` is mounted but cached: a template change needs `sudo docker restart hitchhiking-map`.

---

### Task 1: Shared scalar ride-fact extraction

Pull the per-ride value extraction out of `ride_detail` into a module that `/pending_rides.json` (Task 4) can also use, so there is one implementation instead of a third copy. Behaviour of `/ride/<d_tag>` must not change.

**Files:**
- Create: `hitch/blueprints/utils/ride_facts.py`
- Create: `tests/test_ride_facts.py`
- Modify: `hitch/blueprints/main.py` (the `ride_detail` view, around line 636)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `stop_facts(stops) -> dict` with keys `pickup_lat, pickup_lon, dest_lat, dest_lon, departure_time, arrival_time, waiting_minutes` (all `None` when absent).
  - `haversine_km(lat1, lon1, lat2, lon2) -> float | None`
  - `hitchhiker_name(hitchhikers) -> str` (`"Anonymous"` when unnamed)
  - `is_informative(name, comment, wait) -> bool`
  - `spot_id_for(lat, lon) -> str`
  - `ride_map_entry(ride) -> dict | None` — the `/pending_rides.json` entry for one `RideEvent`-shaped object.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ride_facts.py`:

```python
"""Scalar ride facts shared by /ride/<d_tag> and /pending_rides.json."""

from types import SimpleNamespace

from hitch.blueprints.utils.ride_facts import (
    haversine_km,
    hitchhiker_name,
    is_informative,
    ride_map_entry,
    spot_id_for,
    stop_facts,
)


def _stops(with_destination=True):
    stops = [
        {
            "location": {"latitude": 51.08170, "longitude": 13.73629},
            "departure_time": "2026-07-02T14:00",
            "waiting_duration": "PT12M",
        }
    ]
    if with_destination:
        stops.append(
            {
                "location": {"latitude": 52.51739, "longitude": 13.39513},
                "arrival_time": "2026-07-02T16:30",
            }
        )
    return stops


class TestStopFacts:
    def test_reads_both_ends_of_the_ride(self):
        facts = stop_facts(_stops())
        assert facts["pickup_lat"] == 51.08170
        assert facts["pickup_lon"] == 13.73629
        assert facts["dest_lat"] == 52.51739
        assert facts["dest_lon"] == 13.39513
        assert facts["departure_time"] == "2026-07-02T14:00"
        assert facts["arrival_time"] == "2026-07-02T16:30"
        assert facts["waiting_minutes"] == 12

    def test_a_ride_with_no_destination_has_no_second_stop(self):
        facts = stop_facts(_stops(with_destination=False))
        assert facts["pickup_lat"] == 51.08170
        assert facts["dest_lat"] is None
        assert facts["dest_lon"] is None
        assert facts["arrival_time"] is None

    def test_empty_and_malformed_stops_yield_all_none(self):
        for stops in ([], None, "not a list", [{}]):
            facts = stop_facts(stops)
            assert facts["pickup_lat"] is None
            assert facts["waiting_minutes"] is None

    def test_a_waiting_duration_we_do_not_understand_is_dropped_not_guessed(self):
        # Anything other than the PT<n>M our own form writes (e.g. an hours-based
        # duration from a foreign source) must read as "unknown", never as a number.
        stops = _stops()
        stops[0]["waiting_duration"] = "PT2H30M"
        assert stop_facts(stops)["waiting_minutes"] is None


class TestHaversine:
    def test_known_distance(self):
        # Dresden -> Berlin, ~166 km.
        assert 160 < haversine_km(51.08170, 13.73629, 52.51739, 13.39513) < 172

    def test_missing_endpoint_is_not_a_distance(self):
        assert haversine_km(51.0, 13.0, None, 13.4) is None


class TestHitchhikerName:
    def test_first_named_hitchhiker_wins(self):
        assert hitchhiker_name([{"nickname": "kim"}, {"nickname": "sam"}]) == "kim"

    def test_blank_and_missing_names_read_as_anonymous(self):
        assert hitchhiker_name([{"nickname": "  "}]) == "Anonymous"
        assert hitchhiker_name([{}]) == "Anonymous"
        assert hitchhiker_name([]) == "Anonymous"
        assert hitchhiker_name(None) == "Anonymous"


class TestIsInformative:
    def test_anonymous_rating_only_rides_are_not_informative(self):
        # show.py drops exactly these from every detail view, so surfacing one as
        # pending would show a ride that vanishes at the next cron run.
        assert is_informative("Anonymous", None, None) is False
        assert is_informative("Anonymous", "   ", None) is False

    def test_any_of_a_name_a_comment_or_a_wait_is_enough(self):
        assert is_informative("kim", None, None) is True
        assert is_informative("Anonymous", "long wait but a great driver", None) is True
        assert is_informative("Anonymous", None, 12) is True


class TestSpotId:
    def test_matches_the_five_decimal_frontend_format(self):
        assert spot_id_for(51.0817012, 13.7362899) == "51.08170_13.73629"
        assert spot_id_for(51, 13) == "51.00000_13.00000"
        assert spot_id_for(-8.5, -34.9) == "-8.50000_-34.90000"


class TestRideMapEntry:
    def _ride(self, **overrides):
        fields = dict(
            d="maps.hitchwiki.org-abc",
            stops=_stops(),
            hitchhikers=[{"nickname": "kim"}],
            comment="great ride",
            rating=4,
            submission_time="2026-07-02T16:35:00",
        )
        fields.update(overrides)
        return SimpleNamespace(**fields)

    def test_carries_everything_a_marker_and_a_ride_card_need(self):
        entry = ride_map_entry(self._ride())
        assert entry["id"] == "maps.hitchwiki.org-abc"
        assert entry["spot_id"] == "51.08170_13.73629"
        assert entry["lat"] == 51.08170
        assert entry["lon"] == 13.73629
        assert entry["dest_lat"] == 52.51739
        assert entry["rating"] == 4
        assert entry["wait"] == 12
        assert 160 < entry["distance"] < 172
        assert entry["comment"] == "great ride"
        assert entry["hitchhiker_name"] == "kim"
        assert entry["submission_time"] == "2026-07-02T16:35:00"
        assert entry["ride_datetime"] == "2026-07-02T14:00"
        assert entry["arrival_datetime"] == "2026-07-02T16:30"

    def test_a_ride_with_no_pickup_coordinates_cannot_be_placed(self):
        assert ride_map_entry(self._ride(stops=[])) is None

    def test_a_low_value_ride_is_withheld(self):
        # It would appear for ten minutes and then be dropped by show.py.
        ride = self._ride(hitchhikers=[], comment=None, stops=_stops(with_destination=False))
        assert ride_map_entry(ride) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_ride_facts.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'hitch.blueprints.utils.ride_facts'`.

- [ ] **Step 3: Write the module**

Create `hitch/blueprints/utils/ride_facts.py`:

```python
"""Scalar per-ride facts read out of a RideEvent's `stops` / `hitchhikers`.

One implementation shared by /ride/<d_tag> (which renders a single ride) and
/pending_rides.json (which serves the handful of rides show.py has not picked up yet).
show.py computes the same values in pandas across the whole table; these must stay
numerically identical to it, otherwise a ride would visibly change the moment the cron
takes over from the live endpoint.
"""

import math
import re

# Only the PT<n>M form our own submit path writes. Anything else (a foreign source
# using hours, a malformed value) reads as "no recorded wait" rather than a wrong
# number — an invented wait time would pollute the spot's averages.
_WAITING_DURATION_RE = re.compile(r"^PT(\d+)M$")

EARTH_RADIUS_KM = 6371


def stop_facts(stops):
    """Pickup/destination coordinates and times from a ride's stop list.

    Every key is always present, `None` when the ride does not have it, so callers
    never have to distinguish "absent" from "malformed".
    """
    facts = {
        "pickup_lat": None,
        "pickup_lon": None,
        "dest_lat": None,
        "dest_lon": None,
        "departure_time": None,
        "arrival_time": None,
        "waiting_minutes": None,
    }
    if not isinstance(stops, list) or not stops:
        return facts

    first = stops[0] if isinstance(stops[0], dict) else {}
    location = first.get("location") or {}
    facts["pickup_lat"] = location.get("latitude")
    facts["pickup_lon"] = location.get("longitude")
    facts["departure_time"] = first.get("departure_time")
    match = _WAITING_DURATION_RE.match(first.get("waiting_duration") or "")
    if match:
        facts["waiting_minutes"] = int(match.group(1))

    # A single-stop ride is one where the hitchhiker never recorded where they got to.
    if len(stops) > 1 and isinstance(stops[-1], dict):
        last = stops[-1]
        last_location = last.get("location") or {}
        facts["dest_lat"] = last_location.get("latitude")
        facts["dest_lon"] = last_location.get("longitude")
        facts["arrival_time"] = last.get("arrival_time")

    return facts


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km, or None when either end is missing.

    Same formula show.py applies with `haversine_np`, so a ride's distance does not
    shift when the generated files take over from the live endpoint.
    """
    if None in (lat1, lon1, lat2, lon2):
        return None
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def hitchhiker_name(hitchhikers):
    """Display name for a ride: the first hitchhiker's nickname, else "Anonymous".

    Mirrors get_hitchhiker_name in show.py — the literal string "Anonymous" is what the
    frontend tests against to decide whether to link to a profile.
    """
    if isinstance(hitchhikers, list) and hitchhikers:
        first = hitchhikers[0]
        if isinstance(first, dict):
            nickname = first.get("nickname")
            if isinstance(nickname, str) and nickname.strip():
                return nickname
    return "Anonymous"


def is_informative(name, comment, wait):
    """Whether a ride carries anything beyond a bare rating.

    show.py drops anonymous rides with no comment and no waiting time from every detail
    view (`is_informative`), so serving one here would show a ride for ten minutes and
    then silently take it away again.
    """
    return not (name == "Anonymous" and not (comment or "").strip() and wait is None)


def spot_id_for(lat, lon):
    """The spot id a coordinate belongs to.

    Must stay identical to generate_spot_id in hitch/scripts/show.py — it is the
    rides/by-spot/<id>.json filename and the id map.js derives from marker coordinates,
    so any divergence turns into a 404 or an orphaned marker.
    """
    return f"{round(float(lat), 5):.5f}_{round(float(lon), 5):.5f}"


def ride_map_entry(ride):
    """One /pending_rides.json entry, or None when the ride does not belong on the map.

    `ride` is any object with the RideEvent columns (`d`, `stops`, `hitchhikers`,
    `comment`, `rating`, `submission_time`). The keys match what show.py writes into
    rides/by-spot/<id>.json plus the marker fields from spots.json, so map.js can feed
    the entry straight into the paths that already render both.
    """
    facts = stop_facts(ride.stops)
    if facts["pickup_lat"] is None or facts["pickup_lon"] is None:
        return None

    name = hitchhiker_name(ride.hitchhikers)
    if not is_informative(name, ride.comment, facts["waiting_minutes"]):
        return None

    distance = haversine_km(facts["pickup_lat"], facts["pickup_lon"], facts["dest_lat"], facts["dest_lon"])
    return {
        # The d tag, not the Nostr event id: show.py uses the d tag as a ride's `id` in
        # the per-spot files, and the spot pane links to /ride/<id>.
        "id": ride.d,
        "spot_id": spot_id_for(facts["pickup_lat"], facts["pickup_lon"]),
        "lat": facts["pickup_lat"],
        "lon": facts["pickup_lon"],
        "dest_lat": facts["dest_lat"],
        "dest_lon": facts["dest_lon"],
        "rating": ride.rating,
        "wait": facts["waiting_minutes"],
        "distance": round(distance, 1) if distance is not None else None,
        "comment": ride.comment,
        "hitchhiker_name": name,
        "submission_time": ride.submission_time,
        "ride_datetime": facts["departure_time"],
        "arrival_datetime": facts["arrival_time"],
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_ride_facts.py -v
```

Expected: all PASS.

- [ ] **Step 5: Use the helpers in `ride_detail`**

In `hitch/blueprints/main.py`, add to the imports near the other `hitch.blueprints.utils` imports:

```python
from hitch.blueprints.utils.ride_facts import haversine_km, spot_id_for, stop_facts
```

In `ride_detail`, replace the manual stop parsing (the `stops = content.get("stops") or []` block through the `waiting_minutes` regex) with:

```python
    facts = stop_facts(content.get("stops"))
    pickup_lat = facts["pickup_lat"]
    pickup_lon = facts["pickup_lon"]
    dest_lat = facts["dest_lat"]
    dest_lon = facts["dest_lon"]
    departure_time = facts["departure_time"]
    arrival_time = facts["arrival_time"]
    waiting_minutes = facts["waiting_minutes"]
```

and replace the inline Haversine block (`distance_km = None` through the `2 * 6371 * math.asin(...)` line) with:

```python
    distance_km = haversine_km(pickup_lat, pickup_lon, dest_lat, dest_lon)
```

Leave the rest of the view (hitchhikers with genders, driver, vehicle) untouched — it needs fields the helper deliberately does not carry. `spot_id_for` is imported now but only used in Task 7; if `ruff check` reports `F401` for it, drop it from this task's import line and add it in Task 7 instead.

- [ ] **Step 6: Verify nothing about the ride page changed**

```bash
source .venv/bin/activate && python -m pytest tests/ -v -m "not network" && ruff check && ruff format --check
```

Expected: all PASS. If `math` is now unused in `main.py`, ruff will say so — it is still used elsewhere in the file (the submit handler's NaN handling), so expect no complaint.

- [ ] **Step 7: Commit**

```bash
git add hitch/blueprints/utils/ride_facts.py tests/test_ride_facts.py hitch/blueprints/main.py
git commit -m "refactor(rides): extract shared scalar ride-fact helpers"
```

---

### Task 2: Store the ride locally the moment it is published

**Files:**
- Modify: `hitch/blueprints/utils/post_hitchhiking_ride_to_nostr.py` (the `post` method, around line 76)
- Modify: `hitch/blueprints/main.py` (the `/ride` POST handler, around lines 1136-1170)
- Create: `tests/test_instant_ride_row.py`

**Interfaces:**
- Consumes: `parse_post_to_ride_fields` from `hitch/scripts/nostr_ride_parsing.py` (existing).
- Produces:
  - `HitchhikingDataStandardToNostrPoster.last_event` — the signed `pynostr.event.Event` from the most recent `post()` call, `None` before the first one. `post()` keeps returning the `d` tag string; that contract must not change (`hitch/blueprints/publish_ride.py` and existing tests depend on it).
  - `hitch.blueprints.main._store_published_ride(event) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_instant_ride_row.py`:

```python
"""A submitted ride must be in the local DB — and so on its own page — immediately."""

import json

import pytest

import hitch.blueprints.main as main
from hitch.extensions import db as _db
from hitch.models import RideEvent

PUBKEY = "a" * 64


class _StubEvent:
    """Stands in for a signed pynostr Event: only `to_dict()` is used."""

    def __init__(self, raw):
        self._raw = raw

    def to_dict(self):
        return self._raw


def _raw_event(d_tag="maps.hitchwiki.org-abc", created_at=1_800_000_000, event_id="e1", comment="great ride"):
    content = {
        "version": "1.0.0",
        "source": "maps.hitchwiki.org",
        "comment": comment,
        "rating": 4,
        "submission_time": "2026-07-02T16:35:00",
        "hitchhikers": [{"nickname": "kim"}],
        "stops": [
            {
                "location": {"latitude": 51.08170, "longitude": 13.73629},
                "departure_time": "2026-07-02T14:00",
                "waiting_duration": "PT12M",
            },
            {"location": {"latitude": 52.51739, "longitude": 13.39513}, "arrival_time": "2026-07-02T16:30"},
        ],
    }
    return {
        "id": event_id,
        "kind": 36820,
        "pubkey": PUBKEY,
        "sig": "s" * 128,
        "created_at": created_at,
        "content": json.dumps(content),
        "tags": [["d", d_tag], ["published_at", str(created_at)]],
    }


class _RecordingPoster:
    """Fake poster that publishes nothing but exposes a signed-looking event."""

    def __init__(self):
        self.last_event = None

    def post(self, ride_record, tags=None, d_tag=None):
        tag = "maps.hitchwiki.org-abc"
        if tags is not None:
            tag = next(t[1] for t in tags if t[0] == "d")
        self.last_event = _StubEvent(_raw_event(d_tag=tag))
        return tag

    def close(self):
        pass


@pytest.fixture
def clean_rides(app):
    with app.app_context():
        _db.session.query(RideEvent).delete()
        _db.session.commit()
        yield
        _db.session.query(RideEvent).delete()
        _db.session.commit()


class TestStorePublishedRide:
    def test_inserts_a_brand_new_ride(self, app, clean_rides):
        with app.app_context():
            main._store_published_ride(_StubEvent(_raw_event()))
            row = _db.session.query(RideEvent).filter_by(d="maps.hitchwiki.org-abc").one()
            assert row.rating == 4
            assert row.comment == "great ride"

    def test_reapplying_the_same_event_is_a_no_op(self, app, clean_rides):
        # The 5-minute incremental fetch will hand us back our own event; it must not
        # duplicate the ride or change anything.
        with app.app_context():
            main._store_published_ride(_StubEvent(_raw_event()))
            main._store_published_ride(_StubEvent(_raw_event()))
            rows = _db.session.query(RideEvent).filter_by(d="maps.hitchwiki.org-abc").all()
            assert len(rows) == 1

    def test_an_edit_overwrites_the_row_including_its_primary_key(self, app, clean_rides):
        # A kind-36820 edit reuses (pubkey, d) but is a new event id, so the row is
        # replaced in place rather than added alongside.
        with app.app_context():
            main._store_published_ride(_StubEvent(_raw_event(event_id="e1", created_at=1_800_000_000)))
            main._store_published_ride(
                _StubEvent(_raw_event(event_id="e2", created_at=1_800_000_500, comment="rewritten"))
            )
            rows = _db.session.query(RideEvent).filter_by(d="maps.hitchwiki.org-abc").all()
            assert len(rows) == 1
            assert rows[0].id == "e2"
            assert rows[0].comment == "rewritten"

    def test_a_broken_event_never_breaks_the_submit(self, app, clean_rides):
        # The ride is already on the relay at this point; a local storage failure must
        # not turn a successful publish into a 500.
        with app.app_context():
            main._store_published_ride(_StubEvent({"not": "an event"}))
            assert _db.session.query(RideEvent).count() == 0

    def test_no_event_is_tolerated(self, app, clean_rides):
        with app.app_context():
            main._store_published_ride(None)
            assert _db.session.query(RideEvent).count() == 0


class TestRideIsLiveAfterSubmit:
    def test_the_ride_page_resolves_straight_after_the_post(self, client, monkeypatch, clean_rides):
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        assert client.get("/ride/maps.hitchwiki.org-abc").status_code == 404

        resp = client.post(
            "/ride",
            data={
                "rate": "4",
                "wait": "12",
                "signal": "thumb",
                "comment": "great ride",
                "pickup_lat": "51.08170",
                "pickup_lon": "13.73629",
                "destination_lat": "52.51739",
                "destination_lon": "13.39513",
            },
            headers={"X-Requested-With": "inride"},
        )
        assert resp.status_code == 200

        assert client.get("/ride/maps.hitchwiki.org-abc").status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_instant_ride_row.py -v
```

Expected: FAIL with `AttributeError: module 'hitch.blueprints.main' has no attribute '_store_published_ride'`.

- [ ] **Step 3: Expose the signed event on the poster**

In `hitch/blueprints/utils/post_hitchhiking_ride_to_nostr.py`, add to `__init__`:

```python
        # The most recently published signed event. The caller writes it straight into
        # the local ride_event table so the ride is live before the fetch cron runs;
        # post() still returns only the d tag, which every existing caller relies on.
        self.last_event = None
```

and in `post`, immediately after `event.sign(self.private_key_hex)`:

```python
        self.last_event = event
```

- [ ] **Step 4: Add the upsert helper and call it**

In `hitch/blueprints/main.py`, add the import:

```python
from hitch.scripts.nostr_ride_parsing import parse_post_to_ride_fields
```

and define the helper near the other module-level ride helpers (next to `_user_owns_ride`, around line 96):

```python
def _store_published_ride(event):
    """Write a ride we just published to Nostr straight into the local ride_event table.

    Without this the ride exists only on the relays until fetch_nostr_incremental runs
    (up to 5 min), so /ride/<d_tag> 404s and the author's own ride is missing from their
    profile. We parse our own signed event with parse_post_to_ride_fields — the exact
    function both fetch scripts use — so the row is identical to the one the cron would
    have written, and the cron's upsert then classifies it "unchanged".

    Upsert keyed on the addressable coordinate (pubkey, d), as in
    fetch_nostr_incremental.py. `>=` rather than `>` on created_at: we are the publisher,
    so our event is by definition the newest revision even if an edit lands in the same
    second as the original.

    Known gap: pynostr does not check the relay's OK notice, so a silently rejected event
    leaves a row here that no fetch will ever confirm, and the weekly full fetch_nostr
    (delete-and-recreate) drops it. That is still better than today, where such a ride is
    lost immediately — and it is the same gap dist/temporary.json exists to record.

    Never raises: the ride is already on the relay by the time we get here, so a local DB
    problem must not turn a successful publish into a 500.
    """
    if event is None:
        return
    try:
        fields = parse_post_to_ride_fields(event.to_dict())
        if fields is None or not fields.get("d"):
            return
        row = db.session.query(RideEvent).filter_by(pubkey=fields["pubkey"], d=fields["d"]).first()
        if row is None:
            db.session.add(RideEvent(**fields))
        elif fields["created_at"] >= (row.created_at or 0):
            # An edit publishes a new event id under the same (pubkey, d), so every
            # column is overwritten — including the primary key.
            for column, value in fields.items():
                setattr(row, column, value)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not store the published ride locally; the Nostr fetch cron will import it")
```

Then call it in both branches of the submit handler. In the edit branch, after `poster.close()`:

```python
            _store_published_ride(poster.last_event)
```

and in the new-ride branch, after its `poster.close()`:

```python
            _store_published_ride(poster.last_event)
```

Use `poster.last_event` directly — the attribute now always exists on the real poster. Existing test stubs (`tests/test_inride_submit.py`, `tests/test_anonymous_co_hitchhiker_gender.py`) define fakes without it, so if any test fails with `AttributeError`, add `last_event = None` as a class attribute to that stub rather than weakening the call site with `getattr`.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_instant_ride_row.py -v
```

Expected: all PASS.

- [ ] **Step 6: Run the whole suite and lint**

```bash
source .venv/bin/activate && python -m pytest tests/ -v -m "not network" && ruff check && ruff format --check
```

Expected: all PASS. Fix any stub posters that lack `last_event` as described above.

- [ ] **Step 7: Commit**

```bash
git add hitch/blueprints/utils/post_hitchhiking_ride_to_nostr.py hitch/blueprints/main.py tests/test_instant_ride_row.py
git commit -m "feat(rides): store a published ride locally so /ride/<d_tag> works at once"
```

---

### Task 3: `/pending_rides.json`

Serve the rides `show.py` has not picked up yet, straight from the DB, with the cutoff written by `show.py` itself.

**Files:**
- Modify: `hitch/scripts/show.py` (around line 89, and the end of the file)
- Modify: `hitch/blueprints/main.py` (new route, near `proposed_spots_json` around line 1305)
- Create: `tests/test_pending_rides.py`

**Interfaces:**
- Consumes: `ride_map_entry`, from Task 1.
- Produces:
  - `dist/generated_at.json` — `{"ts": <float epoch seconds>}`, the instant `show.py` read the DB.
  - `GET /pending_rides.json` → a JSON array of `ride_map_entry` dicts.
  - `hitch.blueprints.main._last_generation_ts() -> float | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_pending_rides.py`:

```python
"""Rides logged since show.py last ran, served live so the map shows them at once."""

import json
import os

import pytest

import hitch.blueprints.main as main
from hitch.blueprints.utils.report_ride import OWNER_DELETE_REASON
from hitch.extensions import db as _db
from hitch.models import RideEvent, RideReport

PUBKEY = "a" * 64
GENERATED_TS = 1_800_000_000


def _ride(d_tag, created_at, comment="great ride", nickname="kim", lat=51.08170, lon=13.73629):
    return RideEvent(
        id=f"event-{d_tag}",
        kind=36820,
        pubkey=PUBKEY,
        sig="s" * 128,
        created_at=created_at,
        content={},
        d=d_tag,
        comment=comment,
        rating=4,
        submission_time="2026-07-02T16:35:00",
        hitchhikers=[{"nickname": nickname}] if nickname else [],
        stops=[
            {
                "location": {"latitude": lat, "longitude": lon},
                "departure_time": "2026-07-02T14:00",
                "waiting_duration": "PT12M",
            }
        ],
    )


@pytest.fixture
def dist(app, tmp_path, monkeypatch):
    """Point main.py at a throwaway dist/ and clear the ride tables around each test."""
    monkeypatch.setattr(main, "get_dirs", lambda: {"dist": str(tmp_path)})
    with app.app_context():
        _db.session.query(RideEvent).delete()
        _db.session.query(RideReport).delete()
        _db.session.commit()
    yield tmp_path
    with app.app_context():
        _db.session.query(RideEvent).delete()
        _db.session.query(RideReport).delete()
        _db.session.commit()


def _write_generated_at(dist, ts=GENERATED_TS):
    (dist / "generated_at.json").write_text(json.dumps({"ts": ts}))


def _add(app, *rides):
    with app.app_context():
        for ride in rides:
            _db.session.add(ride)
        _db.session.commit()


class TestCutoff:
    def test_a_ride_older_than_the_last_generation_is_not_pending(self, app, client, dist):
        _write_generated_at(dist)
        _add(app, _ride("old", GENERATED_TS - 60))
        assert client.get("/pending_rides.json").get_json() == []

    def test_a_ride_logged_since_the_last_generation_is_pending(self, app, client, dist):
        _write_generated_at(dist)
        _add(app, _ride("fresh", GENERATED_TS + 60))
        payload = client.get("/pending_rides.json").get_json()
        assert [entry["id"] for entry in payload] == ["fresh"]
        assert payload[0]["spot_id"] == "51.08170_13.73629"
        assert payload[0]["wait"] == 12

    def test_falls_back_to_the_rides_index_mtime(self, app, client, dist):
        # Before the first show.py run that writes generated_at.json. The index mtime is
        # LATER than the snapshot it was built from, so this under-returns rather than
        # over-returns: worst case a ride waits for the cron, as it does today.
        index = dist / "rides_index.json"
        index.write_text("[]")
        os.utime(index, (GENERATED_TS, GENERATED_TS))
        _add(app, _ride("old", GENERATED_TS - 60), _ride("fresh", GENERATED_TS + 60))
        assert [e["id"] for e in client.get("/pending_rides.json").get_json()] == ["fresh"]

    def test_no_generated_data_at_all_yields_nothing(self, app, client, dist):
        _add(app, _ride("fresh", GENERATED_TS + 60))
        assert client.get("/pending_rides.json").get_json() == []


class TestExclusions:
    def test_an_owner_deleted_ride_is_withheld(self, app, client, dist):
        # It would otherwise reappear on the map for ten minutes after being hidden.
        _write_generated_at(dist)
        _add(app, _ride("fresh", GENERATED_TS + 60))
        with app.app_context():
            _db.session.add(RideReport(ride_d_tag="fresh", user_id=1, reason=OWNER_DELETE_REASON))
            _db.session.commit()
        assert client.get("/pending_rides.json").get_json() == []

    def test_two_reports_for_the_same_reason_hide_the_ride(self, app, client, dist):
        _write_generated_at(dist)
        _add(app, _ride("fresh", GENERATED_TS + 60))
        with app.app_context():
            _db.session.add(RideReport(ride_d_tag="fresh", user_id=1, reason="spam"))
            _db.session.add(RideReport(ride_d_tag="fresh", user_id=2, reason="spam"))
            _db.session.commit()
        assert client.get("/pending_rides.json").get_json() == []

    def test_a_single_report_does_not(self, app, client, dist):
        _write_generated_at(dist)
        _add(app, _ride("fresh", GENERATED_TS + 60))
        with app.app_context():
            _db.session.add(RideReport(ride_d_tag="fresh", user_id=1, reason="spam"))
            _db.session.commit()
        assert [e["id"] for e in client.get("/pending_rides.json").get_json()] == ["fresh"]

    def test_an_anonymous_rating_only_ride_is_withheld(self, app, client, dist):
        _write_generated_at(dist)
        ride = _ride("fresh", GENERATED_TS + 60, comment=None, nickname=None)
        ride.stops[0].pop("waiting_duration")
        _add(app, ride)
        assert client.get("/pending_rides.json").get_json() == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_pending_rides.py -v
```

Expected: FAIL — every request 404s, so `.get_json()` returns `None`.

- [ ] **Step 3: Make `show.py` record its snapshot instant**

In `hitch/scripts/show.py`, add `import time` to the imports if it is not already there. Then immediately before `rides_df = pd.read_sql("select * from ride_event", get_db())` (around line 89):

```python
# Instant every generated file below is derived from. Captured BEFORE the read, not
# after the writes: /pending_rides.json serves rides created at or after this timestamp,
# and a ride landing while this script runs must count as pending rather than be
# silently skipped by a cutoff taken once the files are already on disk.
snapshot_ts = time.time()
```

At the very end of the file, after the heatmap block and before `logger.info("All data preparation completed")`:

```python
# Written last, so the file never claims a snapshot whose data is not yet on disk.
# /pending_rides.json reads it to decide which rides the map is still missing.
write_json_file({"ts": snapshot_ts}, "generated_at.json")
```

The early-exit path at the top ("JSON files are up to date") deliberately leaves the old timestamp in place: it is only taken when nothing has been written to the DB since the last generation, so there is nothing pending to miss.

- [ ] **Step 4: Add the endpoint**

In `hitch/blueprints/main.py`, extend the existing report-constant import to include the threshold:

```python
from hitch.blueprints.utils.report_ride import OWNER_DELETE_REASON, REPORT_REASONS, REPORTS_TO_HIDE
```

Add `ride_map_entry` to the `ride_facts` import from Task 1. Then, next to `proposed_spots_json` (around line 1305):

```python
def _last_generation_ts():
    """Epoch seconds of the DB snapshot the generated map files were built from.

    show.py writes dist/generated_at.json as its last act. Before the first run that
    does so, fall back to the rides index's mtime — that is LATER than the snapshot it
    was built from, so the fallback under-returns pending rides rather than
    double-showing rides that are already in the generated files. Returns None when
    nothing has been generated at all, in which case there is no map data to add to.
    """
    dist = get_dirs()["dist"]
    try:
        with open(os.path.join(dist, "generated_at.json")) as f:
            return float(json.load(f)["ts"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        return os.path.getmtime(os.path.join(dist, "rides_index.json"))
    except OSError:
        return None


def _hidden_ride_dtags(d_tags):
    """Which of these rides are hidden from the map by reports.

    Same rule show.py applies before generating anything: REPORTS_TO_HIDE distinct
    reporters agreeing on one reason, or a single owner-deletion row. Scoped to the
    d tags we are about to serve, since that is only ever a handful of rides.
    """
    if not d_tags:
        return set()
    rows = (
        db.session.query(RideReport.ride_d_tag, RideReport.reason, func.count().label("n"))
        .filter(RideReport.ride_d_tag.in_(list(d_tags)))
        .group_by(RideReport.ride_d_tag, RideReport.reason)
        .all()
    )
    return {r.ride_d_tag for r in rows if r.n >= REPORTS_TO_HIDE or r.reason == OWNER_DELETE_REASON}


@main_bp.route("/pending_rides.json")
def pending_rides_json():
    """Rides logged since show.py last generated the map files.

    Served straight from the DB (like /proposed_spots.json) rather than from dist/, so a
    ride submitted seconds ago is on the map immediately instead of waiting up to 15
    minutes for the fetch and generate crons. Normally an empty array; at most it holds
    the last few minutes of rides, so it needs no caching of its own. map.js merges these
    into the markers and into the spot pane, deduping on the ride's d tag once the
    generated files catch up.
    """
    since = _last_generation_ts()
    if since is None:
        return jsonify([])

    rides = db.session.query(RideEvent).filter(RideEvent.created_at >= int(since)).all()
    hidden = _hidden_ride_dtags([r.d for r in rides if r.d])
    entries = []
    for ride in rides:
        if ride.d in hidden:
            continue
        entry = ride_map_entry(ride)
        if entry is not None:
            entries.append(entry)
    return jsonify(entries)
```

Add `from sqlalchemy import func` to the imports if `func` is not already imported in `main.py`.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_pending_rides.py -v
```

Expected: all PASS.

- [ ] **Step 6: Check the whole suite and lint**

```bash
source .venv/bin/activate && python -m pytest tests/ -v -m "not network" && ruff check && ruff format --check
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add hitch/scripts/show.py hitch/blueprints/main.py tests/test_pending_rides.py
git commit -m "feat(map): serve rides show.py has not generated yet at /pending_rides.json"
```

---

### Task 4: Pure merge logic for pending rides

A standalone, `require()`-able module so the merge and dedupe rules are unit-tested under `node` — no browser is available on this host.

**Files:**
- Create: `hitch/static/pending_rides.js`
- Create: `tests/pending_rides.test.js`

**Interfaces:**
- Consumes: the `/pending_rides.json` entry shape from Task 3.
- Produces (browser: `window.PendingRides`; Node: `module.exports`):
  - `SNAP_METRES` — `50`
  - `distanceM(aLat, aLon, bLat, bLon) -> number`
  - `planPendingMerge(pending, spots) -> {attach: [{spotId, rides}], create: [{spotId, lat, lon, rating, review_count, rides}]}` where `spots` is `[{lat, lon, spotId}]`
  - `mergeSpotRides(fileRides, pendingRides) -> array` — deduped on `id`, generated file wins

- [ ] **Step 1: Write the failing test**

Create `tests/pending_rides.test.js`:

```js
const test = require("node:test");
const assert = require("node:assert");
const PendingRides = require("../hitch/static/pending_rides.js");

const DRESDEN = { lat: 51.0817, lon: 13.73629 };

function ride(over) {
  return Object.assign(
    { id: "d1", spot_id: "51.08170_13.73629", lat: DRESDEN.lat, lon: DRESDEN.lon, rating: 4 },
    over,
  );
}

test("a pending ride at a known spot attaches to that spot", () => {
  const spots = [{ lat: DRESDEN.lat, lon: DRESDEN.lon, spotId: "51.08170_13.73629" }];
  const plan = PendingRides.planPendingMerge([ride()], spots);
  assert.strictEqual(plan.create.length, 0);
  assert.strictEqual(plan.attach.length, 1);
  assert.strictEqual(plan.attach[0].spotId, "51.08170_13.73629");
  assert.strictEqual(plan.attach[0].rides.length, 1);
});

test("a ride metres from a known spot snaps onto it instead of making a twin marker", () => {
  // show.py merges rides within 5 m into one anchor and can group a whole service area,
  // so the spot the cron will file this under is NOT the ride's own rounded coordinate.
  const spots = [{ lat: DRESDEN.lat, lon: DRESDEN.lon, spotId: "51.08170_13.73629" }];
  const nudged = ride({ id: "d2", lat: DRESDEN.lat + 0.0002, spot_id: "51.08190_13.73629" });
  const plan = PendingRides.planPendingMerge([nudged], spots);
  assert.strictEqual(plan.create.length, 0);
  assert.strictEqual(plan.attach[0].spotId, "51.08170_13.73629");
});

test("a ride far from every known spot creates a new one", () => {
  const spots = [{ lat: DRESDEN.lat, lon: DRESDEN.lon, spotId: "51.08170_13.73629" }];
  const far = ride({ id: "d3", lat: 52.51739, lon: 13.39513, spot_id: "52.51739_13.39513" });
  const plan = PendingRides.planPendingMerge([far], spots);
  assert.strictEqual(plan.attach.length, 0);
  assert.strictEqual(plan.create.length, 1);
  assert.strictEqual(plan.create[0].spotId, "52.51739_13.39513");
  assert.strictEqual(plan.create[0].lat, 52.51739);
  assert.strictEqual(plan.create[0].review_count, 1);
  assert.strictEqual(plan.create[0].rating, 4);
});

test("several rides at one new spot become a single marker", () => {
  const plan = PendingRides.planPendingMerge(
    [ride({ id: "a", rating: 5 }), ride({ id: "b", rating: 3 })],
    [],
  );
  assert.strictEqual(plan.create.length, 1);
  assert.strictEqual(plan.create[0].review_count, 2);
  assert.strictEqual(plan.create[0].rating, 4);
});

test("a new spot with no rated ride still gets a marker", () => {
  const plan = PendingRides.planPendingMerge([ride({ rating: null })], []);
  assert.strictEqual(plan.create.length, 1);
  assert.strictEqual(plan.create[0].rating, null);
});

test("an unplaceable pending ride is ignored rather than dropped on null island", () => {
  const plan = PendingRides.planPendingMerge([ride({ lat: null, lon: null })], []);
  assert.strictEqual(plan.attach.length, 0);
  assert.strictEqual(plan.create.length, 0);
});

test("a bad payload never throws", () => {
  for (const bad of [null, undefined, "nope", {}]) {
    const plan = PendingRides.planPendingMerge(bad, null);
    assert.deepStrictEqual(plan, { attach: [], create: [] });
  }
});

test("mergeSpotRides keeps the generated copy once the cron catches up", () => {
  const fromFile = [{ id: "d1", comment: "from the generated file" }];
  const pending = [{ id: "d1", comment: "from the live endpoint" }, { id: "d2", comment: "still pending" }];
  const merged = PendingRides.mergeSpotRides(fromFile, pending);
  assert.strictEqual(merged.length, 2);
  assert.strictEqual(merged.find((r) => r.id === "d1").comment, "from the generated file");
  assert.ok(merged.find((r) => r.id === "d2"));
});

test("mergeSpotRides copes with an absent file (a brand-new spot)", () => {
  const merged = PendingRides.mergeSpotRides([], [{ id: "d2" }]);
  assert.strictEqual(merged.length, 1);
});

test("distanceM is metres, not kilometres or radians", () => {
  const d = PendingRides.distanceM(51.0, 13.0, 51.001, 13.0);
  assert.ok(d > 105 && d < 120, `expected ~111 m, got ${d}`);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
node --test tests/pending_rides.test.js
```

Expected: FAIL, `Cannot find module '../hitch/static/pending_rides.js'`.

- [ ] **Step 3: Write the module**

Create `hitch/static/pending_rides.js`:

```js
// Pure merge rules for /pending_rides.json — the rides logged since show.py last
// generated the map files. Kept out of map.js so they are unit-testable under Node
// (no browser is available on the prod host). Browser: window.PendingRides;
// Node: module.exports. Same dual-export shape as ride_submit.js.
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.PendingRides = mod;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // How far a pending ride may sit from an existing marker and still be treated as
  // belonging to it. A pending ride carries its RAW pickup coordinate, while spots.json
  // carries the anchor show.py merged it into (5 m merge radius, then service-area /
  // road-island polygon grouping). Without a snap, a ride at a well-known spot would
  // draw a second marker a few metres away that vanishes at the next cron run.
  const SNAP_METRES = 50;

  const EARTH_RADIUS_M = 6371000;

  function distanceM(aLat, aLon, bLat, bLon) {
    const toRad = Math.PI / 180;
    const dLat = (bLat - aLat) * toRad;
    const dLon = (bLon - aLon) * toRad;
    const h =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(aLat * toRad) * Math.cos(bLat * toRad) * Math.sin(dLon / 2) ** 2;
    return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
  }

  function isPlaceable(ride) {
    return (
      ride &&
      typeof ride.lat === "number" &&
      typeof ride.lon === "number" &&
      Number.isFinite(ride.lat) &&
      Number.isFinite(ride.lon)
    );
  }

  function nearestSpot(ride, spots) {
    let best = null;
    let bestDistance = SNAP_METRES;
    for (const spot of spots) {
      const d = distanceM(ride.lat, ride.lon, spot.lat, spot.lon);
      if (d <= bestDistance) {
        bestDistance = d;
        best = spot;
      }
    }
    return best;
  }

  function meanRating(rides) {
    const ratings = rides.map((r) => r.rating).filter((r) => typeof r === "number");
    if (!ratings.length) return null;
    return ratings.reduce((a, b) => a + b, 0) / ratings.length;
  }

  // Split pending rides into those that belong to a marker already on the map and those
  // that need one. `spots` is [{lat, lon, spotId}] — whatever is currently drawn.
  function planPendingMerge(pending, spots) {
    const result = { attach: [], create: [] };
    if (!Array.isArray(pending)) return result;
    const known = Array.isArray(spots) ? spots : [];

    const attachGroups = new Map();
    const createGroups = new Map();

    for (const ride of pending) {
      if (!isPlaceable(ride)) continue;
      const spot = nearestSpot(ride, known);
      if (spot) {
        if (!attachGroups.has(spot.spotId)) attachGroups.set(spot.spotId, []);
        attachGroups.get(spot.spotId).push(ride);
      } else {
        // Rides at a genuinely new place group by their own spot id. Two rides logged
        // a few metres apart within one cron window would draw two markers; that is
        // rare enough to accept rather than reimplement show.py's clustering here.
        if (!createGroups.has(ride.spot_id)) createGroups.set(ride.spot_id, []);
        createGroups.get(ride.spot_id).push(ride);
      }
    }

    for (const [spotId, rides] of attachGroups) result.attach.push({ spotId, rides });
    for (const [spotId, rides] of createGroups) {
      result.create.push({
        spotId: spotId,
        lat: rides[0].lat,
        lon: rides[0].lon,
        rating: meanRating(rides),
        review_count: rides.length,
        rides: rides,
      });
    }
    return result;
  }

  // Combine a spot's generated ride list with its pending ones. The generated copy wins
  // on a tie: during the overlap window (files regenerated, this page's pending list
  // fetched before that) the same ride is in both, keyed by its d tag.
  function mergeSpotRides(fileRides, pendingRides) {
    const merged = Array.isArray(fileRides) ? fileRides.slice() : [];
    const seen = new Set(merged.map((r) => r.id));
    for (const ride of pendingRides || []) {
      if (!seen.has(ride.id)) merged.push(ride);
    }
    return merged;
  }

  return { SNAP_METRES, distanceM, planPendingMerge, mergeSpotRides };
});
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
node --test tests/pending_rides.test.js
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add hitch/static/pending_rides.js tests/pending_rides.test.js
git commit -m "feat(map): pure merge rules for pending rides"
```

---

### Task 5: Draw pending rides on the map

**Files:**
- Modify: `hitch/templates/map.html` (script tags, around lines 74-81)
- Modify: `hitch/static/map.js` (init sequence around line 355; `handleMarkerClick` around line 2300; a new loader near `loadProposedSpotMarkers` around line 1205)

**Interfaces:**
- Consumes: `window.PendingRides` (Task 4), `GET /pending_rides.json` (Task 3).
- Produces: `pendingRidesBySpot` — module-scoped `Map<spotId, ride[]>`, read by `handleMarkerClick`.

- [ ] **Step 1: Load the module in the page**

In `hitch/templates/map.html`, add after the `ride_submit.js` tag:

```html
<script src="{{ asset_url('/static/pending_rides.js') }}"></script>
```

It must load before `map.js` uses it at init time; the existing tags are all plain (non-deferred) scripts executed in order, and `map.js` only calls into it from `async` init, so placing it anywhere in that block works. Keep it next to the other pure helper modules.

- [ ] **Step 2: Add the loader in `map.js`**

Near `loadProposedSpotMarkers` (around line 1205), add:

```js
// Rides logged since show.py last generated the map files, keyed by the spot they
// belong to. handleMarkerClick merges these into what it fetches from
// rides/by-spot/<sid>.json so a just-logged ride is in the spot pane immediately.
let pendingRidesBySpot = new Map();

// Fetch /pending_rides.json and fold it into the markers. Non-blocking overlay like
// loadProposedSpotMarkers, and must run after loadMarkers (it reads allMarkers and adds
// to markerCluster). Silent on any failure: a missing endpoint or a bad payload leaves
// the map exactly as the generated files drew it.
async function loadPendingRides(map) {
  if (!window.PendingRides) return;
  let data;
  try {
    const resp = await fetch("/pending_rides.json");
    if (!resp.ok) return;
    data = await resp.json();
  } catch (error) {
    console.warn("Could not load pending rides:", error);
    return;
  }
  if (!Array.isArray(data) || !data.length) return;

  const spots = allMarkers.map((m) => {
    const latlng = m.getLatLng();
    return { lat: latlng.lat, lon: latlng.lng, spotId: m.options.spotId };
  });
  const plan = window.PendingRides.planPendingMerge(data, spots);

  const markersBySpotId = new Map(allMarkers.map((m) => [m.options.spotId, m]));
  for (const group of plan.attach) {
    const marker = markersBySpotId.get(group.spotId);
    if (!marker) continue;
    // Only the count moves. show.py's mean rating is taken over a filtered ride set
    // (low-value rides are dropped from detail views but still counted here), and that
    // filter is not reproducible client-side — a recomputed colour would be subtly
    // wrong for ten minutes, which is worse than a stale one.
    marker.options._data.review_count = (marker.options._data.review_count || 0) + group.rides.length;
    pendingRidesBySpot.set(group.spotId, group.rides);
  }

  for (const spot of plan.create) {
    addPendingSpotMarker(spot);
    pendingRidesBySpot.set(spot.spotId, spot.rides);
  }

  console.log(`Loaded ${data.length} pending ride(s) into ${plan.attach.length + plan.create.length} spot(s)`);
}

// Draw a marker for a spot that has no entry in spots.json yet — the first ride ever
// logged there. Styled exactly like loadMarkers' circle markers so it is
// indistinguishable from a generated one, and carries the same spotId/_data contract
// that handleMarkerClick depends on.
function addPendingSpotMarker(spot) {
  const rating = spot.rating || 3;
  const color = { 1: "red", 2: "orange", 3: "yellow", 4: "lightgreen", 5: "lightgreen" }[Math.round(rating)];
  const opacity = { 1: 0.3, 2: 0.4, 3: 0.6, 4: 0.8, 5: 0.8 }[Math.round(rating)];
  const coords = new L.latLng(spot.lat, spot.lon);
  const marker = L.circleMarker(coords, {
    radius: 5,
    weight: 1,
    fillOpacity: opacity,
    color: "black",
    fillColor: color,
    spotId: spot.spotId,
    _data: { lat: spot.lat, lon: spot.lon, rating: rating, review_count: spot.review_count, text: "" },
  });
  marker.on("click", async (e) => await handleMarkerClick(marker, coords, e));
  marker.addTo(markerCluster);
  allMarkers.push(marker);
}
```

- [ ] **Step 3: Call it during init**

In `map.js`, after the `loadProposedSpotMarkers(map);` call (around line 355):

```js
  // Rides logged since the last show.py run — non-blocking, like the overlays above.
  loadPendingRides(map);
```

- [ ] **Step 4: Merge pending rides into the spot pane**

In `handleMarkerClick` (around line 2340), replace the sort block's input. After the `try/catch` that fetches the per-spot file and before the `spotRides.sort(...)` call, insert:

```js
  // Fold in rides show.py has not generated yet. Deduped on the d tag, so a ride that
  // is in both (the files regenerated after this page loaded its pending list) renders
  // once. A brand-new spot has no file at all — the 404 branch above leaves spotRides
  // empty and this supplies its single ride.
  if (window.PendingRides) {
    spotRides = window.PendingRides.mergeSpotRides(spotRides, pendingRidesBySpot.get(spotId));
  }
```

`spotRides` is declared with `let`, so reassignment is fine. Verify that before editing — if it is `const` in the current file, change the declaration to `let`.

- [ ] **Step 5: Verify by reading and by exercising the pure parts**

No browser on this host. Run:

```bash
node --test tests/ && node --check hitch/static/map.js && node --check hitch/static/pending_rides.js
```

Expected: all JS tests PASS and both `--check` calls exit 0 (syntax valid).

Then re-read the three edited regions of `map.js` and confirm: `loadPendingRides` is called after `await loadMarkers(map)`; `pendingRidesBySpot` is declared before both its uses; `addPendingSpotMarker` uses the same `spotId`/`_data` keys `handleMarkerClick` reads.

- [ ] **Step 6: Commit**

```bash
git add hitch/templates/map.html hitch/static/map.js
git commit -m "feat(map): show rides logged since the last generate run"
```

- [ ] **Step 7: Ask the user to check the browser behaviour**

Report that this needs a browser check, and that `hitch/templates/map.html` changed, so the container needs `sudo docker restart hitchhiking-map` before the new script tag is served. What to look for: logging a ride puts it at the top of that spot's pane on the next map load, a ride at a brand-new location draws a marker, and neither is duplicated after the 10-minute cron catches up.

---

### Task 6: Share the ride's own permalink

**Files:**
- Modify: `hitch/blueprints/main.py` (the three success redirects, around lines 1210-1216)
- Modify: `hitch/static/map.js` (`setupShareCard`, around line 2770)
- Modify: `hitch/static/share_card.js` (`build`, around line 455)
- Modify: `tests/test_instant_ride_row.py` (add the redirect assertion)

**Interfaces:**
- Consumes: the `d_tag` computed in the submit handler (existing).
- Produces: `window.hmShareCard.build(ride, dTag)` — `dTag` optional; when present the card's `url` is `/ride/<dTag>`, otherwise the existing `/spot/<spotId>` fallback.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_instant_ride_row.py`:

```python
class TestSuccessRedirectCarriesTheDTag:
    def test_a_new_ride_redirects_with_its_d_tag(self, client, monkeypatch, clean_rides):
        # The full-page POST navigates away, so the redirect URL is the only channel
        # through which the success overlay can learn the ride's permalink.
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        resp = client.post(
            "/ride",
            data={
                "rate": "4",
                "wait": "12",
                "signal": "thumb",
                "comment": "great ride",
                "pickup_lat": "51.08170",
                "pickup_lon": "13.73629",
                "destination_lat": "",
                "destination_lon": "",
            },
        )
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/?ride=maps.hitchwiki.org-abc#success-anon"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
source .venv/bin/activate && python -m pytest tests/test_instant_ride_row.py::TestSuccessRedirectCarriesTheDTag -v
```

Expected: FAIL — `Location` is `/#success-anon`.

- [ ] **Step 3: Put the d tag in the redirect**

In `hitch/blueprints/main.py`, replace the three success redirects at the end of the submit handler:

```python
        # The d tag travels in the URL because the full-page POST navigates away: the
        # success overlay's share card links to /ride/<d_tag>, which now resolves
        # immediately (see _store_published_ride). map.js strips the param once read.
        success_query = f"/?ride={quote(d_tag)}"
        if not edit_d_tag:
            if current_user.is_anonymous:
                return redirect(f"{success_query}#success-anon")
            if any(is_anonymous_co_hitchhiker(ch) for ch in data.get("co_hitchhiker", "").split(",")):
                return redirect(f"{success_query}#success-invite")
        return redirect(f"{success_query}#success")
```

Add `from urllib.parse import quote` to the imports if it is not already there. Leave the `/#success-duplicate` redirect (the duplicate report, around line 1261) alone — no ride is created there.

- [ ] **Step 4: Run the test to verify it passes**

```bash
source .venv/bin/activate && python -m pytest tests/test_instant_ride_row.py -v
```

Expected: all PASS.

- [ ] **Step 5: Use the permalink in the share card**

In `hitch/static/share_card.js`, change the `build` signature from `function build(ride)` to `function build(ride, dTag)` (keep the `window.hmShareCard = { build: build }` export as is), and replace the URL block:

```js
      // The ride's own permalink. It resolves as soon as the submit POST returns —
      // the server writes the published event into the local DB rather than waiting
      // for the Nostr fetch cron. Falls back to the starting spot when no d tag
      // reached us: the offline outbox submits over fetch without navigating, and a
      // returning visitor can be running this file against a cached older page.
      const spotId = from.lat.toFixed(5) + "_" + from.lon.toFixed(5);
      const url = dTag
        ? window.location.origin + "/ride/" + encodeURIComponent(dTag)
        : window.location.origin + "/spot/" + spotId;
```

- [ ] **Step 6: Pass the d tag through from `map.js`**

In `map.js`'s `setupShareCard`, after `const ride = takeLastRide();`:

```js
  // The submit redirect carries the new ride's d tag as ?ride=<d_tag>. Read it, then
  // drop it from the URL: it is a one-shot hand-off, not part of the map's address.
  // replaceState, not pushState — canonicalising is not a navigation.
  const params = new URLSearchParams(window.location.search);
  const dTag = params.get("ride");
  if (dTag) history.replaceState({}, "", "/" + window.location.hash);
```

and change the build call from `.build(ride)` to:

```js
    .build(ride, dTag)
```

- [ ] **Step 7: Verify**

```bash
source .venv/bin/activate && python -m pytest tests/ -v -m "not network" && ruff check && ruff format --check
node --test tests/ && node --check hitch/static/share_card.js && node --check hitch/static/map.js
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add hitch/blueprints/main.py hitch/static/share_card.js hitch/static/map.js tests/test_instant_ride_row.py
git commit -m "feat(share): share a ride's own permalink instead of its spot"
```

---

### Task 7: Link preview for the ride page

**Files:**
- Modify: `hitch/blueprints/main.py` (`ride_detail`, around line 636)
- Modify: `hitch/templates/ride_detail.html` (the block declarations at the top)
- Create: `tests/test_ride_page_preview.py`

**Interfaces:**
- Consumes: `_spot_preview` (existing, `main.py:157`), `spot_id_for` (Task 1), the `SpotName` model.
- Produces: `hitch.blueprints.main._ride_preview_meta(ride_view, spot_id) -> (title, description)`; template variables `og_title` and `og_description` on `ride_detail.html`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ride_page_preview.py`:

```python
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
            _db.session.add(SpotName(spot_id=SPOT_ID, name="Bergstraße"))
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_ride_page_preview.py -v
```

Expected: FAIL, `module 'hitch.blueprints.main' has no attribute '_ride_preview_meta'`.

- [ ] **Step 3: Build the preview values in the route**

In `hitch/blueprints/main.py`, add `SpotName` to the model imports if absent, and add next to `_spot_description` (around line 192):

```python
# Roughly what a messenger card shows before it truncates. Long ride comments are
# common, so trim rather than let the preview run into an ellipsis mid-sentence.
RIDE_COMMENT_PREVIEW_CHARS = 200


def _ride_place_name(spot_id):
    """Display name of the spot a ride started from, or None.

    Prefers the per-spot file, which holds the fully-cascaded name the map itself shows
    (OSM feature, then service area, then fuel, then car-pooling, then geocode). A ride
    logged minutes ago has no such file yet — exactly the ride whose link gets shared —
    so fall back to the cached geocode in spot_name.
    """
    if not spot_id:
        return None
    preview = _spot_preview(spot_id)
    if preview and preview.get("name"):
        return preview["name"]
    row = db.session.get(SpotName, spot_id)
    return row.name if row else None


def _ride_preview_meta(ride, spot_id):
    """(title, description) for a ride's tab title and link preview.

    /ride/<d_tag> is what the success overlay's share card now links to, so a shared
    ride must not unfurl with the generic site blurb. Text only — a per-ride map image
    would need a whole generation pipeline like route_preview.py.
    """
    place = _ride_place_name(spot_id)
    title = f"Hitchhiking ride from {place}" if place else "A hitchhiking ride"
    if ride.get("distance_km"):
        title += f" – {round(ride['distance_km'])} km"

    parts = []
    if ride.get("rating"):
        parts.append(f"Rated {ride['rating']}/5.")
    if ride.get("wait"):
        parts.append(f"Waited {ride['wait']} min.")
    comment = (ride.get("comment") or "").strip()
    if comment:
        if len(comment) > RIDE_COMMENT_PREVIEW_CHARS:
            comment = comment[:RIDE_COMMENT_PREVIEW_CHARS].rstrip() + "…"
        parts.append(comment)
    if not parts:
        parts.append("A hitchhiking ride logged on Hitchwiki Maps.")
    return title, " ".join(parts)
```

At the end of `ride_detail`, before `return render_template(...)`:

```python
    # The share card links here, so the page needs its own preview rather than
    # base.html's site-wide blurb.
    spot_id = spot_id_for(pickup_lat, pickup_lon) if pickup_lat is not None and pickup_lon is not None else None
    og_title, og_description = _ride_preview_meta(ride_view, spot_id)
```

and pass them to `render_template`:

```python
        og_title=og_title,
        og_description=og_description,
```

Make sure `spot_id_for` is imported from `hitch.blueprints.utils.ride_facts` (added in Task 1).

- [ ] **Step 4: Override the blocks in the template**

In `hitch/templates/ride_detail.html`, replace the `{% block title %}` line with:

```jinja
{% block title %}{{ og_title }} | Hitchhiking Map{% endblock %}
{% block og_title %}{{ og_title }}{% endblock %}
{% block og_description %}{{ og_description }}{% endblock %}
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_ride_page_preview.py -v
```

Expected: all PASS.

- [ ] **Step 6: Full suite and lint**

```bash
source .venv/bin/activate && python -m pytest tests/ -v -m "not network" && ruff check && ruff format --check
```

Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add hitch/blueprints/main.py hitch/templates/ride_detail.html tests/test_ride_page_preview.py
git commit -m "feat(rides): give the ride page its own title and link preview"
```

---

### Task 8: Document and deploy

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the docs**

In `CLAUDE.md`, make these edits:

1. In **Ride Creation/Update Flow**, change step 1 to record that the ride is now also written to the local DB immediately, and that `/ride/<d_tag>` and the map work at once; keep the cron steps as the path by which the generated files catch up.
2. In the **Generated JSON Files** section, add `generated_at.json` to the list `show.py` writes, one line: the epoch instant of the DB snapshot the other files were built from, read by `/pending_rides.json` to decide which rides the map is still missing.
3. Next to the `/proposed_spots.json` mention, note `/pending_rides.json` as the other live-from-DB endpoint.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: instant ride visibility"
```

- [ ] **Step 3: Push**

```bash
git status --short   # confirm nothing another agent is working on is staged
git pull --rebase && git push
```

- [ ] **Step 4: Deploy and verify on prod**

`hitch/scripts/show.py` changed, and `hitch/scripts/` is baked into the image, so this needs a rebuild/redeploy for `generated_at.json` to start being written. Until then the endpoint runs on the `rides_index.json` mtime fallback, which is safe. `hitch/templates/` changes (`map.html`, `ride_detail.html`) need `sudo docker restart hitchhiking-map`. `hitch/static/` is live.

Confirm the deploy path with the user before running it, then verify:

```bash
curl -s http://localhost:4242/pending_rides.json | head -c 200
sudo docker exec hitchhiking-map ls -la /app/dist/generated_at.json
```

Expected: a JSON array (usually `[]`), and — after the next `show` cron run on the rebuilt image — the timestamp file exists.

- [ ] **Step 5: Ask the user for the end-to-end check**

Log a real ride and confirm: the success card's share link is `/ride/<d_tag>` and opens the ride page; reloading the map shows the ride at the top of its spot's pane; after the next 10-minute cron the ride is still shown exactly once and the spot's ride count has not double-counted it.

---

## Self-Review

**Spec coverage.** Design Part 1 → Task 2. Part 2 → Tasks 1 and 3. Part 3 → Tasks 4 and 5. Part 4 → Tasks 6 and 7. Spec's "Files touched" table: `post_hitchhiking_ride_to_nostr.py` (T2), `main.py` (T1/T2/T3/T6/T7), `show.py` (T3), `map.js` (T5/T6), `share_card.js` (T6), `ride_detail.html` (T7). The spec's testing section maps to the test files created in Tasks 1, 2, 3, 4, and 7; its deployment notes are Task 8.

**Two corrections to the spec, applied here:** the spec said the dedupe key is "the Nostr event id" — it is the **d tag**, because `show.py:1096` writes `"id": ride["d"]` into the per-spot files. And it did not mention that a pending ride's raw coordinate need not equal the spot anchor `show.py` merges it into; Task 4 adds the 50 m snap that this requires, without which a ride at a known spot would draw a twin marker for ten minutes.

**Type consistency.** `spot_id_for` is used with that name in Tasks 1, 3 (via `ride_map_entry`) and 7. `ride_map_entry` returns the key set `{id, spot_id, lat, lon, dest_lat, dest_lon, rating, wait, distance, comment, hitchhiker_name, submission_time, ride_datetime, arrival_datetime}`, which Task 4's fixtures and Task 5's marker/pane code both consume (`spot_id` snake_case in the payload; `spotId` camelCase only inside the JS plan objects and `marker.options`, matching the existing `map.js` convention). `planPendingMerge` / `mergeSpotRides` / `distanceM` / `SNAP_METRES` are named identically in Tasks 4 and 5. `_store_published_ride` is named identically in Tasks 2, 6 and 7. `hmShareCard.build(ride, dTag)` matches between Task 6's two edits.
