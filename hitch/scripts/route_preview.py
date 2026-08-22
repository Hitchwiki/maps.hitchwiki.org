"""Link-preview assets for a shared route URL (/dir/<from>/<to>).

A messenger that unfurls a route link gets an OpenGraph image and a description
naming both endpoints and the hitchhiking time. Both are built here:

    dist/dir/<key>.json   {"start_label", "dest_label", "core_minutes", ...}
    dist/dir/<key>.png    600x315 basemap with the route drawn on it

Run as a subprocess by the /dir/ view on a cache miss, never imported into the
web workers: building the routing graph costs ~2.5 s and ~190 MB, and this host
has been OOM-killed before (see CLAUDE.md). A short-lived process hands that
memory straight back.

    python -m hitch.scripts.route_preview --from 47.55811,7.58783 --to 52.51739,13.39513
"""

import argparse
import json
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image, ImageDraw

from hitch.helpers import get_dirs
from hitch.scripts.repeatable_router import load_router, routes_with_fallback

# OpenGraph's smallest widely-honoured size that still renders as a large card.
# Bigger costs proportionally more tiles per preview for no visible gain.
IMG_W, IMG_H = 600, 315
PADDING = 26  # px kept clear of the route on every side
TILE = 256
MAX_ZOOM = 12  # a whole-continent route never needs more; caps tiles per image

# OSM's tile policy requires an identifying User-Agent and forbids bulk
# downloading. Previews are crawler-rate and every tile is cached on disk
# forever, so a given tile is fetched at most once.
USER_AGENT = "maps.hitchwiki.org link previews (+https://maps.hitchwiki.org)"
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

ROUTE_COLOR = (26, 115, 232)  # #1a73e8, the same blue the planner draws
CASING_COLOR = (255, 255, 255)
START_COLOR = (24, 128, 56)
DEST_COLOR = (217, 52, 43)
LAND_COLOR = (233, 229, 220)  # stand-in when tiles are unavailable


def preview_key(start, dest):
    """Filename stem for a coordinate pair, at the 5 decimals the URL carries."""
    return f"{start[0]:.5f}_{start[1]:.5f}__{dest[0]:.5f}_{dest[1]:.5f}"


def preview_dir():
    return os.path.join(get_dirs()["dist"], "dir")


# ---------------------------------------------------------------------------
# Web mercator
# ---------------------------------------------------------------------------
def project(lat, lon, zoom):
    """(lat, lon) -> absolute pixel coordinates at this zoom."""
    n = TILE * 2**zoom
    x = (lon + 180.0) / 360.0 * n
    lat = max(min(lat, 85.05112878), -85.05112878)
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def fit_zoom(points):
    """Largest zoom at which every point fits inside the padded image."""
    for zoom in range(MAX_ZOOM, 0, -1):
        xs, ys = zip(*(project(lat, lon, zoom) for lat, lon in points))
        if (max(xs) - min(xs)) <= IMG_W - 2 * PADDING and (max(ys) - min(ys)) <= IMG_H - 2 * PADDING:
            return zoom
    return 1


