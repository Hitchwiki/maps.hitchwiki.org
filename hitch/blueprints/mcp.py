"""MCP server exposing hitchhiking routes and spots to AI assistants.

Why this exists
---------------
`/dir/<from>/<to>` is deliberately `noindex` (the coordinate-pair space is the
square of the spot space, so it can never be crawled), which means an assistant
can only recommend our routes if it can *ask* for one. This endpoint is that ask:
a connector pointed at https://maps.hitchwiki.org/mcp plans a real route from
live community data instead of paraphrasing whatever it once crawled.

The two tools
-------------
`search` and `fetch`, and deliberately nothing else — the pattern OpenAI
requires. Outside developer mode ChatGPT *rejects* an MCP server that lacks
them, and Deep Research calls only these two no matter what else is offered.
Both take a single string, which is what lets a client drive this server
knowing nothing about hitchhiking.

    search("Basel to Berlin")  -> [{id, title, url}, ...]   cheap stubs
    fetch("route:47.55811,7.58783__52.51739,13.39513")
                               -> {id, title, text, url, metadata}

Two consequences shape everything below:

* **Ids must round-trip statelessly.** Whatever `search` emits comes back to
  `fetch` later, possibly on another connection; there is no session. So an id
  *contains* its document (`spot:<lat>_<lon>`, `route:<from>__<to>`) rather than
  indexing into server-side state.
* **`url` must be non-empty or the result is not citable** — that is the whole
  point of answering: ChatGPT renders a link chip back to maps.hitchwiki.org.

The search/fetch split also lands exactly on our cheap/expensive boundary, which
is lucky rather than designed: `search` only geocodes and scans spots.json
(~0.3 s), while the ~190 MB, ~3 s routing graph is forked only in `fetch`, and
only if the model actually opens that result.

Transport
---------
Streamable HTTP (MCP 2025-06-18), **stateless**: one JSON-RPC message per POST,
one `application/json` reply. The spec permits a plain JSON response wherever a
server has nothing to stream, which is the case here. That buys the whole
protocol with no new dependency and no asyncio — the official Python SDK is
ASGI/Starlette and this app is WSGI under waitress. Hence also: no
`Mcp-Session-Id`, and `GET /mcp` returns 405, both spec-legal.

Memory
------
The routing graph must not live in the waitress workers — this host has been
OOM-killed before (see CLAUDE.md). `fetch` shells out to
`hitch/scripts/route_query.py` exactly as `/dir/` shells out to `route_preview`.
Because this endpoint is public and unauthenticated, a semaphore caps how many
of those forks can exist at once; without it a burst of tool calls is a trivial
way to OOM the box.
"""

import json
import math
import os
import re
import subprocess
import sys
import threading

import requests
from flask import Blueprint, current_app, jsonify, make_response, request
from werkzeug.utils import safe_join

from hitch.helpers import get_dirs

mcp_bp = Blueprint("mcp", __name__)

# Protocol versions we can speak. We echo back whichever the client asks for when
# we know it, else our newest — the differences across these three don't touch
# anything a read-only tool server does.
LATEST_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

SERVER_INFO = {
    "name": "hitchwiki-maps",
    "title": "Hitchwiki Maps — hitchhiking routes & spots",
    "version": "1.0.0",
}

SITE_URL = "https://maps.hitchwiki.org"
USER_AGENT = "maps.hitchwiki.org MCP server (+https://maps.hitchwiki.org)"

# A cold route costs ~3 s of graph build; a client that gave up long ago should
# not still be holding a fork of it.
ROUTE_TIMEOUT_S = 40

# Hard cap on concurrent routing subprocesses. Each is ~190 MB, so this is the
# difference between a slow endpoint and a dead host. waitress serves this app
# from one process with a thread pool, so a module-level semaphore covers it.
MAX_CONCURRENT_ROUTES = 2
_route_slots = threading.BoundedSemaphore(MAX_CONCURRENT_ROUTES)
ROUTE_SLOT_WAIT_S = 20

# How many alternatives fetch asks for. Fixed rather than caller-controlled:
# there are no typed arguments to carry it, and each extra alternative is
# another Dijkstra pass in an already expensive fork.
ROUTE_ALTERNATIVES = 2
MAX_WALK_KM = 20.0

