import contextlib
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime

import pandas as pd
from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_security import current_user
from sqlalchemy import text
from werkzeug.utils import safe_join

from hitch.blueprints.publish_ride import ALLOWED_VEHICLE_KINDS, create_record_from_custom_object
from hitch.blueprints.utils.driver_info_choices import (
    ALLOWED_GENDERS,
    ALLOWED_REASONS_TO_PICK_UP,
    COUNTRY_CHOICES,
    COUNTRY_CODES,
    COUNTRY_NAME_BY_CODE,
    GENDER_CHOICES,
    LANGUAGE_CHOICES,
    LANGUAGE_CODES,
    LANGUAGE_NAME_BY_CODE,
    REASON_DESCRIPTION_BY_CODE,
    REASON_TO_PICK_UP_CHOICES,
)
from hitch.blueprints.utils.iso_country_codes import ISO_3166_1_ALPHA_2
from hitch.blueprints.utils.license_plate_country_codes import LICENSE_PLATE_COUNTRY_CHOICES
from hitch.blueprints.utils.notifications import notify_co_hitchhiker_invite, unread_count
from hitch.blueprints.utils.post_hitchhiking_ride_to_nostr import HitchhikingDataStandardToNostrPoster
from hitch.blueprints.utils.report_ride import OWNER_DELETE_REASON, REPORT_REASONS
from hitch.blueprints.utils.ride_ip_log import get_client_ip, log_ride_ip
from hitch.blueprints.utils.route_request_log import log_route_request
from hitch.blueprints.utils.search_request_log import log_search_request
from hitch.extensions import db
from hitch.helpers import get_db, get_dirs
from hitch.models import CoHitchhiker, Follow, ProposedSpot, RideEvent, RideReport, User

main_bp = Blueprint("main", __name__)

THIS_NOSTR_SOURCE = os.getenv("THIS_NOSTR_SOURCE", "yourdomain.com")
THIS_DATA_LICENSE = os.getenv("THIS_DATA_LICENSE", "odbl")

VEHICLE_KIND_EMOJIS = {
    "car": "\U0001f697",
    "bus": "\U0001f68c",
    "van": "\U0001f690",
    "truck": "\U0001f69a",
    "motorbike": "\U0001f3cd️",
    "scooter": "\U0001f6f5",
    "taxi": "\U0001f695",
    "horse-cart": "\U0001f40e",
    "train": "\U0001f686",
    "camper": "\U0001f3d5️",
    "tractor": "\U0001f69c",
    "plane": "✈️",
    "ferry": "⛴️",
    "boat": "⛵",
}
VEHICLE_KIND_CHOICES = [(k, VEHICLE_KIND_EMOJIS[k]) for k in ALLOWED_VEHICLE_KINDS]


def _user_is_hitchhiker(ride, user):
    """Check if the current user is listed among this ride's hitchhikers, whatever its source."""
    if user.is_anonymous:
        return False

    content = ride.content or {}
    hitchhikers = content.get("hitchhikers", [])
    user_nicknames = [hitchhiker.get("nickname") for hitchhiker in hitchhikers]
    return user.username in user_nicknames


def _user_owns_ride(ride, user):
    """Check if the current user may *edit* this ride.

    Editing republishes the event under this app's Nostr key with the same `d` tag, which
    only replaces the original when we published it in the first place (kind 36820 is
    replaceable per (pubkey, kind, d)). A foreign-source ride is signed by another key, so
    re-publishing would fork it into a second event rather than update it — hence editing
    stays restricted to rides we authored. Deletion has no such constraint, see
    `_user_can_delete_ride`.
    """
    if (ride.content or {}).get("source") != "maps.hitchwiki.org":
        return False
    return _user_is_hitchhiker(ride, user)


def _user_can_delete_ride(ride, user):
    """Check if the current user may hide this ride from the map.

    Deleting only writes a local RideReport row (it never touches the relays), so it works
    for rides imported from other sources too — a hitchhiker who finds their own ride
    logged on hitchwiki.org / hitchmap.com must be able to take it off the map, exactly as
    those rides already show up as theirs on their profile page.
    """
    return _user_is_hitchhiker(ride, user)


# TODO: renamed function from map() to render_map() to avoid conflict with map() builtin
# Index route for the map, supports optional .html ending
# Additionally, there can be map variations: light, with_destination
# TODO: are those routes still needed?
@main_bp.route("/", defaults={"map_variation": None})
@main_bp.route("/<any(light, with_destination):map_variation>")
@main_bp.route("/<any(index, light, with_destination):map_variation>.html")
def render_map(map_variation):
    return render_template(
        "map.html",
        map_variation=map_variation,
        hide_add_spot_button=current_app.config.get("HIDE_ADD_SPOT_BUTTON", False),
        hide_account_button=current_app.config.get("HIDE_ACCOUNT_BUTTON", False),
        is_logged_in=not current_user.is_anonymous,
        username=("" if current_user.is_anonymous else current_user.username),
        unread_notifications=unread_count(current_user),
    )


# Spot ids are generate_spot_id()'s "<lat>_<lon>" with 5 decimals (see show.py).
SPOT_ID_RE = re.compile(r"^-?\d+\.\d{1,7}_-?\d+\.\d{1,7}$")


def _external_https(endpoint, **values):
    """Absolute https URL, for a meta tag that must not carry an http:// URL.

    Plain url_for(_external=True) yields http:// in production (see deploy/run.sh:
    waitress strips the X-Forwarded-Proto that ProxyFix would need). Unfurlers and
    search engines discard an insecure og:image or canonical on an https page, so
    state the scheme rather than inferring it. The OAuth redirect_uri has the same
    problem and solves it separately, in oauth._redirect_uri().
    """
    return url_for(endpoint, _external=True, _scheme="https", **values)


