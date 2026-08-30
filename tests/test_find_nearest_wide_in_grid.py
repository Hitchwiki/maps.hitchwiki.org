"""find_nearest_wide_in_grid: the wide-radius spot->feature lookup behind the
distance-labelled "Nearest Hitchwiki article" link (show.py wires it to the
Hitchwiki article grid with a 15 km cap)."""

import numpy as np

from hitch.helpers import find_nearest_wide_in_grid, haversine_np


def make_grid(points):
    """Mimic show.py's build_point_grid: {(round(lat,2), round(lon,2)): [(order, value, lat, lon)]}."""
    grid = {}
    for order, (lat, lon, value) in enumerate(points):
        grid.setdefault((round(lat, 2), round(lon, 2)), []).append((order, value, lat, lon))
    return grid


def test_empty_grid_returns_none():
    assert find_nearest_wide_in_grid(52.0, 13.0, {}, 15.0) is None


def test_finds_article_several_km_away_outside_the_3x3_window():
    # ~11 km north of the spot — many 0.01° cells away, exactly the case
    # find_nearest_in_grid's fixed 3x3 window silently misses.
    grid = make_grid([(52.1, 13.0, "prague")])
    hit = find_nearest_wide_in_grid(52.0, 13.0, grid, 15.0)
    assert hit is not None
    value, km = hit
    assert value == "prague"
    assert 10 < km < 12


def test_respects_the_max_distance_cap():
    grid = make_grid([(52.3, 13.0, "far")])  # ~33 km away
    assert find_nearest_wide_in_grid(52.0, 13.0, grid, 15.0) is None


def test_returns_the_closest_of_several():
    grid = make_grid([(52.1, 13.0, "far"), (52.02, 13.0, "near"), (52.05, 13.0, "mid")])
    value, km = find_nearest_wide_in_grid(52.0, 13.0, grid, 15.0)
    assert value == "near"
    assert km < 3


def test_distance_is_crow_flies_not_road_factored():
    grid = make_grid([(52.1, 13.0, "a")])
    _, km = find_nearest_wide_in_grid(52.0, 13.0, grid, 15.0)
    assert abs(km - float(haversine_np(52.0, 13.0, 52.1, 13.0, factor=1.0))) < 1e-6


def test_high_latitude_longitude_span_widens():
    # At 70°N, 0.01° of longitude is ~0.38 km, so an article 8 km east is ~21
    # cells away in longitude — the cos(lat) term must widen the scan to reach it.
    lat = 70.0
    dlon = 8.0 / (111.0 * float(np.cos(np.radians(lat))))
    grid = make_grid([(lat, 20.0 + dlon, "arctic")])
    hit = find_nearest_wide_in_grid(lat, 20.0, grid, 15.0)
    assert hit is not None and hit[0] == "arctic"
