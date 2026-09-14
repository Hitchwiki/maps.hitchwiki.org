"""All known official stops, including places with no ride contributions yet."""

import json
from functools import lru_cache
from pathlib import Path

from flask import Blueprint, abort, jsonify, redirect

from hitch.helpers import get_dirs
from hitch.models import OsmHitchhikingSpot

official_spots_bp = Blueprint("official_spots", __name__)


@lru_cache(maxsize=1)
def _reviewed_links(dist, stamp, generation_stamp):
    root = Path(dist)
    links = {}
    for spot in json.loads((root / "spots.json").read_text()):
        if not spot.get("osm"):
            continue
        sid = f"{spot['lat']:.5f}_{spot['lon']:.5f}"
        detail = json.loads((root / "rides" / "by-spot" / f"{sid}.json").read_text())
        osm_id = detail["spot"].get("osm_id")
        if osm_id is not None:
            links.setdefault(osm_id, []).append((sid, spot["lat"], spot["lon"]))
    return links


def reviewed_links():
    root = Path(get_dirs()["dist"])
    try:
        generated = root / "generated_at.json"
        return _reviewed_links(
            str(root), (root / "spots.json").stat().st_mtime_ns, generated.stat().st_mtime_ns if generated.exists() else 0
        )
    except (OSError, ValueError, KeyError, TypeError):
        # The registry must remain visible on a fresh install or during regeneration.
        # Exceptions are not cached, so the next request can use completed detail files.
        return {}


def map_spot_id(stop, links):
    candidates = links.get(stop.id, [])
    if candidates:
        # Preserve the map's existing association; never invent reviews for a bench.
        return min(candidates, key=lambda s: ((s[1] - stop.latitude) ** 2 + (s[2] - stop.longitude) ** 2, s[0]))[0]
    return f"{stop.latitude:.5f}_{stop.longitude:.5f}"


@official_spots_bp.route("/official-stops.json")
def official_stops():
    links = reviewed_links()
    markers = []
    for stop in OsmHitchhikingSpot.query.order_by(OsmHitchhikingSpot.id):
        tags = stop.tags or {}
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except ValueError:
                tags = {}
        markers.append(
            {
                "lat": round(stop.latitude, 5),
                "lon": round(stop.longitude, 5),
                "osm": True,
                "osm_id": stop.id,
                "name": tags.get("name") or "",
                "rating": None,
                "review_count": 0,
                "official_unreviewed": True,
                "map_spot_id": map_spot_id(stop, links),
            }
        )
    response = jsonify(markers)
    response.headers["Cache-Control"] = "public, max-age=60"
    return response


@official_spots_bp.route("/official-stop/<int:osm_id>")
def official_stop(osm_id):
    stop = OsmHitchhikingSpot.query.filter_by(id=osm_id).first()
    if stop is None:
        abort(404)
    # Temporary: when a first ride is logged nearby, the representative spot can move.
    return redirect("/spot/" + map_spot_id(stop, reviewed_links()), code=302)
