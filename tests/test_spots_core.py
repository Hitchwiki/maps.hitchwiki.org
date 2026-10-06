import json

from hitch.spots_core import FLAG_BITS, build_core

SPOTS = [
    {
        "lat": 1.0,
        "lon": 2.0,
        "rating": 4.5,
        "review_count": 3,
        "latest_ms": 1000,
        "dest_lats": [5.0],
        "dest_lons": [6.0],
        "osm": True,
        "wiki": True,
    },
    {"lat": 3.0, "lon": 4.0, "rating": 1.0, "review_count": 1},
]


def test_columns_align_with_spots_and_drop_destinations():
    core = build_core(SPOTS)
    assert core["n"] == 2
    for col in ("lat", "lon", "rating", "review_count", "latest_ms", "flags"):
        assert len(core[col]) == 2
    assert "dest_lats" not in core and "dest_lons" not in core
    assert core["lat"] == [1.0, 3.0]
    assert core["latest_ms"] == [1000, None]


def test_flags_bitmask_roundtrip():
    core = build_core(SPOTS)
    assert core["flags"] == [FLAG_BITS["osm"] | FLAG_BITS["wiki"], 0]


def test_smaller_than_legacy():
    many = [dict(SPOTS[0], lat=i / 1000, dest_lats=[1.0, 2.0, 3.0], dest_lons=[1.0, 2.0, 3.0]) for i in range(500)]
    assert len(json.dumps(build_core(many))) < len(json.dumps(many)) / 2