MAX_SEARCH_RESULTS = 10
# Spots offered alongside a route hit, so the model has citable departure points
# and not just the itinerary document.
ROUTE_QUERY_SPOTS = 3
SPOT_SEARCH_RADIUS_KM = 25.0

POINT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)\s*$")
SPOT_ID_RE = re.compile(r"^(-?\d+\.\d+)_(-?\d+\.\d+)$")
ROUTE_ID_RE = re.compile(r"^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)__(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$")

EARTH_RADIUS_KM = 6371.0


class ToolError(Exception):
    """A failure the model should see and can act on (bad id, timeout)."""


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------
def _haversine_km(lat1, lon1, lat2, lon2):
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


# Settlement types, best first. Photon ranks "Lisbon" the *county* (lat 38.995)
# above "Lisbon" the *city* (lat 38.708) — 32 km apart, and the county centroid
# is farmland with no hitchhiking spot near it, which turned the first leg into
# a 27 km walk. A traveller naming a place means the town, so prefer one.
_SETTLEMENT_PRIORITY = ("city", "town", "village", "municipality", "locality", "hamlet")


def _pick_settlement(features):
    """The candidate a traveller most likely meant, else Photon's own top hit.

    Falls back to features[0] when nothing is a settlement, so searching a
    street, a service area or a region still resolves to what was asked for.
    """

    def rank(item):
        idx, feat = item
        ftype = (feat.get("properties") or {}).get("type")
        priority = _SETTLEMENT_PRIORITY.index(ftype) if ftype in _SETTLEMENT_PRIORITY else len(_SETTLEMENT_PRIORITY)
        return priority, idx  # ties keep Photon's own ordering

    return min(enumerate(features), key=rank)[1]


def _geocode(place):
    """A place name (or 'lat,lon') → (lat, lon, label), or None if unresolvable.

    Returns None rather than raising because the caller uses a failed geocode as
    a *signal*: if one half of "X to Y" doesn't resolve, the query wasn't a route
    query after all and we fall back to a spot search.
    """
    if not place or not place.strip():
        return None

    m = POINT_RE.match(place)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        return lat, lon, f"{lat:.5f}, {lon:.5f}"

    try:
        r = requests.get(
            "https://photon.komoot.io/api",
            # Several candidates, because the top hit is not always the one a
            # traveller means — see _pick_settlement.
            params={"q": place, "limit": 5, "lang": "en"},
            headers={"User-Agent": USER_AGENT},
            timeout=8,
        )
        r.raise_for_status()
        features = r.json().get("features") or []
    except (requests.RequestException, ValueError):
        return None
    if not features:
        return None

    feat = _pick_settlement(features)
    lon, lat = feat["geometry"]["coordinates"][:2]
    props = feat.get("properties", {})
    label = ", ".join(str(props[k]) for k in ("name", "state", "country") if props.get(k)) or place
    return float(lat), float(lon), label


# ---------------------------------------------------------------------------
# Intent parsing
#
# `search` receives free text, so the one genuinely lossy step in this server is
# deciding whether a query means "route from X to Y" or "spots around here".
# ---------------------------------------------------------------------------
# Question scaffolding stripped before looking for a separator, because "how to
# hitchhike out of Berlin" contains " to " and would otherwise split into
# ("how", "hitchhike out of berlin").
_QUESTION_PREFIX_RE = re.compile(
    r"^(?:"
    r"how\s+(?:do\s+i|do\s+you|can\s+i|to)|"
    r"what(?:'|’)?s\s+the\s+best\s+way\s+to|"
    r"what\s+is\s+the\s+best\s+way\s+to|"
    r"best\s+way\s+to|"
    r"where\s+(?:can|should)\s+i"
    r")\s+",
    re.IGNORECASE,
)

# Leading verbs/nouns that carry no place information.
_LEAD_NOISE_RE = re.compile(
    r"^(?:hitchhiking|hitchhike|hitching|hitch|thumb|travel|get|go|going|route|routes|directions|trip)\s+",
    re.IGNORECASE,
)

_TRAIL_NOISE_RE = re.compile(r"\s+(?:by\s+hitchhiking|hitchhiking|by\s+thumb|by\s+car)$", re.IGNORECASE)