# ---------------------------------------------------------------------------
# Basemap
# ---------------------------------------------------------------------------
def fetch_tile(z, x, y):
    """One tile, from the disk cache or from OSM. None if it can't be had."""
    n = 2**z
    if not (0 <= y < n):
        return None
    x %= n  # wrap the antimeridian rather than 404
    path = os.path.join(get_dirs()["dist"], "tiles", str(z), str(x), f"{y}.png")
    if os.path.isfile(path):
        try:
            img = Image.open(path).convert("RGB")
            # Bump mtime on every hit so cron.sh's age-based prune reads as "last
            # used", not "last fetched" -- a tile a real route reuses stays warm
            # forever; one nobody has asked for since ages out on its own.
            os.utime(path, None)
            return img
        except OSError:
            pass  # truncated cache entry; refetch
    try:
        r = requests.get(TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": USER_AGENT}, timeout=8)
        r.raise_for_status()
    except requests.RequestException:
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(r.content)
    os.replace(tmp, path)  # never leave a half-written tile in the cache
    try:
        return Image.open(path).convert("RGB")
    except OSError:
        return None


def basemap(zoom, origin_x, origin_y):
    """Tiles composited into an IMG_W x IMG_H canvas whose top-left is (origin_x, origin_y)."""
    canvas = Image.new("RGB", (IMG_W, IMG_H), LAND_COLOR)
    x0, y0 = int(origin_x // TILE), int(origin_y // TILE)
    x1, y1 = int((origin_x + IMG_W) // TILE), int((origin_y + IMG_H) // TILE)
    coords = [(tx, ty) for tx in range(x0, x1 + 1) for ty in range(y0, y1 + 1)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        tiles = list(pool.map(lambda c: fetch_tile(zoom, c[0], c[1]), coords))
    for (tx, ty), tile in zip(coords, tiles):
        if tile is not None:
            canvas.paste(tile, (int(tx * TILE - origin_x), int(ty * TILE - origin_y)))
    return canvas


def attribution(draw):
    """OSM's licence requires visible credit wherever their tiles are shown."""
    text = "© OpenStreetMap contributors"
    box = draw.textbbox((0, 0), text)
    w, h = box[2] - box[0], box[3] - box[1]
    x, y = IMG_W - w - 6, IMG_H - h - 5
    draw.rectangle([x - 4, y - 3, IMG_W, IMG_H], fill=(255, 255, 255))
    draw.text((x, y), text, fill=(70, 70, 70))


def pin(draw, xy, color):
    x, y = xy
    draw.ellipse([x - 9, y - 9, x + 9, y + 9], fill=CASING_COLOR)
    draw.ellipse([x - 7, y - 7, x + 7, y + 7], fill=color)
    draw.ellipse([x - 2.5, y - 2.5, x + 2.5, y + 2.5], fill=CASING_COLOR)


def render_png(path, route_points, start, dest):
    points = route_points or [start, dest]
    zoom = fit_zoom(points)
    xs, ys = zip(*(project(lat, lon, zoom) for lat, lon in points))
    origin_x = (max(xs) + min(xs)) / 2 - IMG_W / 2
    origin_y = (max(ys) + min(ys)) / 2 - IMG_H / 2

    img = basemap(zoom, origin_x, origin_y)
    draw = ImageDraw.Draw(img)

    def to_px(pt):
        x, y = project(pt[0], pt[1], zoom)
        return (x - origin_x, y - origin_y)

    line = [to_px(p) for p in points]
    if len(line) > 1:
        draw.line(line, fill=CASING_COLOR, width=7, joint="curve")
        draw.line(line, fill=ROUTE_COLOR, width=4, joint="curve")
    attribution(draw)
    pin(draw, to_px(start), START_COLOR)
    pin(draw, to_px(dest), DEST_COLOR)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    # Map tiles are flat colour, so a 256-colour palette is visually lossless and
    # cuts the file to ~40%. Messengers skip thumbnails they consider too large.
    img.quantize(colors=256, method=Image.MEDIANCUT).save(tmp, "PNG", optimize=True)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------
# Photon's reverse lookup returns the nearest *feature*, which for a city-centre
# coordinate is a street or a POI ("Wilsdruffer Straße", "K+R"). Its `city` field
# is filled in exactly when `name` is that kind of detail, so prefer it; `name` is
# only the right answer when the feature itself is a settlement.
PLACE_TYPES = {"city", "town", "village", "hamlet", "municipality", "locality", "district", "county", "state"}


def place_label(lat, lon):
    """Nearest settlement name, for the "<start> → <dest>" headline.

    Falls back to the offline database (coarser: it names Berlin's centre
    "Mitte") and finally to bare coordinates, so a preview never fails on a
    third-party outage.
    """
    try:
        r = requests.get(
            "https://photon.komoot.io/reverse",
            params={"lat": lat, "lon": lon, "lang": "en", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=6,
        )
        r.raise_for_status()
        props = r.json()["features"][0]["properties"]
        if props.get("type") in PLACE_TYPES and props.get("name"):
            return props["name"]
        for key in ("city", "locality", "district", "county", "state", "country"):
            if props.get(key):
                return props[key]
        if props.get("name"):
            return props["name"]
    except (requests.RequestException, ValueError, KeyError, IndexError):
        pass
    try:
        import reverse_geocoder

        return reverse_geocoder.search([(lat, lon)], verbose=False)[0]["name"]
    except Exception:
        return f"{lat:.3f}, {lon:.3f}"


def fmt_time(minutes):
    minutes = int(round(minutes))
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}" if h else f"{m}m"


def route_facts(start, dest):
    """The fastest itinerary's headline numbers, or None when nothing connects."""
    router = load_router()
    # Same two passes as the planner, or a shared /dir/ link would preview "no
    # route" for a route the page itself goes on to draw.
    alts = routes_with_fallback(router, start, dest, k=1)
    if not alts:
        return None
    itin = alts[0]
    legs = itin["legs"]
    # Headline the "core" hitching time the way the planner's own result card
    # does: the first/last mile to and from the spots is usually a bus ride, not
    # part of the hitchhike, and can otherwise dominate the total.
    ends = 0.0
    if legs and legs[0]["mode"] == "walk":
        ends += legs[0]["minutes"]
    if len(legs) > 1 and legs[-1]["mode"] == "walk":
        ends += legs[-1]["minutes"]

    points = []
    for leg in legs:
        points.append(leg["from"])
        points.extend(leg["via"])
    points.append(legs[-1]["to"])

    return {
        "core_minutes": round(itin["total_minutes"] - ends, 1),
        "total_minutes": itin["total_minutes"],
        "car_km": itin["car_km"],
        "rides": itin["num_car_legs"],
        "points": points,
    }


def describe(facts, start_label, dest_label):
    if not facts:
        return f"Plan a hitchhiking route from {start_label} to {dest_label} on the Hitchhiking Map."
    rides = "ride" if facts["rides"] == 1 else "rides"
    return (
        f"About {fmt_time(facts['core_minutes'])} hitchhiking from {start_label} to {dest_label} — "
        f"{round(facts['car_km']):,} km in roughly {facts['rides']} {rides}, "
        "based on rides the community has logged."
    )


def build(start, dest):
    """Generate (and cache) the preview JSON + PNG for one coordinate pair."""
    key = preview_key(start, dest)
    out_json = os.path.join(preview_dir(), f"{key}.json")
    out_png = os.path.join(preview_dir(), f"{key}.png")

    facts = route_facts(start, dest)
    start_label, dest_label = place_label(*start), place_label(*dest)
    render_png(out_png, facts["points"] if facts else None, start, dest)

    payload = {
        "start_label": start_label,
        "dest_label": dest_label,
        "title": f"{start_label} → {dest_label} by hitchhiking",
        "description": describe(facts, start_label, dest_label),
        "found": bool(facts),
    }
    if facts:
        payload.update(
            {
                "core_minutes": facts["core_minutes"],
                "total_minutes": facts["total_minutes"],
                "car_km": facts["car_km"],
                "rides": facts["rides"],
            }
        )
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    tmp = out_json + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    # The view treats the JSON's existence as "preview ready", so it must appear
    # only after the PNG it describes is on disk.
    os.replace(tmp, out_json)
    return payload


def _parse_latlon(s):
    lat, lon = s.split(",")
    return (float(lat), float(lon))


def main():
    ap = argparse.ArgumentParser(description="Build link-preview assets for a shared route URL.")
    ap.add_argument("--from", dest="start", required=True, type=_parse_latlon, help="lat,lon")
    ap.add_argument("--to", dest="dest", required=True, type=_parse_latlon, help="lat,lon")
    args = ap.parse_args()
    payload = build(args.start, args.dest)
    json.dump(payload, sys.stdout)


if __name__ == "__main__":
    main()
