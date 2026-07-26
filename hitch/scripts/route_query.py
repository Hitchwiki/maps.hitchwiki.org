"""Full hitchhiking itineraries for one coordinate pair, as JSON on stdout.

The subprocess half of the MCP server (hitch/blueprints/mcp.py). Same reason
route_preview.py is a subprocess: building the routing graph costs ~190 MB and
~3 s, which must not be resident in every waitress worker on a host that has
been OOM-killed before (see CLAUDE.md). A short-lived process hands that memory
straight back.

route_preview.py returns only the headline numbers for a link unfurl; the MCP
`fetch` tool, answering "how do I hitchhike from A to B", needs the legs
themselves, so this emits the itineraries whole.

Standalone script (plain python3, stdlib only), like build_ride_routes.py and
spot_names.py — deliberately NOT run as `python -m hitch.scripts.route_query`,
because importing the `hitch` package executes hitch/__init__.py and pulls the
entire Flask app into a process whose whole point is to stay small. It therefore
imports its sibling engine by path rather than as hitch.scripts.repeatable_router.

    python3 hitch/scripts/route_query.py --from 47.55811,7.58783 --to 52.51739,13.39513 --k 2
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from repeatable_router import DEFAULT_MAX_WALK_KM, load_router, routes_with_fallback  # noqa: E402


def query(start, dest, k=2, max_walk_km=DEFAULT_MAX_WALK_KM):
    router = load_router(max_walk_km=max_walk_km)
    # Same two passes as the planner UI (repeatable corridors, then one-off
    # rides), or the MCP answer would contradict what the map itself draws.
    alts = routes_with_fallback(router, start, dest, k=k)
    return {"found": bool(alts), "itineraries": alts}


def _parse_latlon(s):
    lat, lon = s.split(",")
    return (float(lat), float(lon))


def main():
    ap = argparse.ArgumentParser(description="Hitchhiking itineraries as JSON.")
    ap.add_argument("--from", dest="start", required=True, type=_parse_latlon, help="lat,lon")
    ap.add_argument("--to", dest="dest", required=True, type=_parse_latlon, help="lat,lon")
    ap.add_argument("--k", type=int, default=2, help="number of diverse alternatives")
    ap.add_argument("--max-walk-km", type=float, default=DEFAULT_MAX_WALK_KM)
    args = ap.parse_args()
    json.dump(query(args.start, args.dest, k=args.k, max_walk_km=args.max_walk_km), sys.stdout)


if __name__ == "__main__":
    main()
