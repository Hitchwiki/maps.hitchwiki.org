"""Indexable "Hitchhiking from X to Y" pages for well-evidenced city pairs.

Why these exist
---------------
`/dir/<from>/<to>` is permanently `noindex`: the URL space is the square of the
spot space, so a crawler could mint new ones forever (see CLAUDE.md's URL scheme
section). That leaves us with no crawlable page answering "how do I hitchhike
from Berlin to Munich" — the exact question people, and the assistants that
search on their behalf, actually ask.

This generates a *bounded* set of real pages for that question: only city pairs
the routing graph can connect using rides the community actually logged, with
the itinerary, the spots to stand at, typical waits, and quoted rider comments.
Bounded is the whole point — a page per coordinate pair would be the doorway-page
pattern search engines penalise, and the penalty lands on the whole domain.

Selection
---------
  * Candidate cities come from dist/city/top_cities.json, written by cities.py,
    which already spent ~25 min ranking every city by ride volume. Recomputing
    that here would double the nightly cost for an identical answer.
  * Ordered pairs (A->B and B->A are different journeys, and different searches)
    within DISTANCE_BAND_KM: below the floor it isn't a hitchhiking trip, above
    the ceiling the evidence thins out into a chain of weak legs.
  * A pair earns a page only if every leg is corroborated by >= MIN_SUPPORT rides
    and the route passes spots with at least MIN_COMMENTS rider comments between
    them. Comments are what makes the page worth reading rather than a table of
    numbers, and they are what an assistant can quote.
  * The survivors are ranked by evidence and the best MAX_PAGES kept.

Cost
----
The routing graph is built ONCE here (~1.8 s, ~190 MB) and reused for every pair,
unlike the per-request subprocess the web app needs — this is an offline batch on
the same host that has been OOM-killed before, so it must never run in a worker.
At ~290 ms/pair the defaults come to roughly 10-15 min, which is why this is a
nightly cron job and not something a request can trigger.

Run: flask --app hitch generate route_pages
"""

import itertools
import json
import logging
import math
import os
import urllib.parse

from flask import g
from jinja2 import Environment, FileSystemLoader

from hitch.helpers import get_dirs
from hitch.scripts.repeatable_router import load_router
from hitch.translations import SUPPORTED_LANGUAGES, t

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dirs = get_dirs()
dist_dir = dirs["dist"]
SITE_URL = "https://maps.hitchwiki.org"

# How many of the ranked cities to consider. Pairs grow quadratically and each one
# costs a ~290 ms Dijkstra, so this is the main cost dial: 80 cities -> 6,320
# ordered pairs, most of which the distance band drops before routing.
MAX_CITIES = 80
DISTANCE_BAND_KM = (80, 1500)
MAX_PAGES = 300

# Every leg corroborated by at least this many logged rides. 1 means a single
# hitchhiker reported it once, which is not enough to publish as advice.
MIN_SUPPORT = 2
MIN_COMMENTS = 3
# A first/last mile longer than this means the city has no usable spot near it and
# the "route" is really a hike.
MAX_WALK_KM = 25.0

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def _slug(text):
    """URL-safe, lowercase, ASCII-ish slug: "Frankfurt am Main" -> "frankfurt-am-main"."""
    out = []
    for ch in text.lower().strip():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_/":
            out.append("-")
        # Anything else (commas, apostrophes, diacritics we can't fold) is dropped.
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "route"


def _route_loc(from_slug, to_slug):
    return f"{SITE_URL}/route/{urllib.parse.quote(from_slug)}-to-{urllib.parse.quote(to_slug)}.html"


def _spot_id(lat, lon):
    """Must match generate_spot_id() in show.py, or every spot link 404s."""
    return f"{lat:.5f}_{lon:.5f}"


_spot_cache = {}


def _spot_detail(spot_id):
    if spot_id not in _spot_cache:
        path = os.path.join(dist_dir, "rides", "by-spot", f"{spot_id}.json")
        try:
            with open(path, encoding="utf-8") as f:
                _spot_cache[spot_id] = json.load(f)
        except (OSError, ValueError):
            _spot_cache[spot_id] = None
    return _spot_cache[spot_id]


