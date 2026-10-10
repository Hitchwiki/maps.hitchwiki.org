"""#351: coordinate waypoints between a ride's first and last stop shape the drawn route."""

import importlib.util
import os

spec = importlib.util.spec_from_file_location(
    "build_ride_routes", os.path.join(os.path.dirname(__file__), "..", "hitch", "scripts", "build_ride_routes.py")
)
brr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brr)

START, DEST = (52.0, 13.0), (48.0, 11.0)


def stop(lat, lon):
    return {"location": {"latitude": lat, "longitude": lon}}


def test_two_point_key_is_unchanged():
    assert brr._route_key(START, DEST) == "52.0000,13.0000;48.0000,11.0000"
    assert brr._route_key(START, DEST, ()) == brr._route_key(START, DEST)


def test_via_key_orders_points_between_endpoints():
    assert brr._route_key(START, DEST, [(50.0, 12.0)]) == "52.0000,13.0000;50.0000,12.0000;48.0000,11.0000"


def test_via_points_skip_text_only_and_near_duplicates():
    middle = [
        {"location": None},
        {"name": "somewhere"},
        stop(None, None),
        stop(52.0001, 13.0001),  # ~13 m from start
        stop(50.0, 12.0),
        stop(50.0, 12.0),  # same as previous waypoint
        stop(48.0001, 11.0),  # ~11 m from destination
    ]
    assert brr._via_points(middle, START, DEST) == [(50.0, 12.0)]


def test_via_points_are_capped():
    middle = [stop(51.0 - i * 0.1, 12.5) for i in range(20)]
    assert len(brr._via_points(middle, START, DEST)) == brr.MAX_VIA_POINTS