# Filler around a bare place name in a spot query.
_SPOT_PREFIX_RE = re.compile(
    r"^(?:"
    r"(?:good\s+|best\s+|the\s+best\s+)?(?:hitchhiking\s+|hitching\s+)?(?:spots?|places?|locations?)\s+"
    r"(?:to\s+hitchhike\s+)?(?:near|around|in|at|out\s+of|from|leaving)|"
    r"(?:hitchhike|hitchhiking|hitching)\s+(?:out\s+of|from|near|around|in)|"
    r"(?:leaving|near|around|in|out\s+of|from)"
    r")\s+",
    re.IGNORECASE,
)

_SEPARATORS = (" to ", " -> ", " --> ", " → ", "→", "->")

# A left-hand side that is one of these means the split found a stray "to", not
# a route (belt and braces alongside the prefix stripping above).
_NOT_A_PLACE = {"how", "what", "where", "when", "why", "who", "way", "best way", "i", "you", "it"}


def _strip_noise(text):
    text = _QUESTION_PREFIX_RE.sub("", text.strip())
    text = _LEAD_NOISE_RE.sub("", text.strip())
    text = _TRAIL_NOISE_RE.sub("", text.strip())
    return text.strip(" ,.?!")


def _split_route_query(query):
    """('Basel', 'Berlin') if the query names two endpoints, else None."""
    text = _strip_noise(query)
    text = re.sub(r"^from\s+", "", text, flags=re.IGNORECASE)

    lowered = text.lower()
    for sep in _SEPARATORS:
        idx = lowered.find(sep)
        if idx == -1:
            continue
        left = text[:idx].strip(" ,.")
        right = text[idx + len(sep) :].strip(" ,.")
        right = re.sub(r"^to\s+", "", right, flags=re.IGNORECASE).strip()
        if not left or not right:
            continue
        if left.lower() in _NOT_A_PLACE:
            continue
        # A place name this long is almost certainly a sentence we mis-split.
        if len(left) > 60 or len(right) > 60:
            continue
        return left, right
    return None


def _place_query(query):
    """The place a non-route query is about ('spots near Berlin' -> 'Berlin')."""
    text = _strip_noise(query)
    text = _SPOT_PREFIX_RE.sub("", text.strip())
    return text.strip(" ,.?!") or query.strip()


# ---------------------------------------------------------------------------
# Spot data (generated files — cheap to read, no DB, no routing graph)
# ---------------------------------------------------------------------------
_spots_cache = {"mtime": None, "rows": None}
_spots_lock = threading.Lock()


def _load_spots():
    """spots.json as compact tuples, reloaded only when show.py rewrites it.

    Tuples rather than the raw dicts because this is ~35k entries living for the
    life of the worker; the dicts cost several times more for fields no tool
    here reads.
    """
    path = os.path.join(get_dirs()["dist"], "spots.json")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    with _spots_lock:
        if _spots_cache["mtime"] == mtime and _spots_cache["rows"] is not None:
            return _spots_cache["rows"]
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return []
    rows = [(s["lat"], s["lon"], s.get("rating"), s.get("review_count", 0)) for s in raw]
    with _spots_lock:
        _spots_cache["mtime"] = mtime
        _spots_cache["rows"] = rows
    return rows


def _spot_id(lat, lon):
    """The map's spot identity — must match generate_spot_id() in show.py."""
    return f"{lat:.5f}_{lon:.5f}"


def _spot_detail(spot_id):
    """The per-spot detail file show.py writes, or None."""
    path = safe_join(get_dirs()["dist"], "rides", "by-spot", f"{spot_id}.json")
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _spot_name(lat, lon):
    """Display name for a spot, falling back to coordinates.

    Reads the already reverse-geocoded name out of the per-spot file rather than
    geocoding live: spot_names.py has done this offline for every spot, and a
    Photon call per leg would make a 7-leg route seven round trips slower.
    """
    detail = _spot_detail(_spot_id(lat, lon))
    name = (detail or {}).get("spot", {}).get("name")
    return name or f"{lat:.5f}, {lon:.5f}"


# Photon's reverse lookup returns the nearest *feature*, which for a city-centre
# coordinate is a street or POI ("Wilsdruffer Straße"). Its `city` field is filled
# in exactly when `name` is that kind of detail, so prefer it — same rule as
# route_preview.place_label.
PLACE_TYPES = {"city", "town", "village", "hamlet", "municipality", "locality", "district", "county", "state"}


