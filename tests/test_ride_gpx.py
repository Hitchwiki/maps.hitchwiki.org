"""GPX export of a user's own rides (/me/rides.gpx) and the shared serialiser."""

import io
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from hitch.blueprints.utils import ride_gpx
from hitch.blueprints.utils.ride_gpx import rides_gpx
from hitch.extensions import db as _db
from hitch.gpx import GPX_NS, HW_NS, GpxStream, build_waypoint, gpx_root, serialize
from hitch.models import RideEvent, User

GPX = f"{{{GPX_NS}}}"
HW = f"{{{HW_NS}}}"


def _ride(with_destination=True, **overrides):
    content = {
        "version": "0.0.0",
        "stops": [
            {
                "location": {"latitude": 53.71988, "longitude": 9.93927},
                "departure_time": "2026-06-12T15:12:00",
                "waiting_duration": "PT90M",
            }
        ],
        "rating": 3,
        "hitchhikers": [{"nickname": "Wanda", "gender": "female"}],
        "comment": "Decent spot for getting north out of Hamburg.",
        "signals": [{"methods": ["thumb", "sign"], "duration": "PT90M"}],
        "mode_of_transportation": {"kind": "car", "license_plate_country": "DE"},
        "occupants": [{"was_driver": True, "gender": "male", "year_of_birth": 1970, "languages": ["de", "en"]}],
        "source": "maps.hitchwiki.org",
        "license": "odbl",
        "submission_time": "2026-07-26T13:12:50",
    }
    if with_destination:
        content["stops"].append({"location": {"latitude": 55.02246, "longitude": 9.36325}, "arrival_time": "2026-06-12T18:30:00"})
    content.update(overrides.pop("content", {}))
    ride = SimpleNamespace(
        id="event-id",
        kind=36820,
        pubkey="a" * 64,
        created_at=1769433170,
        d="maps.hitchwiki.org-abc123",
        content=content,
        rating=content.get("rating"),
        comment=content.get("comment"),
        submission_time=content.get("submission_time"),
        source=content.get("source"),
        license=content.get("license"),
    )
    for key, value in overrides.items():
        setattr(ride, key, value)
    return ride


def _parse(rides, username="Wanda"):
    return ET.fromstring(rides_gpx(rides, username))


@pytest.fixture(autouse=True)
def isolated_dist(tmp_path, monkeypatch):
    """Point the spot-name lookup at an empty dist/, so a real generated file on the
    machine running the tests can't decide what a ride is called."""
    monkeypatch.setattr(ride_gpx, "get_dirs", lambda: {"dist": str(tmp_path)})
    return tmp_path


class TestShape:
    def test_a_ride_with_a_destination_becomes_a_route(self):
        root = _parse([_ride()])
        assert root.findall(f"{GPX}wpt") == []
        (route,) = root.findall(f"{GPX}rte")
        points = route.findall(f"{GPX}rtept")
        assert [(p.get("lat"), p.get("lon")) for p in points] == [
            ("53.71988", "9.93927"),
            ("55.02246", "9.36325"),
        ]

    def test_a_ride_without_a_destination_becomes_a_single_waypoint(self):
        # Inventing an endpoint for a ride that never recorded one would draw a
        # line on the user's map that no car ever drove.
        root = _parse([_ride(with_destination=False)])
        assert root.findall(f"{GPX}rte") == []
        (wpt,) = root.findall(f"{GPX}wpt")
        assert (wpt.get("lat"), wpt.get("lon")) == ("53.71988", "9.93927")

    def test_a_ride_with_no_coordinates_is_skipped_rather_than_written_at_null_island(self):
        root = _parse([_ride(content={"stops": []})])
        assert root.findall(f"{GPX}wpt") == [] and root.findall(f"{GPX}rte") == []

    def test_the_document_is_valid_gpx_1_1_with_metadata(self):
        root = _parse([_ride()])
        assert root.tag == f"{GPX}gpx"
        assert root.get("version") == "1.1"
        metadata = root.find(f"{GPX}metadata")
        assert "Wanda" in metadata.find(f"{GPX}name").text


