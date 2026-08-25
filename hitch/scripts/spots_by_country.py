"""Write dist/spots_by_country/<CC>.gpx -- every spot split by country (issue #114).

Till's own words in the issue: "I downloaded the GPX and ended up with 45,000
dots on my map." Splits the existing all-spots dist/spots.gpx (see
spots_gpx.py) into one GPX per country, so a visitor who only cares about
France can download France instead of the whole world.

Standalone script (plain python3, like country_ratings.py), not folded into
show.py's 10-minute cycle: country data changes only when new spots appear,
so re-splitting ~190 countries' worth of GPX (plus .gz compression each)
every 10 minutes would add real, unnecessary I/O to the one cron job this
repo's own CLAUDE.md already flags as runtime-sensitive.

Reads back show.py's own already-written output rather than reusing its
in-memory state (a deliberate downstream, decoupled script, same shape as
country_ratings.py): dist/spots.json for coordinates and
dist/rides/by-spot/<id>.json for the same per-spot waypoint detail show.py's
own _spot_waypoints() builds. Must run after `show` (and after `spot_names`,
so spots have real names rather than bare coordinates) -- same dependency
shape as sync_fuel/why_not_hitchhike.

Country is derived via the offline reverse_geocoder package (no API calls,
no network), the same tool country_ratings.py already uses for rides --
batched in one call so 37k+ lookups are cheap (one KD-tree build, one bulk
query, not one lookup per spot).

Outputs:
  - dist/spots_by_country/<CC>.gpx (+ .gz sidecar) -- one GPX per country,
    same waypoint shape as the full dist/spots.gpx.
  - dist/spots_by_country/index.json -- {cc: {name, spot_count, size_bytes}},
    for a future UI country-picker to read. Country name comes from
    pycountry (already a dependency), not reverse_geocoder (which only
    returns the nearest city's name, not the country's).

Runs daily via cron (see deploy/cron.sh) and can also be triggered by hand:

    flask --app hitch generate spots_by_country   # how cron invokes it
    python hitch/scripts/spots_by_country.py       # standalone, equivalent
"""

import datetime
import json
import os

import pycountry
import reverse_geocoder as rg

from hitch.scripts.spots_gpx import spot_waypoint, write_spots_gpx

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DIST_DIR = os.environ.get("SPOTS_BY_COUNTRY_DIST_DIR", os.path.join(BASE_DIR, "dist"))
SPOTS_JSON = os.path.join(DIST_DIR, "spots.json")
BY_SPOT_DIR = os.path.join(DIST_DIR, "rides", "by-spot")
OUT_DIR = os.path.join(DIST_DIR, "spots_by_country")


def round_coord(value):
    """Matches show.py's round_coord: 5 decimals (~1 m) -- both files must
    agree on this or the derived spot id below drifts from the real one."""
    return round(float(value), 5)


def generate_spot_id(lat, lon):
    """Matches show.py's generate_spot_id byte-for-byte -- the per-spot
    filenames (rides/by-spot/<id>.json) depend on this being identical."""
    return f"{round_coord(lat):.5f}_{round_coord(lon):.5f}"


def country_name(cc):
    country = pycountry.countries.get(alpha_2=cc)
    return country.name if country else cc


def read_spot_detail(spot_id):
    """The same {"spot": ..., "rides": ...} doc show.py wrote for this spot.

    A spot present in the spots.json read at the top of this script but
    missing its per-spot file is a rare race (a spot dropped between the
    two on-disk reads), not a bug worth crashing a whole country's file
    over -- it just gets an empty detail/rides, matching show.py's own
    `spot_details.get(spot_id, {})` fallback.
    """
    try:
        with open(os.path.join(BY_SPOT_DIR, f"{spot_id}.json")) as f:
            doc = json.load(f)
    except FileNotFoundError:
        return {}, []
    return doc.get("spot", {}), doc.get("rides", [])


def country_waypoints(spots):
    for spot in spots:
        spot_id = generate_spot_id(spot["lat"], spot["lon"])
        detail, rides = read_spot_detail(spot_id)
        last_ride = None
        if spot.get("latest_ms"):
            last_ride = datetime.datetime.fromtimestamp(spot["latest_ms"] / 1000, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
        yield spot_waypoint(spot, detail, spot_id, last_ride, rides)


def main():
    with open(SPOTS_JSON) as f:
        spots = json.load(f)

    # Batched, single-call reverse geocode -- the reason country_ratings.py
    # batches its own ~79k ride coordinates in one call rather than looping.
    coords = [(s["lat"], s["lon"]) for s in spots]
    results = rg.search(coords)

    spots_by_cc = {}
    for spot, res in zip(spots, results):
        spots_by_cc.setdefault(res["cc"], []).append(spot)

    os.makedirs(OUT_DIR, exist_ok=True)
    # Clear stale per-country files first: a country that drops to zero
    # spots (no code path guarantees it can't) must not leave a stale,
    # undercounted file sitting next to an index.json that no longer lists it.
    for name in os.listdir(OUT_DIR):
        if name.endswith(".gpx") or name.endswith(".gpx.gz"):
            os.remove(os.path.join(OUT_DIR, name))

    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    index = {}
    for cc, cc_spots in sorted(spots_by_cc.items()):
        path = os.path.join(OUT_DIR, f"{cc}.gpx")
        size = write_spots_gpx(path, country_waypoints(cc_spots), len(cc_spots), generated_at)
        index[cc] = {"name": country_name(cc), "spot_count": len(cc_spots), "size_bytes": size}

    with open(os.path.join(OUT_DIR, "index.json"), "w") as f:
        json.dump(index, f)

    total_spots = sum(v["spot_count"] for v in index.values())
    print(f"Wrote {len(index)} country GPX files ({total_spots} spots) to {OUT_DIR}")


# Run on import too, so `flask --app hitch generate spots_by_country` works
# (the generate command executes scripts by importing them). Also runnable
# directly via `python hitch/scripts/spots_by_country.py`.
main()
