"""dist/spots.gpx — the whole map as waypoints, for the menu's "Download rides" link.

The point of these tests is that a waypoint carries the spot *page*: an offline map app
is the end of the road for this file, so anything the pane shows and the waypoint drops
is simply lost to whoever imported it.
"""

import io
from xml.etree import ElementTree as ET

from hitch.gpx import GPX_NS, HW_NS, GpxStream
from hitch.scripts.spots_gpx import ride_lines, sort_rides, spot_waypoint

GPX = f"{{{GPX_NS}}}"
HW = f"{{{HW_NS}}}"

SPOT = {"lat": 53.5601, "lon": 10.06199, "rating": 4.0, "review_count": 3, "latest_ms": 1_754_000_000_000}
DETAIL = {"name": "Sievekingsallee, Hamburg", "wait": 88, "distance": 428}


def _ride(**overrides):
    ride = {
        "id": "hitchwiki.org-79351f5b",
        "rating": 4,
        "wait": 25,
        "distance": 427.9,
        "comment": "Much better than the Horner Kreisel itself.",
        "hitchhiker_name": "Ewelinalucy",
        "submission_time": "2016-05-20T18:56:38",
        "ride_datetime": None,
        "arrival_datetime": None,
        "no_ride": False,
    }
    ride.update(overrides)
    return ride


def _desc(rides, spot=None, detail=None):
    wpt = spot_waypoint(spot or SPOT, detail or DETAIL, "53.56010_10.06199", "2026-08-01", rides)
    return wpt["desc"]


def test_desc_keeps_the_spot_summary_above_the_rides():
    desc = _desc([_ride()])
    summary, first_ride = desc.split("\n\n", 1)
    assert "Rating: 4.0/5" in summary
    assert "Rides logged: 3" in summary
    assert "Typical wait: 88 min" in summary
    assert "Much better than the Horner Kreisel itself." in first_ride


def test_ride_line_mirrors_the_spot_pane_card():
    # Same facts in the same order as map.js renderRideCards: date, wait, distance,
    # rating, then who.
    head, comment = ride_lines(_ride(ride_datetime="2026-08-01T11:32:00"))
    assert head == "Sat 2026-08-01 11:32 · 25 min wait · 428 km · 4/5 — Ewelinalucy"
    assert comment == "Much better than the Horner Kreisel itself."


def test_weekday_comes_from_the_date_alone():
    # The stamp is already the ride's own local wall-clock time; re-interpreting the
    # offset would move a ride logged near midnight onto the wrong day.
    assert ride_lines(_ride(ride_datetime="2026-08-01T23:50:00+13:00"))[0].startswith("Sat 2026-08-01 23:50")


def test_a_ride_with_no_usable_timestamp_still_lists_its_facts():
    head = ride_lines(_ride(submission_time=None, ride_datetime=None))[0]
    assert head == "25 min wait · 428 km · 4/5 — Ewelinalucy"


def test_missing_stats_are_left_out_rather_than_printed_as_zero():
    head = ride_lines(_ride(wait=None, distance=None, rating=0, hitchhiker_name=None))[0]
    assert head == "Fri 2016-05-20 — Anonymous"


def test_no_ride_is_flagged_like_the_pane_badge():
    assert ride_lines(_ride(no_ride=True))[0].startswith("No ride · ")


def test_photo_urls_are_absolute():
    # The per-spot files store them site-relative, which resolves against nothing once
    # the file has been imported into a map app.
    lines = ride_lines(_ride(images=["/ride-images/2026/08/abc.jpg"]))
    assert lines[-1] == "Photo: https://maps.hitchwiki.org/ride-images/2026/08/abc.jpg"


def test_rides_are_listed_newest_first_like_the_pane():
    old = _ride(comment="older", submission_time="2016-05-20T18:56:38")
    new = _ride(comment="newer", submission_time="2024-09-22T08:17:18")
    assert [r["comment"] for r in sort_rides([old, new])] == ["newer", "older"]
    assert _desc([old, new]).index("newer") < _desc([old, new]).index("older")


def test_a_spot_with_no_rides_is_just_its_summary():
    # Spots whose rides were all low-value keep their marker but have nothing to list;
    # the description must not end in a dangling blank block.
    assert _desc([]) == _desc(None) == _desc([]).strip()


def test_rides_are_not_mirrored_into_extensions():
    # Deliberate: doing so doubled the file for a channel no map app renders, and
    # dist/rides/by-spot/<id>.json already publishes the same rides as structured data.
    wpt = spot_waypoint(SPOT, DETAIL, "53.56010_10.06199", "2026-08-01", [_ride()])
    assert set(wpt["extensions"]["spot"]) == {"rating", "rides", "wait_minutes", "distance_km", "last_ride"}


def test_written_document_parses_and_keeps_the_comment():
    buffer = io.BytesIO()
    with GpxStream(buffer, name="Hitchhiking spots") as stream:
        stream.waypoint(spot_waypoint(SPOT, DETAIL, "53.56010_10.06199", "2026-08-01", [_ride()]))

    root = ET.fromstring(buffer.getvalue())
    wpt = root.find(f"{GPX}wpt")
    assert wpt.get("lat") == "53.5601"
    assert wpt.find(f"{GPX}name").text == "Sievekingsallee, Hamburg"
    assert "Much better than the Horner Kreisel itself." in wpt.find(f"{GPX}desc").text
    assert wpt.find(f"{GPX}link").get("href") == "https://maps.hitchwiki.org/spot/53.56010_10.06199"
    assert wpt.find(f"{GPX}extensions/{HW}spot/{HW}rides").text == "3"