def _reverse_label(lat, lon):
    """Human name for a route endpoint, for the document title.

    The title is the string an assistant reads out and cites, so bare
    coordinates there are a real cost. Unlike leg names (one per leg, hence the
    offline `_spot_name`) there are only two per document, so one Photon round
    trip each is affordable inside a fetch that already forks the router.

    Deliberately NO `reverse_geocoder` fallback: it loads ~30 MB into the
    long-lived waitress workers and this host has been OOM-killed before.
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
    return _spot_name(lat, lon)


def _spots_near(lat, lon, radius_km, limit):
    """Nearest spots ranked by evidence → [(km, lat, lon, rating, count)]."""
    rows = _load_spots()
    if not rows:
        return []
    # Degree box first: haversine on 35k spots is wasteful when the radius is a
    # few km, and the box is a cheap superset of the circle.
    dlat = radius_km / 111.0
    dlon = radius_km / max(1e-6, 111.0 * math.cos(math.radians(lat)))
    found = []
    for s_lat, s_lon, rating, count in rows:
        if abs(s_lat - lat) > dlat or abs(s_lon - lon) > dlon:
            continue
        km = _haversine_km(lat, lon, s_lat, s_lon)
        if km <= radius_km:
            found.append((km, s_lat, s_lon, rating, count))
    # Rank by evidence then rating: a 5.0 from one person is worth less than a
    # 4.2 from twenty, and the reader is choosing where to actually stand.
    found.sort(key=lambda r: (-(r[4] or 0), -(r[3] or 0), r[0]))
    return found[:limit]


# ---------------------------------------------------------------------------
# Routing (subprocess + disk cache)
# ---------------------------------------------------------------------------
def _route_cache_path(start, dest):
    key = f"{start[0]:.5f}_{start[1]:.5f}__{dest[0]:.5f}_{dest[1]:.5f}__k{ROUTE_ALTERNATIVES}"
    return safe_join(get_dirs()["dist"], "mcp", f"{key}.json")


def _graph_mtime():
    try:
        return os.path.getmtime(os.path.join(get_dirs()["dist"], "repeatable_routes.json"))
    except OSError:
        return 0.0


def _run_route(start, dest):
    """Itineraries for a coordinate pair, from cache or a routing subprocess.

    Cache entries older than the nightly graph rebuild are ignored rather than
    deleted, so a stale answer is never served after build_ride_routes.py has
    learned new corridors.
    """
    cached = _route_cache_path(start, dest)
    if cached and os.path.isfile(cached):
        try:
            if os.path.getmtime(cached) >= _graph_mtime():
                with open(cached, encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, ValueError):
            pass

    if not _route_slots.acquire(timeout=ROUTE_SLOT_WAIT_S):
        raise ToolError("The routing engine is busy right now. Please retry in a few seconds.")
    try:
        proc = subprocess.run(
            [
                sys.executable,
                os.path.join(get_dirs()["root"], "hitch", "scripts", "route_query.py"),
                "--from",
                f"{start[0]},{start[1]}",
                "--to",
                f"{dest[0]},{dest[1]}",
                "--k",
                str(ROUTE_ALTERNATIVES),
                "--max-walk-km",
                str(MAX_WALK_KM),
            ],
            cwd=get_dirs()["root"],
            capture_output=True,
            timeout=ROUTE_TIMEOUT_S,
            check=True,
        )
        result = json.loads(proc.stdout)
    except subprocess.TimeoutExpired as e:
        raise ToolError("Routing timed out. Please try again.") from e
    except (subprocess.SubprocessError, OSError, ValueError) as e:
        current_app.logger.warning("mcp route failed %s -> %s: %s", start, dest, e)
        raise ToolError("The routing engine failed on this request.") from e
    finally:
        _route_slots.release()

    if cached:
        try:
            os.makedirs(os.path.dirname(cached), exist_ok=True)
            tmp = cached + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(result, f)
            os.replace(tmp, cached)  # never leave a half-written cache entry
        except OSError:
            pass
    return result


# ---------------------------------------------------------------------------
# Document rendering
# ---------------------------------------------------------------------------
def _fmt_time(minutes):
    minutes = int(round(minutes or 0))
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}" if h else f"{m} min"


def _route_doc_id(start, dest):
    return f"route:{start[0]:.5f},{start[1]:.5f}__{dest[0]:.5f},{dest[1]:.5f}"


def _route_url(start, dest):
    return f"{SITE_URL}/dir/{start[0]:.5f},{start[1]:.5f}/{dest[0]:.5f},{dest[1]:.5f}"


def _render_itinerary(itin, start_label, dest_label):
    """One itinerary as prose the model reads verbatim and cites."""
    legs = itin["legs"]
    # The planner's own result card headlines the "core" hitching time: the first
    # and last mile to/from the spots is usually a bus ride, not hitchhiking, and
    # can otherwise dominate a short route's total.
    ends = 0.0
    if legs and legs[0]["mode"] == "walk":
        ends += legs[0]["minutes"]
    if len(legs) > 1 and legs[-1]["mode"] == "walk":
        ends += legs[-1]["minutes"]

    rides = itin["num_car_legs"]
    out = [
        f"About {_fmt_time(itin['total_minutes'] - ends)} of hitchhiking "
        f"({round(itin['car_km']):,} km in {rides} ride{'s' if rides != 1 else ''}), "
        f"including roughly {_fmt_time(itin['wait_minutes'])} of waiting by the road."
    ]
    if itin["walk_km"]:
        out.append(f"Plus about {itin['walk_km']:.1f} km of walking to and from the spots.")

    for i, leg in enumerate(legs, 1):
        frm_name = _spot_name(*leg["from"]) if i > 1 else start_label
        to_name = _spot_name(*leg["to"]) if i < len(legs) else dest_label
        if leg["mode"] == "walk":
            out.append(f"{i}. Walk {leg['km']:.1f} km ({_fmt_time(leg['minutes'])}) from {frm_name} to {to_name}.")
        else:
            via = f" passing {len(leg['via'])} known spot{'s' if len(leg['via']) != 1 else ''}" if leg["via"] else ""
            # Support is the number of logged rides evidencing the weakest
            # segment of this leg; 1 means a single hitchhiker ever reported it.
            evidence = "1 logged ride — weak evidence" if (leg.get("support") or 0) < 2 else f"{leg['support']} logged rides"
            out.append(
                f"{i}. Hitch {leg['km']:.0f} km ({_fmt_time(leg['minutes'])}) from {frm_name} to {to_name}{via}. "
                f"Expect about {_fmt_time(leg['wait_minutes'])} of waiting to get picked up here ({evidence})."
            )
    return out


def _render_route_document(start, dest, start_label, dest_label):
    """The full text of a route document, plus its metadata."""
    result = _run_route(start, dest)
    alts = result.get("itineraries") or []
    title = f"{start_label} → {dest_label} by hitchhiking"
    url = _route_url(start, dest)

    if not alts:
        text = (
            f"No hitchhiking route from {start_label} to {dest_label} could be built from rides "
            "the community has logged.\n\n"
            "This means there is no logged hitchhiking spot within walking distance of one of the "
            "endpoints — not that the trip is impossible, only that it isn't evidenced in this data. "
            f"The interactive planner is at {url} ."
        )
        return title, text, url, {"found": False}

    lines = [f"Hitchhiking route: {start_label} → {dest_label}", ""]
    for itin in alts:
        head = "Fastest option" if itin.get("rank", 0) == 0 else f"Alternative {itin['rank'] + 1}"
        lines.append(f"{head}:")
        lines.extend(_render_itinerary(itin, start_label, dest_label))
        lines.append("")
    lines.append(
        "Estimates come from rides hitchhikers logged on Hitchwiki Maps: travel time assumes 100 km/h "
        "in a car and 5 km/h walking, and each waiting time is the average actually reported at that "
        "spot. They are community averages, not guarantees."
    )
    lines.append(f"Interactive version of this route: {url}")

    best = alts[0]
    meta = {
        "found": True,
        "total_minutes": best["total_minutes"],
        "waiting_minutes": best["wait_minutes"],
        "car_km": best["car_km"],
        "walk_km": best["walk_km"],
        "rides": best["num_car_legs"],
        "min_logged_rides_per_leg": best.get("min_support"),
        "alternatives": len(alts),
    }
    return title, "\n".join(lines), url, meta


def _waited(ride):
    return f"waited {int(ride['wait'])} min" if ride.get("wait") is not None else ""


def _render_spot_document(spot_id):
    detail = _spot_detail(spot_id)
    if not detail:
        raise ToolError(
            f"No hitchhiking spot known with id {spot_id!r}. Ids look like '52.51739_13.39513' and come from a search result."
        )
    info = detail.get("spot", {})
    rides = detail.get("rides", []) or []
    name = info.get("name") or spot_id
    url = f"{SITE_URL}/spot/{spot_id}"
    title = f"{name} — hitchhiking spot"

    lines = [f"Hitchhiking spot: {name}", ""]
    facts = []
    if info.get("wait") is not None:
        facts.append(f"typical wait {int(info['wait'])} minutes")
    if info.get("distance") is not None:
        facts.append(f"average onward ride {round(info['distance'])} km")
    facts.append(f"{len(rides)} logged ride{'s' if len(rides) != 1 else ''}")
    lines.append("; ".join(facts).capitalize() + ".")
    if info.get("hitchwiki_article"):
        lines.append(f"Hitchwiki article: {info['hitchwiki_article']}")

    # Comments are what an assistant can actually turn into advice; a bare rating
    # tells the reader nothing.
    with_comments = [r for r in rides if (r.get("comment") or "").strip()][:8]
    if with_comments:
        lines += ["", "What hitchhikers reported here:"]
        for r in with_comments:
            who = r.get("hitchhiker_name") or "anonymous"
            # Either half can be missing, so build the parenthetical from what is
            # actually there — otherwise an undated ride renders as "(, waited 3 min)".
            parts = [p for p in ((r.get("submission_time") or "")[:10], _waited(r)) if p]
            where = f" ({', '.join(parts)})" if parts else ""
            lines.append(f'- {who}{where}: "{r["comment"].strip()}"')
    lines += ["", f"Spot page: {url}"]

    meta = {
        "typical_wait_minutes": info.get("wait"),
        "average_ride_km": info.get("distance"),
        "logged_rides": len(rides),
    }
    return title, "\n".join(lines), url, meta


def _spot_result(km, lat, lon, rating, count, context=None):
    """One spots-search hit as a {id, title, url} stub."""
    sid = _spot_id(lat, lon)
    detail = _spot_detail(sid) or {}
    info = detail.get("spot", {})
    name = info.get("name") or f"{lat:.5f}, {lon:.5f}"
    bits = []
    if rating:
        bits.append(f"rated {rating:.1f}/5 from {count} ride{'s' if count != 1 else ''}")
    if info.get("wait") is not None:
        bits.append(f"~{int(info['wait'])} min wait")
    where = f" {context}" if context else ""
    detail_txt = f" ({', '.join(bits)})" if bits else ""
    return {
        "id": f"spot:{sid}",
        "title": f"{name} — hitchhiking spot{where}, {km:.0f} km away{detail_txt}",
        "url": f"{SITE_URL}/spot/{sid}",
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
def tool_search(args):
    """Free text → citable document stubs. Never forks the routing graph."""
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ToolError("'query' must be a non-empty string.")

    def spot_stubs(lat, lon, label, limit):
        return [_spot_result(*row, context=f"near {label}") for row in _spots_near(lat, lon, SPOT_SEARCH_RADIUS_KM, limit)]

    place = None
    pair = _split_route_query(query)
    if pair:
        start, dest = _geocode(pair[0]), _geocode(pair[1])
        if start and dest:
            s_lat, s_lon, s_label = start
            d_lat, d_lon, d_label = dest
            route = {
                "id": _route_doc_id((s_lat, s_lon), (d_lat, d_lon)),
                "title": f"{s_label} → {d_label} by hitchhiking — route, times and waits",
                "url": _route_url((s_lat, s_lon), (d_lat, d_lon)),
            }
            # Departure spots ride along so the model has more than one citable
            # source for the same answer.
            return [route] + spot_stubs(s_lat, s_lon, s_label, ROUTE_QUERY_SPOTS)
        # Only one half resolved: either the split found a stray "to", or the
        # user named somewhere we can't place. Answer about the half we *do*
        # know rather than geocoding the whole string, which resolves to nothing.
        place = start or dest

    if place is None:
        place = _geocode(_place_query(query))
    if place is None:
        return []  # empty is a valid answer; the model can rephrase
    return spot_stubs(place[0], place[1], place[2], MAX_SEARCH_RESULTS)


def _parse_document_id(raw):
    """A search id — or a URL the model echoed back — into ('spot'|'route', ...).

    Accepts the bare and URL forms too because models routinely pass back the
    `url` field instead of the `id` field.
    """
    ident = str(raw or "").strip()
    if not ident:
        raise ToolError("'id' must be a non-empty string.")

    if ident.startswith(f"{SITE_URL}/spot/"):
        ident = "spot:" + ident[len(f"{SITE_URL}/spot/") :]
    elif ident.startswith(f"{SITE_URL}/dir/"):
        ident = "route:" + ident[len(f"{SITE_URL}/dir/") :].replace("/", "__")

    if ident.startswith("spot:"):
        body = ident[5:]
    elif ident.startswith("route:"):
        body = ident[6:]
        m = ROUTE_ID_RE.match(body)
        if not m:
            raise ToolError(f"Malformed route id {raw!r}. Expected 'route:<lat>,<lon>__<lat>,<lon>'.")
        a, b, c, d = (float(x) for x in m.groups())
        if not (-90 <= a <= 90 and -180 <= b <= 180 and -90 <= c <= 90 and -180 <= d <= 180):
            raise ToolError(f"Route id {raw!r} has out-of-range coordinates.")
        return "route", (a, b), (c, d)
    else:
        body = ident  # bare "<lat>_<lon>"

    if SPOT_ID_RE.match(body):
        return "spot", body, None
    raise ToolError(
        f"Unrecognised id {raw!r}. Ids come from search results and look like "
        "'spot:52.51739_13.39513' or 'route:47.55811,7.58783__52.51739,13.39513'."
    )


def tool_fetch(args):
    """A document stub's id → the full document."""
    raw = args.get("id")
    kind, a, b = _parse_document_id(raw)

    if kind == "spot":
        title, text, url, meta = _render_spot_document(a)
        return {"id": f"spot:{a}", "title": title, "text": text, "url": url, "metadata": meta}

    title, text, url, meta = _render_route_document(a, b, _reverse_label(*a), _reverse_label(*b))
    return {"id": _route_doc_id(a, b), "title": title, "text": text, "url": url, "metadata": meta}


