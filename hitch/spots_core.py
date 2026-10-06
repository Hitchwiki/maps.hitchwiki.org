"""Columnar, destination-free twin of spots.json (#622 slice 2a).

spots.json is ~5.6 MB / ~1 MB gzipped, and every visitor waits for it before a marker
draws. Nearly a quarter of it is `dest_lats`/`dest_lons`, which only the direction
filter and a selected spot's destination lines need. This file carries everything else
as parallel arrays (no repeated keys), so a slow phone can paint markers first.

Row i of every column describes the same spot, in the same order as spots.json.
`flags` is a bitmask of the presence booleans; `latest_ms` is null where the spot has
no dated ride.
"""

FLAG_BITS = {"osm": 1, "cp": 2, "fuel": 4, "wiki": 8, "wikimap": 16}


def build_core(spots_data: list[dict]) -> dict:
    return {
        "n": len(spots_data),
        "flag_bits": FLAG_BITS,
        "lat": [s["lat"] for s in spots_data],
        "lon": [s["lon"] for s in spots_data],
        "rating": [s["rating"] for s in spots_data],
        "review_count": [s["review_count"] for s in spots_data],
        "latest_ms": [s.get("latest_ms") for s in spots_data],
        "flags": [sum(bit for key, bit in FLAG_BITS.items() if s.get(key)) for s in spots_data],
    }