def _spot_preview(spot_id):
    """Link-preview facts for a spot, or None if we have nothing to say about it.

    Read from dist/rides/by-spot/<spot_id>.json — the same per-spot file the map
    lazy-loads on marker click — rather than spots.json, which is multi-MB and
    would be a silly thing to parse on every crawler hit. The file is absent for
    coordinates with no (informative) rides; the map still pans there, so this is
    a missing preview, not a 404.
    """
    path = safe_join(get_dirs()["dist"], "rides", "by-spot", f"{spot_id}.json")
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            payload = json.load(f)
    except (OSError, ValueError):
        return None

    rides = payload.get("rides") or []
    ratings = [r["rating"] for r in rides if r.get("rating")]
    if not ratings:
        return None
    spot = payload.get("spot") or {}
    return {
        "rating": sum(ratings) / len(ratings),
        "count": len(rides),
        "wait": spot.get("wait"),
        "distance": spot.get("distance"),
    }


def _spot_description(preview):
    """One sentence a messenger/crawler can show under the link."""
    plural = "ride" if preview["count"] == 1 else "rides"
    parts = [f"Rated {preview['rating']:.1f}/5 from {preview['count']} {plural}."]
    if preview["wait"]:
        parts.append(f"Typical wait {round(preview['wait'])} min.")
    if preview["distance"]:
        parts.append(f"Rides average {round(preview['distance'])} km.")
    parts.append("See the spot on the hitchhiking map.")
    return " ".join(parts)


# OSM-style permalink for a single spot, mirroring /node/<id>#map=z/lat/lon.
# The spot id lives in the path rather than a #fragment or ?query because
# messengers strip fragments when auto-linking a pasted URL, and because a path
# is the stable, indexable address for the spot. map.js reads it back off
# location.pathname and opens the spot pane; the #map= hash only carries the
# (disposable) viewport. The route renders the same map template as "/" — it
# exists so the URL survives a round trip, and so a pasted link can carry
# per-spot OpenGraph tags instead of the generic homepage ones.
@main_bp.route("/spot/<spot_id>")
def render_spot(spot_id):
    if not SPOT_ID_RE.match(spot_id):
        abort(404)
    lat, lon = (float(v) for v in spot_id.split("_"))
    preview = _spot_preview(spot_id)
    return render_template(
        "map.html",
        map_variation=None,
        spot_title=f"Hitchhiking spot at {lat:.5f}, {lon:.5f}",
        spot_description=_spot_description(preview) if preview else None,
        spot_url=_external_https("main.render_spot", spot_id=spot_id),
        hide_add_spot_button=current_app.config.get("HIDE_ADD_SPOT_BUTTON", False),
        hide_account_button=current_app.config.get("HIDE_ACCOUNT_BUTTON", False),
        is_logged_in=not current_user.is_anonymous,
        unread_notifications=unread_count(current_user),
    )


# A route endpoint in a shared link: "<lat>,<lon>" at the 5 decimals routing.js writes.
DIR_POINT_RE = re.compile(r"^-?\d+\.\d{1,7},-?\d+\.\d{1,7}$")

# How long a request will wait for a cold preview to be built. The routing graph
# takes ~3 s to build, so the first visitor to a route pays for it; messengers
# give an unfurl roughly ten seconds before they give up.
PREVIEW_TIMEOUT_S = 25


def _parse_dir_point(point):
    if not DIR_POINT_RE.match(point):
        abort(404)
    lat, lon = (float(v) for v in point.split(","))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        abort(404)
    return lat, lon


def _route_preview(start, dest, build=True):
    """Cached preview facts for a route, building them on a miss.

    Generation runs in a subprocess (hitch.scripts.route_preview): the routing
    graph costs ~190 MB, which we don't want resident in every waitress worker
    on a host that has been OOM-killed before. A lock file makes it single-
    flight, so a burst of crawler hits on one link can't fork a dozen of them —
    losers of the race fall back to the generic preview rather than queueing.
    """
    key = f"{start[0]:.5f}_{start[1]:.5f}__{dest[0]:.5f}_{dest[1]:.5f}"
    cached = safe_join(get_dirs()["dist"], "dir", f"{key}.json")
    if not cached:
        return key, None
    if os.path.isfile(cached):
        try:
            with open(cached) as f:
                return key, json.load(f)
        except (OSError, ValueError):
            pass
    if not build:
        return key, None

    # The lock lives beside the cache entry, so the directory has to exist before
    # we can take it — on a fresh deploy nothing has written dist/dir/ yet.
    lock = f"{cached}.lock"
    try:
        os.makedirs(os.path.dirname(cached), exist_ok=True)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        # A builder that was killed (this host has been OOM-killed before) leaves
        # its lock behind; without this the route could never be built again.
        try:
            stale = time.time() - os.path.getmtime(lock) > 2 * PREVIEW_TIMEOUT_S
        except OSError:
            stale = False
        if not stale:
            return key, None  # someone else is already building it
        with contextlib.suppress(OSError):
            os.unlink(lock)
        return _route_preview(start, dest, build=True)
    except OSError:
        return key, None
    os.close(fd)
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "hitch.scripts.route_preview",
                "--from",
                f"{start[0]},{start[1]}",
                "--to",
                f"{dest[0]},{dest[1]}",
            ],
            cwd=get_dirs()["root"],
            capture_output=True,
            timeout=PREVIEW_TIMEOUT_S,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as e:
        current_app.logger.warning("route preview failed for %s: %s", key, e)
        return key, None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(lock)
    return _route_preview(start, dest, build=False)


# Shareable route permalink, mirroring /spot/<id>: the endpoints live in the path
# rather than the old #dir/<from>/<to> fragment because a fragment never reaches
# the server, so a pasted route link could never carry its own preview. routing.js
# reads the path back and reopens the planner; the legacy hash is still accepted
# and rewritten to this path.
@main_bp.route("/dir/<start>/<dest>")
def render_directions(start, dest):
    s, d = _parse_dir_point(start), _parse_dir_point(dest)
    _, preview = _route_preview(s, d)
    return render_template(
        "map.html",
        map_variation=None,
        spot_title=preview["title"] if preview else "Hitchhiking route",
        spot_description=preview["description"] if preview else None,
        spot_url=_external_https("main.render_directions", start=start, dest=dest),
        og_image=_external_https("main.render_directions_preview", start=start, dest=dest) if preview else None,
        noindex=True,
        hide_add_spot_button=current_app.config.get("HIDE_ADD_SPOT_BUTTON", False),
        hide_account_button=current_app.config.get("HIDE_ACCOUNT_BUTTON", False),
        is_logged_in=not current_user.is_anonymous,
        unread_notifications=unread_count(current_user),
    )