class TestRideDetail:
    def test_every_fact_reaches_the_readable_description(self):
        desc = _parse([_ride()]).find(f"{GPX}rte").find(f"{GPX}desc").text
        for expected in (
            "Rating: 3/5",
            "Waited: 1 h 30 min",
            "Departed: 2026-06-12T15:12:00",
            "Arrived: 2026-06-12T18:30:00",
            "Signalled with: thumb, sign",
            "Vehicle: car",
            "Licence plate from: DE",
            "Driver: male; born 1970; speaks de, en",
            "Hitchhikers: Wanda",
            "Source: maps.hitchwiki.org",
            "Decent spot for getting north out of Hamburg.",
        ):
            assert expected in desc, expected
        # The distance shown must be the map's road estimate (great-circle x 1.25),
        # so the export doesn't contradict the profile page.
        assert "Distance: 187 km" in desc

    def test_the_whole_ride_record_survives_in_the_extensions(self):
        # This is the promise of the export: a field this app has no UI for is
        # still in the file the user downloads.
        extensions = _parse([_ride()]).find(f"{GPX}rte").find(f"{GPX}extensions")
        ride = extensions.find(f"{HW}ride")
        assert ride.find(f"{HW}version").text == "0.0.0"
        assert ride.find(f"{HW}mode_of_transportation").find(f"{HW}kind").text == "car"
        # A list repeats its element rather than being flattened.
        methods = [m.text for m in ride.find(f"{HW}signals").findall(f"{HW}methods")]
        assert methods == ["thumb", "sign"]
        nostr = extensions.find(f"{HW}nostr")
        assert nostr.find(f"{HW}d").text == "maps.hitchwiki.org-abc123"

    def test_a_give_up_is_labelled_as_one_not_as_missing_data(self):
        ride = _ride(with_destination=False)
        ride.content["no_ride"] = {"reasons": ["too cold"]}
        desc = _parse([ride]).find(f"{GPX}wpt").find(f"{GPX}desc").text
        assert "Gave up here" in desc
        assert "Gave up because: too cold" in desc

    def test_each_ride_links_back_to_its_page(self):
        link = _parse([_ride()]).find(f"{GPX}rte").find(f"{GPX}link")
        assert link.get("href") == "https://maps.hitchwiki.org/ride/maps.hitchwiki.org-abc123"


class TestSpotNames:
    def test_rides_are_titled_with_the_spot_names_the_map_shows(self, isolated_dist):
        by_spot = isolated_dist / "rides" / "by-spot"
        by_spot.mkdir(parents=True)
        (by_spot / "53.71988_9.93927.json").write_text('{"spot": {"name": "Elbtunnel"}, "rides": []}')
        (by_spot / "55.02246_9.36325.json").write_text('{"spot": {"name": "Padborg"}, "rides": []}')

        route = _parse([_ride()]).find(f"{GPX}rte")
        assert route.find(f"{GPX}name").text == "Elbtunnel → Padborg (2026-07-26)"
        assert [p.find(f"{GPX}name").text for p in route.findall(f"{GPX}rtept")] == ["Elbtunnel", "Padborg"]

    def test_an_unnamed_spot_falls_back_rather_than_breaking_the_export(self):
        route = _parse([_ride()]).find(f"{GPX}rte")
        assert route.find(f"{GPX}name").text == "Hitchhiking ride (2026-07-26)"


def _one_waypoint_doc(wpt):
    root = gpx_root()
    root.append(build_waypoint(wpt))
    return ET.fromstring(serialize(root))


class TestSerializer:
    def test_coordinates_never_come_out_in_scientific_notation(self):
        # str(1e-05) is "1e-05", which is not a valid xsd:decimal and reads as 0
        # in several parsers.
        (wpt,) = _one_waypoint_doc({"lat": 0.00001, "lon": -0.000002}).findall(f"{GPX}wpt")
        assert wpt.get("lat") == "0.00001"
        assert wpt.get("lon") == "-0.000002"

    def test_a_coordinate_of_zero_stays_zero_rather_than_an_empty_string(self):
        (wpt,) = _one_waypoint_doc({"lat": 0, "lon": 0}).findall(f"{GPX}wpt")
        assert (wpt.get("lat"), wpt.get("lon")) == ("0", "0")

    def test_a_json_key_that_is_not_a_legal_xml_name_is_sanitised(self):
        parsed = _one_waypoint_doc({"lat": 1, "lon": 2, "extensions": {"ride": {"2 odd:key!": "value"}}})
        (child,) = list(parsed.find(f"{GPX}wpt").find(f"{GPX}extensions").find(f"{HW}ride"))
        assert child.tag == f"{HW}_2_odd_key_"
        assert child.text == "value"

    def test_booleans_are_written_the_way_xsd_spells_them(self):
        parsed = _one_waypoint_doc({"lat": 1, "lon": 2, "extensions": {"ride": {"would_ride_again": False}}})
        assert parsed.find(f"{GPX}wpt").find(f"{GPX}extensions").find(f"{HW}ride").find(f"{HW}would_ride_again").text == "false"

    def test_the_declaration_and_default_namespace_are_what_importers_expect(self):
        body = serialize(gpx_root(name="x"))
        assert body.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')
        assert b'xmlns="http://www.topografix.com/GPX/1/1"' in body