def _spot_name(lat, lon):
    detail = _spot_detail(_spot_id(lat, lon))
    return (detail or {}).get("spot", {}).get("name") or f"{lat:.5f}, {lon:.5f}"


def fmt_time(minutes):
    minutes = int(round(minutes or 0))
    h, m = divmod(minutes, 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def describe_route(itin, start_label, dest_label):
    """Turn one itinerary into the legs, stats and quotes the template renders."""
    legs = itin["legs"]
    # The planner headlines the "core" hitching time: the walk at each end is
    # usually a bus ride, not hitchhiking, and can dominate a short trip.
    ends = 0.0
    if legs and legs[0]["mode"] == "walk":
        ends += legs[0]["minutes"]
    if len(legs) > 1 and legs[-1]["mode"] == "walk":
        ends += legs[-1]["minutes"]

    steps, quotes, seen_spots = [], [], set()
    for i, leg in enumerate(legs):
        is_first, is_last = i == 0, i == len(legs) - 1
        frm = start_label if is_first else _spot_name(*leg["from"])
        to = dest_label if is_last else _spot_name(*leg["to"])
        # spot_names.py often reverse-geocodes a spot to the city it sits in, which
        # otherwise renders as "from Berlin to Berlin". Qualify the *spot* side so
        # the two ends of the leg are distinguishable.
        if frm == to:
            if is_first:
                to = f"a hitchhiking spot near {to}"
            else:
                frm = f"a hitchhiking spot near {frm}"
        # NB: "from" would be unusable in the template — it is a reserved word in
        # both Jinja and Python, so neither step.from nor from=... would compile.
        steps.append(
            {
                "mode": leg["mode"],
                "origin_name": frm,
                "dest_name": to,
                "km": round(leg["km"], 1),
                "minutes": fmt_time(leg["minutes"]),
                "wait": fmt_time(leg["wait_minutes"]) if leg["mode"] == "car" else None,
                "support": leg.get("support"),
                "via_count": len(leg["via"]),
                "spot_id": _spot_id(*leg["from"]) if leg["mode"] == "car" else None,
                # First/last mile. The router costs it at walking pace, but nobody
                # walks 17 km out of Berlin — they take a tram. Saying so is both
                # more useful and more honest than presenting it as a 3.5 h walk.
                "is_edge_walk": leg["mode"] == "walk" and (is_first or is_last),
            }
        )
        # Collect rider comments from the spots this route actually boards at.
        if leg["mode"] != "car":
            continue
        sid = _spot_id(*leg["from"])
        if sid in seen_spots:
            continue
        seen_spots.add(sid)
        detail = _spot_detail(sid) or {}
        for ride in (detail.get("rides") or [])[:20]:
            text = (ride.get("comment") or "").strip()
            if len(text) < 25:
                continue  # one-word notes carry no advice
            quotes.append(
                {
                    "text": text[:400],
                    "who": ride.get("hitchhiker_name") or "Anonymous",
                    "when": (ride.get("submission_time") or "")[:10],
                    "spot": _spot_name(*leg["from"]),
                    "spot_url": f"{SITE_URL}/spot/{sid}",
                }
            )

    car_legs = [leg for leg in legs if leg["mode"] == "car"]
    # Structured data built here rather than in the template: a HowToStep list is
    # awkward to assemble in Jinja, and this is the copy a parser (or an assistant
    # summarising the page) lifts the numbers from, so it should be exact.
    jsonld_steps = [
        {
            "@type": "HowToStep",
            "position": i,
            "name": f"{'Walk' if s['mode'] == 'walk' else 'Hitch'} to {s['dest_name']}",
            "text": (
                f"{'Walk' if s['mode'] == 'walk' else 'Hitch'} {s['km']} km "
                f"({s['minutes']}) from {s['origin_name']} to {s['dest_name']}"
                + (f", after about {s['wait']} of waiting." if s["wait"] else ".")
            ),
        }
        for i, s in enumerate(steps, 1)
    ]
    return {
        "steps": steps,
        "jsonld_steps": jsonld_steps,
        "quotes": quotes[:10],
        "core_minutes": itin["total_minutes"] - ends,
        "core_time": fmt_time(itin["total_minutes"] - ends),
        "wait_time": fmt_time(itin["wait_minutes"]),
        "car_km": round(itin["car_km"]),
        "walk_km": round(itin["walk_km"], 1),
        "rides": itin["num_car_legs"],
        "min_support": min((leg.get("support") or 0) for leg in car_legs) if car_legs else 0,
    }


def main():
    top_path = os.path.join(dist_dir, "city", "top_cities.json")
    try:
        with open(top_path, encoding="utf-8") as f:
            cities = json.load(f)[:MAX_CITIES]
    except (OSError, ValueError):
        logger.warning("No %s yet — run `flask generate cities` first. Skipping route pages.", top_path)
        return

    logger.info("Loading routing graph…")
    router = load_router()
    logger.info("Graph: %d spots, %d corridors", len(router.car_spots), len(router.tree_adj))

    lo, hi = DISTANCE_BAND_KM
    pairs = [
        (a, b) for a, b in itertools.permutations(cities, 2) if lo <= haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) <= hi
    ]
    logger.info("%d city pairs within %d-%d km (from %d cities)", len(pairs), lo, hi, len(cities))

    candidates = []
    for n, (a, b) in enumerate(pairs, 1):
        if n % 500 == 0:
            logger.info("Routing pairs: %d/%d (%d kept)", n, len(pairs), len(candidates))
        alts = router.routes((a["lat"], a["lon"]), (b["lat"], b["lon"]), k=1)
        if not alts:
            continue
        itin = alts[0]
        if itin["walk_km"] > MAX_WALK_KM:
            continue
        info = describe_route(itin, a["city"], b["city"])
        if info["min_support"] < MIN_SUPPORT or len(info["quotes"]) < MIN_COMMENTS:
            continue
        candidates.append((a, b, info))

    # Best-evidenced first: corroboration, then how much riders actually wrote.
    candidates.sort(key=lambda c: (-c[2]["min_support"], -len(c[2]["quotes"]), c[2]["core_minutes"]))
    chosen = candidates[:MAX_PAGES]
    logger.info("%d pairs routable and well-evidenced; publishing %d", len(candidates), len(chosen))

    env = Environment(loader=FileSystemLoader("hitch/templates"))
    env.globals["t"] = t
    env.globals["g"] = g
    env.globals["SUPPORTED_LANGUAGES"] = SUPPORTED_LANGUAGES
    template = env.get_template("route_template.html")

    out_dir = os.path.join(dist_dir, "route")
    os.makedirs(out_dir, exist_ok=True)
    g.lang = "en"

    manifest, listed = [], []
    for a, b, info in chosen:
        from_slug, to_slug = _slug(a["city"]), _slug(b["city"])
        filename = f"{from_slug}-to-{to_slug}.html"
        canonical = _route_loc(from_slug, to_slug)
        planner_url = f"{SITE_URL}/dir/{a['lat']:.5f},{a['lon']:.5f}/{b['lat']:.5f},{b['lon']:.5f}"
        with open(os.path.join(out_dir, filename), "w", encoding="utf-8") as f:
            f.write(
                template.render(
                    origin=a,
                    destination=b,
                    info=info,
                    canonical_url=canonical,
                    planner_url=planner_url,
                    title=f"{a['city']} to {b['city']}",
                )
            )
        manifest.append(canonical)
        listed.append(
            {
                "origin": a["city"],
                "destination": b["city"],
                "filename": filename,
                "core_time": info["core_time"],
                "rides": info["rides"],
            }
        )

    # Index page: without an internal link, a crawler only ever reaches these via
    # the sitemap, and orphaned pages are indexed far less reliably.
    listed.sort(key=lambda r: (r["origin"], r["destination"]))
    grouped = [(origin, list(rs)) for origin, rs in itertools.groupby(listed, key=lambda r: r["origin"])]
    index_template = env.get_template("route_index.html")
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_template.render(grouped=grouped, canonical_url=f"{SITE_URL}/route/index.html"))
    manifest.append(f"{SITE_URL}/route/index.html")

    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    logger.info("Wrote %d route pages + index page + index.json", len(chosen))


main()