# Fire-and-forget beacon from routing.js each time the in-app planner runs a
# search. Route planning is entirely client-side, so this is the only place the
# server learns which corridors people ask for. Always returns 204 — the client
# uses navigator.sendBeacon and never reads the response.
@main_bp.route("/log-route-request", methods=["POST"])
def log_route_request_endpoint():
    data = request.get_json(silent=True) or {}
    try:
        slat, slon = float(data["slat"]), float(data["slon"])
        dlat, dlon = float(data["dlat"]), float(data["dlon"])
    except (KeyError, TypeError, ValueError):
        return ("", 204)
    if -90 <= slat <= 90 and -180 <= slon <= 180 and -90 <= dlat <= 90 and -180 <= dlon <= 180:
        log_route_request(slat, slon, dlat, dlon, data.get("sname", ""), data.get("dname", ""))
    return ("", 204)


# Fire-and-forget beacon from map.js each time a place is picked from the search
# bar. The geocoder runs client-side, so this is the only place the server learns
# which places people search for. Always returns 204 (client uses sendBeacon).
@main_bp.route("/log-search-request", methods=["POST"])
def log_search_request_endpoint():
    data = request.get_json(silent=True) or {}
    try:
        lat, lon = float(data["lat"]), float(data["lon"])
    except (KeyError, TypeError, ValueError):
        return ("", 204)
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        log_search_request(data.get("name", ""), lat, lon)
    return ("", 204)


@main_bp.route("/dir/<start>/<dest>/preview.png")
def render_directions_preview(start, dest):
    s, d = _parse_dir_point(start), _parse_dir_point(dest)
    key, preview = _route_preview(s, d)
    if not preview:
        abort(404)
    path = safe_join(get_dirs()["dist"], "dir", f"{key}.png")
    if not path or not os.path.isfile(path):
        abort(404)
    # The image is a pure function of the coordinates, so it never goes stale in
    # a way a crawler would notice; let the CDN and the messenger keep it.
    return send_file(path, mimetype="image/png", max_age=604800)

@main_bp.route("/driver_info_choices.json")
def driver_info_choices_json():
    """Choice lists for the in-ride details sheet — same options as the /ride form,
    delivered as JSON so the client renders them without duplicating the data."""
    from hitch.blueprints.utils.ride_score import WEIGHTS

    return jsonify({
        "reasons": REASON_TO_PICK_UP_CHOICES,
        "genders": GENDER_CHOICES,
        "languages": LANGUAGE_CHOICES,
        "countries": COUNTRY_CHOICES,
        "plate_countries": LICENSE_PLATE_COUNTRY_CHOICES,
        "vehicle_kinds": VEHICLE_KIND_CHOICES,
        "passenger_kinds": WEIGHTS["passenger_kinds"],
    })


def _ride_to_card(ride):
    """Build the card dict the activities/recent template renders for a RideEvent."""
    content = ride.content if ride.content else {}
    stops = content.get("stops") or []
    pickup_lat, pickup_lon = None, None
    if stops:
        coords = stops[0].get("location", {})
        pickup_lat = coords.get("latitude")
        pickup_lon = coords.get("longitude")
    hitchhikers = content.get("hitchhikers") or []
    nickname = hitchhikers[0].get("nickname", "Anonymous") if hitchhikers else "Anonymous"
    return {
        "d_tag": ride.d,
        "created": pd.to_datetime(ride.created_at, unit="s").strftime("%Y-%m-%d %H:%M") if ride.created_at else "N/A",
        "rating": int(ride.rating) if ride.rating else 0,
        "comment": ride.comment or "",
        "pickup_lat": pickup_lat,
        "pickup_lon": pickup_lon,
        "hitchhiker_name": nickname,
    }


def _followed_usernames():
    """Usernames the logged-in user follows (empty for anonymous users)."""
    if current_user.is_anonymous:
        return []
    return [
        row[0]
        for row in db.session.query(User.username)
        .join(Follow, Follow.followed_id == User.id)
        .filter(Follow.follower_id == current_user.id)
        .all()
    ]


def _followed_rides(followed_usernames, limit=10):
    """The most recent rides by the given followed users.

    Rides link to users by hitchhiker nickname (name-based, not a foreign key), so we
    match the followed users' usernames against the nicknames stored in the ride's
    content JSON. A json_each subquery does the filtering in SQL so we only load the
    newest `limit` matching rides instead of scanning every ride in Python.
    """
    if not followed_usernames:
        return []

    placeholders = ",".join(f":n{i}" for i in range(len(followed_usernames)))
    params = {f"n{i}": name for i, name in enumerate(followed_usernames)}
    params["lim"] = limit
    sql = text(
        f"""
        SELECT re.id FROM ride_event re
        WHERE re.submission_time IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM json_each(json_extract(re.content, '$.hitchhikers')) je
            WHERE json_extract(je.value, '$.nickname') IN ({placeholders})
          )
        ORDER BY re.submission_time DESC
        LIMIT :lim
        """
    )
    ids = [r[0] for r in db.session.execute(sql, params).all()]
    if not ids:
        return []
    rides_by_id = {r.id: r for r in db.session.query(RideEvent).filter(RideEvent.id.in_(ids)).all()}
    # Preserve the submission-time ordering from the SQL query.
    return [_ride_to_card(rides_by_id[i]) for i in ids if i in rides_by_id]