class TestStreaming:
    """The 35k-spot export (show.py) writes waypoints one at a time to keep memory flat."""

    def _stream(self, count, **metadata):
        buffer = io.BytesIO()
        with GpxStream(buffer, **metadata) as stream:
            for i in range(count):
                stream.waypoint({"lat": 50 + i, "lon": 8 + i, "name": f"Spot {i}", "extensions": {"spot": {"rides": i}}})
        return buffer.getvalue()

    def test_a_streamed_document_parses_as_one_well_formed_gpx(self):
        parsed = ET.fromstring(self._stream(3, name="Spots"))
        assert parsed.find(f"{GPX}metadata").find(f"{GPX}name").text == "Spots"
        assert [w.find(f"{GPX}name").text for w in parsed.findall(f"{GPX}wpt")] == ["Spot 0", "Spot 1", "Spot 2"]

    def test_namespaces_are_declared_once_on_the_root_not_on_every_waypoint(self):
        # Re-declaring xmlns on each of 35k waypoints would add megabytes of noise.
        body = self._stream(3)
        assert body.count(b'xmlns="http://www.topografix.com/GPX/1/1"') == 1
        assert body.count(b"xmlns:hw=") == 1
        # The extension elements still resolve into our namespace through the root.
        assert ET.fromstring(body).find(f"{GPX}wpt").find(f"{GPX}extensions").find(f"{HW}spot") is not None

    def test_an_abandoned_document_is_left_unclosed_rather_than_looking_complete(self):
        # A truncated file that ends in </gpx> would be served as if it were whole.
        buffer = io.BytesIO()
        with pytest.raises(RuntimeError), GpxStream(buffer, name="Spots") as stream:
            stream.waypoint({"lat": 1, "lon": 2})
            raise RuntimeError("generation failed halfway")
        assert not buffer.getvalue().rstrip().endswith(b"</gpx>")


@pytest.fixture
def logged_in_user(app, client):
    """Create a user with one logged ride and log them in.

    Login is Hitchwiki OAuth (no local password form to POST), so seed Flask-Login's
    session key directly — the same thing login_user() ultimately does.
    """
    ride = _ride()
    with app.app_context():
        user = User(
            username="Wanda",
            email="wanda@example.com",
            password="x",
            active=True,
            fs_uniquifier="ride-gpx-test-uniquifier",
        )
        event = RideEvent(
            id=ride.id,
            kind=ride.kind,
            pubkey=ride.pubkey,
            sig="s" * 128,
            created_at=ride.created_at,
            d=ride.d,
            content=ride.content,
            stops=ride.content["stops"],
            hitchhikers=ride.content["hitchhikers"],
            rating=ride.rating,
            comment=ride.comment,
            submission_time=ride.submission_time,
            source=ride.source,
            license=ride.license,
        )
        _db.session.add_all([user, event])
        _db.session.commit()
        user_id, event_id = user.id, event.id

    with client.session_transaction() as sess:
        # Flask-Security's UserMixin.get_id() returns fs_uniquifier, not the PK.
        sess["_user_id"] = "ride-gpx-test-uniquifier"
        sess["_fresh"] = True

    yield SimpleNamespace(id=user_id, username="Wanda")

    with app.app_context():
        for model, key in ((User, user_id), (RideEvent, event_id)):
            row = _db.session.get(model, key)
            if row:
                _db.session.delete(row)
        _db.session.commit()


class TestRoutes:
    def test_the_download_page_and_files_require_a_login(self, client):
        # Someone else's ride records are not theirs to export, so there is no
        # /account/<username> counterpart to any of these.
        for path in ("/me/downloads", "/me/rides.gpx", "/me/rides.json"):
            response = client.get(path)
            assert response.status_code == 302
            assert "/login" in response.headers["Location"]

    def test_the_gpx_download_serves_the_users_own_rides(self, client, logged_in_user):
        response = client.get("/me/rides.gpx")
        assert response.status_code == 200
        assert response.mimetype == "application/gpx+xml"
        assert 'filename="hitchwiki-maps-Wanda.gpx"' in response.headers["Content-Disposition"]
        # Private data behind a login must never land in a shared cache.
        assert "no-store" in response.headers["Cache-Control"]
        (route,) = ET.fromstring(response.data).findall(f"{GPX}rte")
        assert len(route.findall(f"{GPX}rtept")) == 2

    def test_the_json_download_serves_the_signed_events_verbatim(self, client, logged_in_user):
        response = client.get("/me/rides.json")
        assert response.status_code == 200
        (event,) = response.get_json()
        # The signature is the point: the export can be verified against Nostr.
        assert event["sig"] == "s" * 128
        assert event["content"]["comment"] == "Decent spot for getting north out of Hamburg."

    def test_the_download_page_counts_routes_and_waypoints_separately(self, client, logged_in_user):
        response = client.get("/me/downloads")
        assert response.status_code == 200
        assert b"Download GPX" in response.data