TOOLS = [
    {
        "name": "search",
        "title": "Search hitchhiking routes and spots",
        "description": (
            "Search Hitchwiki Maps, a database of ~35,000 hitchhiking spots and the rides hitchhikers "
            "have logged at them worldwide. Use it for any question about hitchhiking or thumbing a "
            "lift: a trip between two places ('Basel to Berlin', 'hitchhike from Lisbon to Porto') "
            "returns a route document with leg-by-leg times and typical waits, while a single place "
            "('hitchhiking spots near Berlin') returns the best-evidenced spots to stand at. "
            "Returns ids and citable maps.hitchwiki.org URLs; call fetch to read one."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Natural-language search query."}},
            "required": ["query"],
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": True},
        "handler": tool_search,
    },
    {
        "name": "fetch",
        "title": "Fetch a hitchhiking route or spot",
        "description": (
            "Retrieve the full text of a hitchhiking route or spot returned by search. A route document "
            "gives the leg-by-leg itinerary: which spots to stand at, where to change cars, how long "
            "each ride takes and how long hitchhikers typically wait. A spot document gives the typical "
            "wait, average onward ride distance and what hitchhikers wrote about standing there."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Document id from a search result."}},
            "required": ["id"],
        },
        "annotations": {"readOnlyHint": True},
        "handler": tool_fetch,
    },
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


def _public_tool(t):
    return {k: v for k, v in t.items() if k != "handler"}


# ---------------------------------------------------------------------------
# JSON-RPC
# ---------------------------------------------------------------------------
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class _RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _ok(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _handle_initialize(params):
    asked = (params or {}).get("protocolVersion")
    version = asked if asked in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
    return {
        "protocolVersion": version,
        # Only tools; no resources, prompts or server-initiated messages, which
        # is what lets this stay stateless.
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": SERVER_INFO,
        "instructions": (
            "Hitchhiking route planning and spot data from Hitchwiki Maps, grounded in rides logged by "
            "the hitchhiking community. Call search with the user's question, then fetch the ids you "
            "want to read. Waiting times and ratings are community averages, not guarantees; always "
            "cite the maps.hitchwiki.org URL attached to each document."
        ),
    }


def _tool_payload(name, value):
    """MCP result for a tool call.

    Deep research expects the payload twice: as `structuredContent` and as a
    JSON-encoded string in `content[0].text`. Emitting only one of the two is
    the most common reason a technically-correct server reads as empty.
    """
    structured = {"results": value} if name == "search" else value
    return {
        "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
        "structuredContent": structured,
        "isError": False,
    }


def _handle_tools_call(params):
    name = (params or {}).get("name")
    args = (params or {}).get("arguments") or {}
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        raise _RpcError(INVALID_PARAMS, f"Unknown tool: {name!r}")
    try:
        value = tool["handler"](args)
    except ToolError as e:
        # A tool-level failure is a *result*, not a protocol error: the model is
        # meant to read it and retry with better arguments.
        return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    except (ValueError, TypeError) as e:
        return {"content": [{"type": "text", "text": f"Invalid arguments: {e}"}], "isError": True}
    except Exception:
        current_app.logger.exception("mcp tool %s failed", name)
        return {"content": [{"type": "text", "text": "The tool failed unexpectedly."}], "isError": True}
    return _tool_payload(name, value)


def _dispatch(message):
    """One JSON-RPC message → a response dict, or None for a notification."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "Expected a JSON-RPC 2.0 message.")

    method = message.get("method")
    req_id = message.get("id")
    params = message.get("params")

    # No "id" means a notification: the spec forbids replying to it at all.
    if req_id is None:
        return None

    try:
        if method == "initialize":
            return _ok(req_id, _handle_initialize(params))
        if method == "ping":
            return _ok(req_id, {})
        if method == "tools/list":
            return _ok(req_id, {"tools": [_public_tool(t) for t in TOOLS]})
        if method == "tools/call":
            return _ok(req_id, _handle_tools_call(params))
        return _error(req_id, METHOD_NOT_FOUND, f"Method not found: {method!r}")
    except _RpcError as e:
        return _error(req_id, e.code, e.message)
    except Exception:
        current_app.logger.exception("mcp dispatch failed for %s", method)
        return _error(req_id, INTERNAL_ERROR, "Internal server error.")


def _cors(resp):
    """Public read-only data, so any origin may call it — including browser-based
    MCP clients, which need the protocol header allow-listed to send it."""
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, MCP-Protocol-Version, Authorization"
    resp.headers["Access-Control-Max-Age"] = "86400"
    return resp


@mcp_bp.route("/mcp", methods=["POST", "GET", "OPTIONS"])
def mcp_endpoint():
    if request.method == "OPTIONS":
        return _cors(make_response("", 204))

    if request.method == "GET":
        # Statelessness means we have nothing to push; the spec's answer for a
        # server that doesn't offer the SSE stream is 405.
        return _cors(make_response(jsonify({"error": "This MCP server is stateless; POST JSON-RPC messages instead."}), 405))

    try:
        payload = request.get_json(force=True)
    except Exception:
        return _cors(make_response(jsonify(_error(None, PARSE_ERROR, "Invalid JSON.")), 400))

    # A client may batch messages into an array; a batch of only notifications
    # produces no responses at all, which must be 202 with an empty body.
    if isinstance(payload, list):
        responses = [r for r in (_dispatch(m) for m in payload) if r is not None]
        if not responses:
            return _cors(make_response("", 202))
        return _cors(make_response(jsonify(responses), 200))

    response = _dispatch(payload)
    if response is None:
        return _cors(make_response("", 202))
    return _cors(make_response(jsonify(response), 200))


@mcp_bp.route("/.well-known/mcp.json")
def mcp_discovery():
    """Machine-readable pointer to the endpoint, for clients and directories that
    probe a domain rather than being handed a URL."""
    return _cors(
        make_response(
            jsonify(
                {
                    "name": SERVER_INFO["name"],
                    "title": SERVER_INFO["title"],
                    "description": (
                        "Hitchhiking route planning and spot data from Hitchwiki Maps, "
                        "grounded in rides logged by the hitchhiking community."
                    ),
                    "version": SERVER_INFO["version"],
                    "endpoint": f"{SITE_URL}/mcp",
                    "transport": "streamable-http",
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "authentication": "none",
                    "tools": [{"name": t["name"], "description": t["description"]} for t in TOOLS],
                }
            )
        )
    )