def _suggested_hitchhikers(ride_cards, limit=3):
    """Follow suggestions for users who follow nobody yet: the most active hitchhikers
    among the recent ride cards. Only registered users are suggested — they have a
    profile page and can actually be followed (rides by unregistered nicknames can't)."""
    me = None if current_user.is_anonymous else current_user.username
    counts = {}
    for ride in ride_cards:
        name = ride.get("hitchhiker_name")
        # Skip anonymous rides and the viewer themselves (can't follow yourself).
        if not name or name == "Anonymous" or name == me:
            continue
        counts[name] = counts.get(name, 0) + 1
    if not counts:
        return []
    registered = {row[0] for row in db.session.query(User.username).filter(User.username.in_(counts.keys())).all()}
    ranked = sorted(
        ((name, count) for name, count in counts.items() if name in registered),
        key=lambda kv: kv[1],
        reverse=True,
    )[:limit]
    return [{"username": name, "ride_count": count} for name, count in ranked]


@main_bp.route("/recent")
def recent_spots():
    """Activities page: rides from people you follow, then the last 100 added rides."""
    rides = (
        db.session.query(RideEvent)
        .filter(RideEvent.submission_time.isnot(None))
        .order_by(RideEvent.submission_time.desc())
        .limit(100)
        .all()
    )
    ride_list = [_ride_to_card(ride) for ride in rides]

    followed_usernames = _followed_usernames()
    followed_rides = _followed_rides(followed_usernames)
    # When the user follows nobody yet, suggest active hitchhikers to follow instead.
    follow_suggestions = _suggested_hitchhikers(ride_list) if (not current_user.is_anonymous and not followed_usernames) else []
    return render_template(
        "recent.html",
        rides=ride_list,
        followed_rides=followed_rides,
        follow_suggestions=follow_suggestions,
        is_logged_in=not current_user.is_anonymous,
    )


@main_bp.route("/ride/<d_tag>")
def ride_detail(d_tag):
    """Public read-only page showing all details of a single ride."""
    ride = db.session.query(RideEvent).filter_by(d=d_tag).first()
    if not ride:
        abort(404)

    content = ride.content or {}
    stops = content.get("stops") or []
    pickup_lat = pickup_lon = dest_lat = dest_lon = None
    departure_time = None
    arrival_time = None
    waiting_minutes = None
    if stops:
        first = stops[0]
        loc = first.get("location") or {}
        pickup_lat = loc.get("latitude")
        pickup_lon = loc.get("longitude")
        departure_time = first.get("departure_time")
        wd = first.get("waiting_duration")
        if wd:
            m = re.match(r"PT(\d+)M", wd)
            if m:
                waiting_minutes = int(m.group(1))
        if len(stops) > 1:
            last_stop = stops[-1]
            last_loc = last_stop.get("location") or {}
            dest_lat = last_loc.get("latitude")
            dest_lon = last_loc.get("longitude")
            arrival_time = last_stop.get("arrival_time")

    signal_methods = []
    for sig in content.get("signals") or []:
        for method in sig.get("methods") or []:
            if method not in signal_methods:
                signal_methods.append(method)

    hitchhikers = [
        {"nickname": h.get("nickname") or "Anonymous", "gender": h.get("gender")} for h in (content.get("hitchhikers") or [])
    ]

    distance_km = None
    if pickup_lat is not None and dest_lat is not None and pickup_lon is not None and dest_lon is not None:
        # Haversine
        lat1, lon1, lat2, lon2 = map(math.radians, [pickup_lat, pickup_lon, dest_lat, dest_lon])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        distance_km = 2 * 6371 * math.asin(math.sqrt(a))

    submission_dt = ride.submission_time or None

    # Build a presentable "driver" view object from the first occupant flagged as the driver.
    driver = None
    driver_obj = next(
        (o for o in (content.get("occupants") or []) if isinstance(o, dict) and o.get("was_driver")),
        None,
    )
    if driver_obj:
        reasons_raw = driver_obj.get("reasons_to_pick_up") or []
        if isinstance(reasons_raw, str):
            reasons_raw = [reasons_raw]
        languages_raw = driver_obj.get("languages") or []
        country_code = (driver_obj.get("origin_country") or "").upper() or None
        yob = driver_obj.get("year_of_birth")
        age = None
        if yob:
            try:
                age = max(0, datetime.now().year - int(yob))
            except (TypeError, ValueError):
                age = None
        would_ride_again = driver_obj.get("would_ride_again")
        driver = {
            # Tristate: True / False / None (unanswered). Templates must test `is not none`,
            # since an explicit "no" is falsy but still an answer worth showing.
            "would_ride_again": would_ride_again if isinstance(would_ride_again, bool) else None,
            "reasons": [REASON_DESCRIPTION_BY_CODE.get(r, r) for r in reasons_raw],
            "origin_country_code": country_code,
            "origin_country_name": COUNTRY_NAME_BY_CODE.get(country_code) if country_code else None,
            "age": age,
            "gender": driver_obj.get("gender") or None,
            "languages": [LANGUAGE_NAME_BY_CODE.get(c, c) for c in languages_raw],
        }
        # Only attach the driver section if at least one field has a value.
        if not any(
            [
                driver["would_ride_again"] is not None,
                driver["reasons"],
                driver["origin_country_name"],
                driver["age"],
                driver["gender"],
                driver["languages"],
            ]
        ):
            driver = None

    mot = content.get("mode_of_transportation") or {}
    vehicle = None
    if isinstance(mot, dict) and mot.get("kind"):
        kind = mot.get("kind")
        vehicle = {
            "kind": kind,
            "emoji": VEHICLE_KIND_EMOJIS.get(kind, ""),
            "make": mot.get("make"),
            "model": mot.get("model"),
            "license_plate_country": mot.get("license_plate_country"),
            "license_plate_identifier": mot.get("license_plate_identifier"),
        }

    ride_view = {
        "d_tag": d_tag,
        "rating": ride.rating,
        "comment": ride.comment,
        "wait": waiting_minutes,
        "signal_methods": signal_methods,
        "hitchhikers": hitchhikers,
        "pickup_lat": pickup_lat,
        "pickup_lon": pickup_lon,
        "dest_lat": dest_lat,
        "dest_lon": dest_lon,
        "departure_time": departure_time,
        "arrival_time": arrival_time,
        "submission_time": submission_dt,
        "source": content.get("source") or ride.source,
        "distance_km": distance_km,
        "is_owner": _user_owns_ride(ride, current_user),
        "can_delete": _user_can_delete_ride(ride, current_user),
        "vehicle": vehicle,
        "driver": driver,
    }

    # Whether the current user has already reported this ride (drives the button label).
    already_reported = (
        not current_user.is_anonymous
        and RideReport.query.filter_by(ride_d_tag=d_tag, user_id=current_user.id).first() is not None
    )
    # An owner deletion hides the ride from the map, so the owner sees "hidden" state
    # instead of a delete button (the ride page itself stays reachable via its permalink).
    owner_deleted = RideReport.query.filter_by(ride_d_tag=d_tag, reason=OWNER_DELETE_REASON).first() is not None
    return render_template(
        "ride_detail.html",
        ride=ride_view,
        already_reported=already_reported,
        owner_deleted=owner_deleted,
        report_confirmed=request.args.get("reported") == "1",
    )


@main_bp.route("/delete-ride/<d_tag>", methods=["POST"])
def delete_ride(d_tag):
    """Let any of a ride's hitchhikers hide it, including rides imported from other sources.

    The event lives on the Nostr relays and cannot be recalled, so "delete" here means a
    single RideReport row with OWNER_DELETE_REASON, which show.py treats as sufficient to
    drop the ride from every generated map file (no reporter threshold).
    """
    if current_user.is_anonymous:
        return redirect(f"/login?next=/ride/{d_tag}")

    ride = db.session.query(RideEvent).filter_by(d=d_tag).first()
    if not ride:
        abort(404)
    if not _user_can_delete_ride(ride, current_user):
        abort(403)

    # Reports are unique per (ride, user): if the owner had already filed a report, promote
    # it to the deletion reason rather than inserting a second row.
    existing = RideReport.query.filter_by(ride_d_tag=d_tag, user_id=current_user.id).first()
    if existing:
        existing.reason = OWNER_DELETE_REASON
    else:
        db.session.add(RideReport(ride_d_tag=d_tag, user_id=current_user.id, reason=OWNER_DELETE_REASON))
    db.session.commit()
    return redirect(f"/ride/{d_tag}")


@main_bp.route("/report-ride/<d_tag>", methods=["GET", "POST"])
def report_ride(d_tag):
    """Let a logged-in user report a ride for a reason (advertising / non-existing spot).

    Anonymous visitors are sent to the login page. A user can report a given ride only
    once — re-reporting updates their chosen reason rather than adding a second row, so
    one person can never reach the auto-hide threshold (>= 2 reports of the same reason)
    on their own.
    """
    # Only logged-in users may report; bounce anonymous visitors to login and bring them
    # back to this report page afterwards.
    if current_user.is_anonymous:
        return redirect(f"/login?next=/report-ride/{d_tag}")

    ride = db.session.query(RideEvent).filter_by(d=d_tag).first()
    if not ride:
        abort(404)

    existing = RideReport.query.filter_by(ride_d_tag=d_tag, user_id=current_user.id).first()

    if request.method == "POST":
        reason = request.form.get("reason", "")
        if reason not in REPORT_REASONS:
            return render_template(
                "report_ride.html", d_tag=d_tag, reasons=REPORT_REASONS, selected=reason, error="Please choose a reason."
            )
        if existing:
            existing.reason = reason  # one report per (ride, user): update, don't duplicate
        else:
            db.session.add(RideReport(ride_d_tag=d_tag, user_id=current_user.id, reason=reason))
        db.session.commit()
        return redirect(f"/ride/{d_tag}?reported=1")

    return render_template(
        "report_ride.html",
        d_tag=d_tag,
        reasons=REPORT_REASONS,
        selected=existing.reason if existing else None,
        error=None,
    )


@main_bp.route("/ride", methods=["GET", "POST"])
def ride_form():
    """Dedicated ride form page."""
    if request.method == "GET":
        edit_d_tag = request.args.get("edit")
        ride_data = None

        if edit_d_tag:
            # Load existing ride data for editing
            ride = db.session.query(RideEvent).filter_by(d=edit_d_tag).first()
            if ride and ride.content and _user_owns_ride(ride, current_user):
                # Extract data from the ride for pre-filling the form
                content = ride.content
                stops = content.get("stops", [])

                ride_data = {
                    "d_tag": edit_d_tag,  # Store d_tag for POST handler
                    "rating": ride.rating,
                    "comment": ride.comment,
                    # Keep the checkbox ticked when re-editing a no-ride record, otherwise
                    # saving the form again would silently drop the no_ride marker.
                    "no_ride": content.get("no_ride") is not None,
                    "pickup_lat": "",
                    "pickup_lon": "",
                    "destination_lat": "",
                    "destination_lon": "",
                    "wait": "",
                    "signal": [],
                    "datetime_ride": "",
                    "arrival_datetime": "",
                    "co_hitchhiker": "",
                    "vehicle_kind": "",
                    "vehicle_make": "",
                    "vehicle_model": "",
                    "vehicle_license_plate_country": "",
                    "vehicle_license_plate_identifier": "",
                    "driver_would_ride_again": "",
                    "driver_reason_to_pick_up": [],
                    "driver_origin_country": "",
                    "driver_age": "",
                    "driver_gender": "",
                    "driver_languages": [],
                }

                # Driver = the occupant with was_driver=True (first such occupant wins).
                occupants = content.get("occupants") or []
                driver = next((o for o in occupants if isinstance(o, dict) and o.get("was_driver")), None)
                if driver:
                    reasons = driver.get("reasons_to_pick_up") or []
                    # Backwards-compat: model used to allow a single string here.
                    if isinstance(reasons, str):
                        reasons = [reasons]
                    ride_data["driver_reason_to_pick_up"] = [r for r in reasons if r in ALLOWED_REASONS_TO_PICK_UP]
                    # Tristate -> the hidden input's 'yes' / 'no' / '' vocabulary.
                    wra = driver.get("would_ride_again")
                    ride_data["driver_would_ride_again"] = "" if wra is None else ("yes" if wra else "no")
                    ride_data["driver_origin_country"] = (driver.get("origin_country") or "").upper()
                    yob = driver.get("year_of_birth")
                    if yob:
                        ride_data["driver_age"] = max(0, datetime.now().year - int(yob))
                    ride_data["driver_gender"] = driver.get("gender") or ""
                    langs = driver.get("languages") or []
                    ride_data["driver_languages"] = [code for code in langs if code in LANGUAGE_CODES]

                mot = content.get("mode_of_transportation") or {}
                if isinstance(mot, dict):
                    ride_data["vehicle_kind"] = mot.get("kind") or ""
                    ride_data["vehicle_make"] = mot.get("make") or ""
                    ride_data["vehicle_model"] = mot.get("model") or ""
                    ride_data["vehicle_license_plate_country"] = mot.get("license_plate_country") or ""
                    ride_data["vehicle_license_plate_identifier"] = mot.get("license_plate_identifier") or ""

                # Extract coordinates from stops
                if stops:
                    first_stop = stops[0]
                    coords = first_stop.get("location", {})
                    ride_data["pickup_lat"] = coords.get("latitude", "")
                    ride_data["pickup_lon"] = coords.get("longitude", "")

                    # Extract wait from waiting_duration ISO 8601 e.g. "PT30M" -> 30
                    waiting_duration = first_stop.get("waiting_duration")
                    if waiting_duration:
                        match = re.match(r"PT(\d+)M", waiting_duration)
                        if match:
                            ride_data["wait"] = int(match.group(1))

                    # Extract datetime from departure_time e.g. "2024-01-15T14:30:00" -> "2024-01-15T14:30"
                    departure_time = first_stop.get("departure_time")
                    if departure_time:
                        ride_data["datetime_ride"] = departure_time[:16]

                    if len(stops) > 1:
                        last_stop = stops[-1]
                        coords = last_stop.get("location", {})
                        ride_data["destination_lat"] = coords.get("latitude", "")
                        ride_data["destination_lon"] = coords.get("longitude", "")
                        arrival_time = last_stop.get("arrival_time")
                        if arrival_time:
                            ride_data["arrival_datetime"] = arrival_time[:16]

                # Extract signals — flatten methods across all Signal entries
                method_to_form = {"sign": "sign", "thumb": "thumb", "asking": "ask"}
                selected = []
                for sig in content.get("signals", []) or []:
                    for method in sig.get("methods", []) or []:
                        mapped = method_to_form.get(method)
                        if mapped and mapped not in selected:
                            selected.append(mapped)
                ride_data["signal"] = selected

                # Requirement: co-hitchhikers already on a ride cannot be removed when editing,
                # only new ones can be added. "Already present" means either:
                # (a) in the nostr event's hitchhikers list (already accepted, published to Nostr), or
                # (b) in the CoHitchhiker table with accepted="open" (invited, pending response).
                current_nickname = current_user.username if not current_user.is_anonymous else None
                all_hitchhikers = content.get("hitchhikers", [])
                hitchhikers_on_nostr = {
                    h.get("nickname")
                    for h in all_hitchhikers
                    if h.get("nickname") and h.get("nickname") != current_nickname and h.get("nickname") != "Anonymous"
                }
                # Anonymous hitchhikers are always co-hitchhikers (creator must be
                # logged in to edit, so they are never "Anonymous" themselves)
                anon_count = sum(1 for h in all_hitchhikers if h.get("nickname") == "Anonymous")
                pending_invites = {
                    c.co_hitchhiker
                    for c in db.session.query(CoHitchhiker).filter_by(nostr_ride_event_d_tag=edit_d_tag, accepted="open").all()
                }
                locked_co_hitchhikers = sorted(hitchhikers_on_nostr | pending_invites)
                all_co = locked_co_hitchhikers + ["Anonymous"] * anon_count
                ride_data["co_hitchhiker"] = ",".join(all_co)
                ride_data["co_hitchhiker_locked"] = ",".join(locked_co_hitchhikers)

        return render_template(
            "ride_form.html",
            ride_data=ride_data,
            vehicle_kinds=VEHICLE_KIND_CHOICES,
            country_codes=ISO_3166_1_ALPHA_2,
            country_choices=COUNTRY_CHOICES,
            license_plate_country_choices=LICENSE_PLATE_COUNTRY_CHOICES,
            language_choices=LANGUAGE_CHOICES,
            gender_choices=GENDER_CHOICES,
            reason_to_pick_up_choices=REASON_TO_PICK_UP_CHOICES,
        )

    # POST request - process the form submission (same logic as experience route)
    form = request.form
    data = form.to_dict(flat=True)

    # In-ride tracker submits via fetch and must stay on the map, so answer JSON
    # instead of the usual redirect. Detected by the X-Requested-With header.
    wants_json = request.headers.get("X-Requested-With") == "inride"

    try:
        # Signal and reason-to-pick-up arrive as comma-separated codes from the chip widgets.
        data["signal"] = [s.strip() for s in (data.get("signal") or "").split(",") if s.strip()]
        data["driver_reason_to_pick_up"] = [
            r.strip() for r in (data.get("driver_reason_to_pick_up") or "").split(",") if r.strip()
        ]
        # "I did not get a ride here" checkbox — an unchecked box submits no key at all.
        # The in-ride Give Up flow posts no_ride=1 for the same meaning.
        data["no_ride"] = str(data.get("no_ride", "")).strip() not in ("", "0", "false")
        rating = int(data["rate"])
        data["wait"] = int(data["wait"]) if data["wait"] != "" else None
        wait = data["wait"]
        assert wait is None or wait >= 0, f"Wait time must be non-negative, the wait time is {wait}."
        assert rating in range(1, 6), f"Rating must be between 1 and 5, the rating is {rating}."
        comment = None if data["comment"] == "" else data["comment"]
        assert comment is None or len(comment) < 10000, (
            f"Comment must be less than 10000 characters, the comment length is {len(comment)}."
        )

        signals_selected = [s for s in data["signal"] if s and s != "null"]
        for s in signals_selected:
            assert s in ["thumb", "sign", "ask"], f"Signal must be one of thumb, sign, ask - got {s}."
        data["signal"] = signals_selected

        # Driver-info parsing.
        # reason_to_pick_up: validate against the enum allowlist.
        driver_reasons = [r for r in data["driver_reason_to_pick_up"] if r]
        for r in driver_reasons:
            assert r in ALLOWED_REASONS_TO_PICK_UP, f"Invalid reason_to_pick_up: {r}"
        data["driver_reason_to_pick_up"] = driver_reasons

        # would_ride_again: the smiley pair is tristate — 'yes' / 'no' / '' (unanswered).
        # Keep unanswered as None so it stays distinct from an explicit "no".
        wra_raw = (data.get("driver_would_ride_again") or "").strip()
        assert wra_raw in ("", "yes", "no"), f"Invalid would_ride_again: {wra_raw}"
        data["driver_would_ride_again"] = {"yes": True, "no": False}.get(wra_raw)

        # Gender: empty or one of the enum values.
        driver_gender = (data.get("driver_gender") or "").strip()
        assert driver_gender == "" or driver_gender in ALLOWED_GENDERS, f"Invalid driver gender: {driver_gender}"
        data["driver_gender"] = driver_gender

        # Age -> year_of_birth. We translate here so publish_ride doesn't need the current date.
        driver_age_raw = (data.get("driver_age") or "").strip()
        if driver_age_raw:
            driver_age = int(driver_age_raw)
            assert 0 <= driver_age <= 120, f"Driver age out of range: {driver_age}"
            data["driver_year_of_birth"] = datetime.now().year - driver_age
        else:
            data["driver_year_of_birth"] = None

        # Origin country: arrives as ISO alpha-2 code (the country picker stores codes).
        driver_country = (data.get("driver_origin_country") or "").strip().upper()
        assert driver_country == "" or driver_country in COUNTRY_CODES, f"Invalid driver origin country: {driver_country}"
        data["driver_origin_country"] = driver_country

        # Languages: comma-separated ISO 639-3 codes from the chip input.
        driver_lang_raw = (data.get("driver_languages") or "").strip()
        driver_languages = [code for code in (c.strip() for c in driver_lang_raw.split(",")) if code]
        for code in driver_languages:
            assert code in LANGUAGE_CODES, f"Invalid language code: {code}"
        data["driver_languages"] = driver_languages

        # Validate vehicle fields: kind must be one of the allowed enum values (or empty),
        # license_plate_country must be a valid ISO 3166-1 alpha-2 code (or empty). Other
        # vehicle fields are free text and length-capped to avoid abuse.
        vehicle_kind = (data.get("vehicle_kind") or "").strip()
        assert vehicle_kind == "" or vehicle_kind in ALLOWED_VEHICLE_KINDS, f"Invalid vehicle kind: {vehicle_kind}"
        vehicle_country = (data.get("vehicle_license_plate_country") or "").strip().upper()
        assert vehicle_country == "" or vehicle_country in ISO_3166_1_ALPHA_2, f"Invalid license plate country: {vehicle_country}"
        data["vehicle_license_plate_country"] = vehicle_country
        for free_field in ("vehicle_make", "vehicle_model", "vehicle_license_plate_identifier"):
            val = (data.get(free_field) or "").strip()
            assert len(val) <= 255, f"{free_field} must be <= 255 characters"
            data[free_field] = val

        # Arrival must be strictly after pickup time when both are provided so the
        # Nostr stops timeline is monotonic.
        departure_str = (data.get("datetime_ride") or "").strip()
        arrival_str = (data.get("arrival_datetime") or "").strip()
        if departure_str and arrival_str:
            assert datetime.fromisoformat(arrival_str) > datetime.fromisoformat(departure_str), (
                "Arrival time must be later than the pickup time."
            )
        data["datetime_ride"] = departure_str
        data["arrival_datetime"] = arrival_str

        # Get coordinates from individual form fields
        lat = float(data["pickup_lat"]) if data["pickup_lat"] else None
        lon = float(data["pickup_lon"]) if data["pickup_lon"] else None
        dest_lat = float(data["destination_lat"]) if data["destination_lat"] else None
        dest_lon = float(data["destination_lon"]) if data["destination_lon"] else None

        # Convert empty destination coordinates to NaN for compatibility
        if dest_lat is None:
            dest_lat = float("nan")
        if dest_lon is None:
            dest_lon = float("nan")

        assert lat is not None and -90 <= lat <= 90, f"Invalid pickup latitude: {lat}"
        assert lon is not None and -180 <= lon <= 180, f"Invalid pickup longitude: {lon}"
        assert (-90 <= dest_lat <= 90 and -180 <= dest_lon <= 180) or (math.isnan(dest_lat) and math.isnan(dest_lon)), (
            f"Invalid destination coordinates: {dest_lat}, {dest_lon}"
        )

        # ride_row = {
        #     "rating": rating,
        #     "wait": wait,
        #     "comment": comment,
        #     "nickname": None,
        #     "datetime": now,
        #     "ip": ip,
        #     "reviewed": False,
        #     "banned": False,
        #     "lat": lat,
        #     "dest_lat": dest_lat,
        #     "lon": lon,
        #     "dest_lon": dest_lon,
        #     "country": country,
        #     "signal": signal,
        #     "ride_datetime": datetime_ride,
        #     "user_id": current_user.id if not current_user.is_anonymous else None,
        # }

        ### Check if this is an edit operation
        edit_d_tag = data.get("edit_d_tag", "").strip()
        if edit_d_tag:
            existing_ride = db.session.query(RideEvent).filter_by(d=edit_d_tag).first()
            # Inride requests use fetch (no navigation), so return JSON instead of redirecting.
            if not existing_ride or not _user_owns_ride(existing_ride, current_user):
                if wants_json:
                    return jsonify({"ok": False, "error": "unauthorized"}), 400
                return redirect("/#error")  # User doesn't own this ride

            # Create new record with updated form data to get updated fields
            # TODO: define license properly instead of using "xxx"
            updated_record = create_record_from_custom_object(
                custom_object=data, source=THIS_NOSTR_SOURCE, license=THIS_DATA_LICENSE
            )

            # post the updated event (maintaining all original tags including d tag)
            poster = HitchhikingDataStandardToNostrPoster()
            _ = poster.post(ride_record=updated_record, tags=existing_ride.tags)
            poster.close()
            d_tag = edit_d_tag  # Keep the same d_tag
        else:
            # This is a new ride - normal flow
            # TODO: define license properly instead of using "xxx"
            record = create_record_from_custom_object(custom_object=data, source=THIS_NOSTR_SOURCE, license=THIS_DATA_LICENSE)

            poster = HitchhikingDataStandardToNostrPoster()
            # Offline outbox retries carry a stable client-supplied d_tag so a resend
            # replaces the same event instead of creating a duplicate ride.
            client_d_tag = (data.get("client_d_tag") or "").strip() or None
            d_tag = poster.post(ride_record=record, d_tag=client_d_tag)
            poster.close()

        # Abuse trail: pair the saved ride's d tag with the submitter's IP so a flood of
        # fake rides can be traced back to one source. Edits are logged too, since an
        # abuser can also vandalise a ride they own by editing it.
        log_ride_ip(d_tag)

        ### Co-hitchhikers
        # Requirement: co-hitchhikers already on a ride cannot be removed when editing, only new
        # ones can be added. We achieve this by only inserting co-hitchhikers not already in the DB.
        if "co_hitchhiker" in data and data["co_hitchhiker"] != "":
            current_username = current_user.username if not current_user.is_anonymous else None
            existing_co = {c.co_hitchhiker for c in db.session.query(CoHitchhiker).filter_by(nostr_ride_event_d_tag=d_tag).all()}
            invited_user_ids = []
            for ch in data["co_hitchhiker"].split(","):
                username = ch.strip()
                if username == "" or username == "Anonymous":
                    continue  # anonymous hitchhikers are handled in the Nostr event, not in CoHitchhiker
                if username == current_username:
                    continue  # skip self
                if username in existing_co:
                    continue  # already present, cannot be removed so no need to re-add
                invited_user = User.query.filter_by(username=username).first()
                if not invited_user:
                    continue  # skip non-existent users
                co_hitchhiker = CoHitchhiker(
                    nostr_ride_event_d_tag=d_tag,
                    co_hitchhiker=username,
                    accepted="open",
                )
                db.session.add(co_hitchhiker)
                invited_user_ids.append(invited_user.id)
            db.session.commit()
            # Notify newly invited co-hitchhikers (after commit, so the pending invite exists
            # by the time they open their profile to accept/reject it).
            inviter_name = current_username or "Someone"
            for uid in invited_user_ids:
                notify_co_hitchhiker_invite(uid, inviter_name)

        if wants_json:
            return jsonify({"ok": True, "d_tag": d_tag}), 200
        return redirect("/#success")

    except (AssertionError, ValueError, KeyError) as err:
        # Bad input — permanent. 400 with no `transient` flag; the offline outbox flags it
        # for manual retry/discard rather than looping on it forever.
        if wants_json:
            return jsonify({"ok": False, "error": str(err)}), 400
        raise
    except Exception as err:
        # Anything else during publish (relay unreachable, timeout, signing hiccup) is
        # transient — tell the JSON client to keep the item queued and retry later, so a
        # dead relay never looks like a validation error (which would wrongly flag it).
        if wants_json:
            return jsonify({"ok": False, "error": str(err), "transient": True}), 503
        raise


# Report duplicates
@main_bp.route("/report-duplicate", methods=["POST"])
def report_duplicate():
    data = request.form

    now = str(datetime.datetime.utcnow())

    ip = get_client_ip()

    from_lat, from_lon, to_lat, to_lon = map(float, data["report"].split(","))

    df = pd.DataFrame(
        [
            {
                "datetime": now,
                "ip": ip,
                "reviewed": False,
                "accepted": False,
                "from_lat": from_lat,
                "to_lat": to_lat,
                "from_lon": from_lon,
                "to_lon": to_lon,
            }
        ]
    )

    df.to_sql("duplicates", get_db(), index=None, if_exists="append")

    return redirect("/#success-duplicate")


# Max length of a proposed-spot comment. Kept short: the note is a one-line hint
# ("good sign spot on the on-ramp"), not a ride report. Enforced server-side so a
# crafted request can't store an unbounded blob; the textarea also caps it client-side.
PROPOSED_SPOT_COMMENT_MAX = 500


@main_bp.route("/propose-spot", methods=["POST"])
def propose_spot():
    """Store a user-proposed hitchhiking spot (blue marker), NOT published to Nostr.

    Reached from the map's long-press "Propose a spot" action. Anonymous proposals are
    allowed; when logged in we record the user id + username so the marker can credit them.
    """
    data = request.form

    # Reject anything that isn't a real coordinate rather than storing a NaN/None row
    # that would later break the map's marker rendering.
    try:
        lat = float(data.get("lat", ""))
        lon = float(data.get("lon", ""))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid coordinates"}), 400
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return jsonify({"ok": False, "error": "coordinates out of range"}), 400

    comment = (data.get("comment") or "").strip()[:PROPOSED_SPOT_COMMENT_MAX]

    spot = ProposedSpot(
        latitude=lat,
        longitude=lon,
        comment=comment or None,
        user_id=None if current_user.is_anonymous else current_user.id,
        username=None if current_user.is_anonymous else current_user.username,
        ip=get_client_ip(),
    )
    db.session.add(spot)
    db.session.commit()

    return jsonify({"ok": True, "id": spot.id})


@main_bp.route("/proposed_spots.json")
def proposed_spots_json():
    """Live list of user-proposed spots for the map's blue markers.

    Served straight from the DB (not a generated dist/ file) so a spot proposed seconds
    ago is already visible on the next map load, without waiting on a show.py cron pass.
    """
    spots = ProposedSpot.query.order_by(ProposedSpot.id.desc()).all()
    return jsonify(
        [
            {
                "id": s.id,
                "lat": round(s.latitude, 5),
                "lon": round(s.longitude, 5),
                "comment": s.comment or "",
                "user": s.username or "",
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in spots
        ]
    )
