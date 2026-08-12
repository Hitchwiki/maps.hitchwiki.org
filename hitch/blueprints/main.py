import contextlib
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from functools import lru_cache
from urllib.parse import quote

import pandas as pd
from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_security import current_user
from pydantic import ValidationError
from sqlalchemy import func, text
from werkzeug.utils import safe_join

from hitch.blueprints.publish_ride import (
    ALLOWED_VEHICLE_KINDS,
    anonymous_co_hitchhiker_token,
    construct_hitchhiker_from_current_user,
    create_record_from_custom_object,
    is_anonymous_co_hitchhiker,
)
from hitch.blueprints.user import _extract_ride_info
from hitch.blueprints.utils.driver_info_choices import (
    ALLOWED_GENDERS,
    ALLOWED_REASONS_TO_HITCHHIKE,
    ALLOWED_REASONS_TO_PICK_UP,
    ALLOWED_RIDE_REASONS,
    COUNTRY_CHOICES,
    COUNTRY_CODES,
    COUNTRY_NAME_BY_CODE,
    GENDER_CHOICES,
    LANGUAGE_CHOICES,
    LANGUAGE_CODES,
    LANGUAGE_NAME_BY_CODE,
    REASON_DESCRIPTION_BY_CODE,
    REASON_TO_HITCHHIKE_CHOICES,
    REASON_TO_HITCHHIKE_DESCRIPTION_BY_CODE,
    REASON_TO_PICK_UP_CHOICES,
    RIDE_REASON_CHOICES,
    RIDE_REASON_DESCRIPTION_BY_CODE,
)
from hitch.blueprints.utils.filter_request_log import FILTER_FIELDS, log_filter_request
from hitch.blueprints.utils.hitchhiking_data_standard_pydantic_model import HitchhikingRecord
from hitch.blueprints.utils.iso_country_codes import ISO_3166_1_ALPHA_2
from hitch.blueprints.utils.license_plate_country_codes import LICENSE_PLATE_COUNTRY_CHOICES
from hitch.blueprints.utils.notifications import (
    notify_co_hitchhiker_invite,
    notify_ride_comment,
    notify_ride_like,
    unread_count,
)
from hitch.blueprints.utils.post_hitchhiking_ride_to_nostr import HitchhikingDataStandardToNostrPoster
from hitch.blueprints.utils.report_ride import OWNER_DELETE_REASON, REPORT_REASONS, REPORTS_TO_HIDE
from hitch.blueprints.utils.ride_facts import haversine_km, ride_map_entry, spot_id_for, stop_facts
from hitch.blueprints.utils.ride_images import (
    MAX_IMAGES_PER_RIDE,
    RideImageError,
    attach_ride_images,
    claim_draft_images,
    delete_ride_image,
    image_url,
    images_for_draft,
    images_for_ride,
    prepare_upload,
    store_draft_image,
    sweep_stale_drafts,
    valid_draft_token,
)
from hitch.blueprints.utils.ride_ip_log import get_client_ip, log_ride_ip
from hitch.blueprints.utils.ride_sources import THIS_NOSTR_SOURCE, ride_is_replaceable, ride_source
from hitch.blueprints.utils.route_request_log import log_route_request
from hitch.blueprints.utils.search_request_log import log_search_request
from hitch.blueprints.utils.signup_prompt_log import PROMPT_ACTIONS, log_signup_prompt
from hitch.extensions import db
from hitch.helpers import get_db, get_dirs
from hitch.models import (
    CoHitchhiker,
    Follow,
    ProposedSpot,
    RideComment,
    RideEvent,
    RideImage,
    RideLike,
    RideReport,
    SpotName,
    User,
)
from hitch.scripts.nostr_ride_parsing import parse_post_to_ride_fields
from hitch.translations import t
from hitch.translations.weekdays import weekday_names
from hitch.usernames import find_user_ci, same_username, username_key

main_bp = Blueprint("main", __name__)

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
    """Check if the current user is listed among this ride's hitchhikers, whatever its source.

    Names are compared case-insensitively (hitch/usernames.py) — the rides someone imported
    from another platform carry the spelling they used there, and an exact match would lock
    them out of editing their own ride history.
    """
    if user.is_anonymous:
        return False

    content = ride.content or {}
    hitchhikers = content.get("hitchhikers", [])
    return any(same_username(user.username, h.get("nickname")) for h in hitchhikers)


def _user_owns_ride(ride, user):
    """Check if the current user may *edit* this ride.

    Editing republishes the event under this app's Nostr key with the same `d` tag, which
    only replaces the original when we published it in the first place. That covers rides
    logged here *and* the datasets this project imported and republished itself — a
    hitchhiker whose old hitchmap.com rides are on this map can fix them. A ride another
    platform put on the relays stays read-only however it got here; see
    `hitch/blueprints/utils/ride_sources.py` for both halves of that rule. Deletion has no
    such constraint, see `_user_can_delete_ride`.
    """
    if not ride_is_replaceable(ride):
        return False
    return _user_is_hitchhiker(ride, user)


def _ride_is_unclaimed(ride):
    """Whether this ride has no named hitchhiker, i.e. nobody has put their name to it.

    Both shapes count: an empty hitchhikers list (some imports carry none) and one whose
    entries are all the anonymous placeholder — including the "Anonymous:<gender>" tokens
    an anonymous co-hitchhiker is recorded as.
    """
    nicknames = [(h or {}).get("nickname") for h in ((ride.content or {}).get("hitchhikers") or [])]
    return all(not n or is_anonymous_co_hitchhiker(n) for n in nicknames)


def _store_published_ride(event):
    """Write a ride we just published to Nostr straight into the local ride_event table.

    Without this the ride exists only on the relays until fetch_nostr_incremental runs
    (up to 5 min), so /ride/<d_tag> 404s and the author's own ride is missing from their
    profile. We parse our own signed event with parse_post_to_ride_fields — the exact
    function both fetch scripts use — so the row is identical to the one the cron would
    have written, and the cron's upsert then classifies it "unchanged".

    Upsert keyed on the addressable coordinate (pubkey, d), as in
    fetch_nostr_incremental.py. `>=` rather than `>` on created_at: we are the publisher,
    so our event is by definition the newest revision even if an edit lands in the same
    second as the original.

    Known gap: pynostr does not check the relay's OK notice, so a silently rejected event
    leaves a row here that no fetch will ever confirm, and the weekly full fetch_nostr
    (delete-and-recreate) drops it. That is still better than today, where such a ride is
    lost immediately — and it is the same gap dist/temporary.json exists to record.

    Never raises: the ride is already on the relay by the time we get here, so a local DB
    problem must not turn a successful publish into a 500.
    """
    if event is None:
        return
    try:
        fields = parse_post_to_ride_fields(event.to_dict())
        if fields is None or not fields.get("d"):
            return
        row = db.session.query(RideEvent).filter_by(pubkey=fields["pubkey"], d=fields["d"]).first()
        if row is None:
            db.session.add(RideEvent(**fields))
        elif fields["created_at"] >= (row.created_at or 0):
            # An edit publishes a new event id under the same (pubkey, d), so every
            # column is overwritten — including the primary key.
            for column, value in fields.items():
                setattr(row, column, value)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not store the published ride locally; the Nostr fetch cron will import it")


def _user_can_delete_ride(ride, user):
    """Check if the current user may hide this ride from the map.

    Deleting only writes a local RideReport row (it never touches the relays), so it works
    for rides imported from other sources too — a hitchhiker who finds their own ride
    logged on hitchwiki.org / hitchmap.com must be able to take it off the map, exactly as
    those rides already show up as theirs on their profile page.
    """
    return _user_is_hitchhiker(ride, user)


def _ride_owner_users(ride):
    """Registered users among this ride's listed hitchhikers, matched by nickname.

    A ride can list several hitchhikers (co-hitchhiking); any of them counts as "the
    person whose ride it is" for the follow-gated comment permission below.
    """
    content = ride.content or {}
    keys = [username_key(h.get("nickname")) for h in (content.get("hitchhikers") or []) if h.get("nickname")]
    if not keys:
        return []
    # Case-insensitive: a ride logged under another spelling of someone's name is still theirs.
    return db.session.query(User).filter(func.lower(User.username).in_(keys)).all()


def _user_can_comment_on_ride(ride, user):
    """A user may comment on a ride if it's their own, or if any of its owners follows them.

    Comments are follow-gated (like DMs) so a ride can't be flooded with comments from
    strangers its owner has never engaged with; owners can always comment on their own ride.
    """
    if user.is_anonymous:
        return False
    owners = _ride_owner_users(ride)
    if any(owner.id == user.id for owner in owners):
        return True
    if not owners:
        return False
    owner_ids = [owner.id for owner in owners]
    return Follow.query.filter(Follow.follower_id.in_(owner_ids), Follow.followed_id == user.id).first() is not None


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
        # "/", "/index.html", "/light", "/light.html", "/with_destination" and
        # "/with_destination.html" are six URLs onto one map (times 31 languages, times
        # the ?heatmap=true toggle). They are variants of the same page, not pages, so
        # they all name "/" as canonical instead of each defending itself.
        canonical_url=_external_https("main.render_map", map_variation=None),
        hide_add_spot_button=current_app.config.get("HIDE_ADD_SPOT_BUTTON", False),
        hide_account_button=current_app.config.get("HIDE_ACCOUNT_BUTTON", False),
        is_logged_in=not current_user.is_anonymous,
        username=("" if current_user.is_anonymous else current_user.username),
        unread_notifications=unread_count(current_user),
        activities_badge=activities_badge(),
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

    Resolved against the language that served this request. main_bp is registered once
    per language as "main_<lang>" (register_blueprints), and a bare "main.render_spot"
    always resolves to the English registration -- so /de/spot/<id> would name the
    English URL as its own canonical while the hreflang block next to it declares the
    two as translations. Search Console reads that as "Alternate page with proper
    canonical tag" and drops the translated page.
    """
    lang = getattr(g, "lang", "en")
    blueprint, _, view = endpoint.rpartition(".")
    if lang != "en" and blueprint:
        endpoint = f"{blueprint}_{lang}.{view}"
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
    spot = payload.get("spot") or {}
    name = spot.get("name")
    # A name alone is worth a preview — it gives the tab and the messenger card a real
    # place instead of coordinates — so the rating fields are optional from here on.
    if not ratings and not name:
        return None
    return {
        "name": name,
        "rating": sum(ratings) / len(ratings) if ratings else None,
        "count": len(rides) if ratings else None,
        "wait": spot.get("wait"),
        "distance": spot.get("distance"),
    }


def _spot_description(preview):
    """One sentence a messenger/crawler can show under the link, or None if we have
    nothing to say. Returning None for a named-but-unrated spot is deliberate: the
    template's robots meta keys off the description, and naming ~30k spots must not
    turn them into 30k indexable pages that say nothing."""
    if not preview or preview["rating"] is None:
        return None
    plural = t("ride") if preview["count"] == 1 else t("rides")
    parts = [t("Rated {rating:.1f}/5 from {count} {plural}.", rating=preview["rating"], count=preview["count"], plural=plural)]
    if preview["wait"]:
        parts.append(t("Typical wait {wait} min.", wait=round(preview["wait"])))
    if preview["distance"]:
        parts.append(t("Rides average {distance} km.", distance=round(preview["distance"])))
    parts.append(t("See the spot on the hitchhiking map."))
    return " ".join(parts)


# Roughly what a messenger card shows before it truncates. Long ride comments are
# common, so trim rather than let the preview run into an ellipsis mid-sentence.
RIDE_COMMENT_PREVIEW_CHARS = 200


def _ride_place_name(spot_id):
    """Display name of the spot a ride started from, or None.

    Prefers the per-spot file, which holds the fully-cascaded name the map itself shows
    (OSM feature, then service area, then fuel, then car-pooling, then geocode). A ride
    logged minutes ago has no such file yet — exactly the ride whose link gets shared —
    so fall back to the cached geocode in spot_name.
    """
    if not spot_id:
        return None
    preview = _spot_preview(spot_id)
    if preview and preview.get("name"):
        return preview["name"]
    row = db.session.get(SpotName, spot_id)
    return row.name if row else None


def _ride_preview_meta(ride, spot_id):
    """(title, description) for a ride's tab title and link preview.

    /ride/<d_tag> is what the success overlay's share card now links to, so a shared
    ride must not unfurl with the generic site blurb. Text only — a per-ride map image
    would need a whole generation pipeline like route_preview.py.
    """
    place = _ride_place_name(spot_id)
    title = t("Hitchhiking ride from {place}", place=place) if place else t("A hitchhiking ride")
    # Truthiness is deliberate here, unlike the wait check below: a 0.0 km ride (pickup
    # and destination coincide) isn't worth putting in the title as "– 0 km".
    if ride.get("distance_km"):
        title += " – " + t("{km} km", km=round(ride["distance_km"]))

    parts = []
    if ride.get("rating"):
        parts.append(t("Rated {rating}/5.", rating=ride["rating"]))
    # An instant pickup (wait == 0) is a real, good outcome, not a missing value — keep
    # it distinct from "wait never recorded" the same way stop_facts and the template do.
    if ride.get("wait") is not None:
        parts.append(t("Waited {wait} min.", wait=ride["wait"]))
    comment = (ride.get("comment") or "").strip()
    if comment:
        if len(comment) > RIDE_COMMENT_PREVIEW_CHARS:
            comment = comment[:RIDE_COMMENT_PREVIEW_CHARS].rstrip() + "…"
        parts.append(comment)
    if not parts:
        parts.append(t("A hitchhiking ride logged on Hitchwiki Maps."))
    return title, " ".join(parts)


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
    name = preview["name"] if preview else None
    return render_template(
        "map.html",
        map_variation=None,
        spot_title=t("{name} — hitchhiking spot", name=name)
        if name
        else t("Hitchhiking spot at {lat:.5f}, {lon:.5f}", lat=lat, lon=lon),
        spot_description=_spot_description(preview),
        spot_url=_external_https("main.render_spot", spot_id=spot_id),
        hide_add_spot_button=current_app.config.get("HIDE_ADD_SPOT_BUTTON", False),
        hide_account_button=current_app.config.get("HIDE_ACCOUNT_BUTTON", False),
        is_logged_in=not current_user.is_anonymous,
        unread_notifications=unread_count(current_user),
        activities_badge=activities_badge(),
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


@lru_cache(maxsize=1)
def _country_cc_by_name():
    """Country name -> ISO-2 code, from the same geojson the map's Countries mode uses.

    Cached for the process: the file is small but this runs on every crawler hit,
    and the mapping only changes when the geojson is redeployed.
    """
    path = os.path.join(current_app.root_path, "static", "countries.geojson")
    try:
        with open(path) as f:
            geo = json.load(f)
    except (OSError, ValueError):
        return {}
    return {f["properties"]["name"]: f["properties"]["cc"] for f in geo.get("features", [])}


def _country_description(name):
    """One sentence of real statistics for a country, or None if we have none.

    Built from dist/country_insights.json (median wait/distance, keyed by ISO code)
    — the same numbers the country sheet draws as histograms. A country with no
    entry gets no description, which makes the page noindex: an empty country view
    is a soft 404 and would only dilute the site.
    """
    cc = _country_cc_by_name().get(name)
    if not cc:
        return None
    path = safe_join(get_dirs()["dist"], "country_insights.json")
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            insights = json.load(f).get(cc) or {}
    except (OSError, ValueError):
        return None

    wait = (insights.get("wait") or {}).get("stats") or {}
    distance = (insights.get("distance") or {}).get("stats") or {}
    # n is the sample size behind the median; without it there is no claim to make.
    if not wait.get("n"):
        return None

    parts = [t("Median wait {wait} min across {n} logged rides", wait=round(wait["median"]), n=wait["n"])]
    if distance.get("median"):
        parts.append(t("typical ride {km} km", km=round(distance["median"])))
    return t(
        "Hitchhiking in {name}: {facts}. Read what hitchhiking there is like and see waiting-time statistics.",
        name=name,
        facts=", ".join(parts),
    )


# Country permalink, mirroring /spot/<id>. The name lives in the path rather than
# the older #country/<name> fragment because crawlers discard everything after
# "#": every country shared one indexable URL ("/"), so none of them could rank,
# carry its own description, or appear in the sitemap. map.js reads the path back
# and opens the same country sheet; the legacy hash is still accepted.
@main_bp.route("/country/<name>")
def render_country(name):
    description = _country_description(name)
    return render_template(
        "map.html",
        map_variation=None,
        spot_title=t("Hitchhiking in {name}", name=name),
        spot_description=description,
        spot_url=_external_https("main.render_country", name=name),
        hide_add_spot_button=current_app.config.get("HIDE_ADD_SPOT_BUTTON", False),
        hide_account_button=current_app.config.get("HIDE_ACCOUNT_BUTTON", False),
        is_logged_in=not current_user.is_anonymous,
        unread_notifications=unread_count(current_user),
        activities_badge=activities_badge(),
    )


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
        activities_badge=activities_badge(),
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


# Fire-and-forget beacon from map.js once a filter combination settles (the
# client debounces, so this is one row per intent rather than one per keystroke).
# Filtering is entirely client-side, so this is the only place the server learns
# which filters people use. `matches` records how many spots survived, which is
# what separates a useful filter from one people try and abandon. Always returns
# 204 (client uses sendBeacon).
@main_bp.route("/log-filter-request", methods=["POST"])
def log_filter_request_endpoint():
    data = request.get_json(silent=True) or {}
    filters = data.get("filters")
    if not isinstance(filters, dict):
        return ("", 204)
    # Only ever record the filters we know about — the client is untrusted, and
    # unknown keys would not have a column to land in anyway.
    known = {k: filters[k] for k in FILTER_FIELDS if filters.get(k) not in (None, "", False)}
    if not known:
        return ("", 204)
    try:
        matches = int(data["matches"])
    except (KeyError, TypeError, ValueError):
        matches = None
    log_filter_request(known, matches)
    return ("", 204)


# Fire-and-forget beacon from map.js for the post-submit sign-up nudges. The
# overlays are client-side (shown at most once per browser), so this is the only
# place the server learns whether they convert. Always returns 204 (client uses
# sendBeacon).
@main_bp.route("/log-signup-prompt", methods=["POST"])
def log_signup_prompt_endpoint():
    data = request.get_json(silent=True) or {}
    prompt, action = data.get("prompt"), data.get("action")
    if action in PROMPT_ACTIONS.get(prompt, ()):
        log_signup_prompt(prompt, action)
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

    return jsonify(
        {
            "reasons": REASON_TO_PICK_UP_CHOICES,
            "genders": GENDER_CHOICES,
            "languages": LANGUAGE_CHOICES,
            "countries": COUNTRY_CHOICES,
            "plate_countries": LICENSE_PLATE_COUNTRY_CHOICES,
            "vehicle_kinds": VEHICLE_KIND_CHOICES,
            "passenger_kinds": WEIGHTS["passenger_kinds"],
        }
    )


def _ride_to_card(ride):
    """Build the card dict the activities/recent template renders for a RideEvent.

    Shares _extract_ride_info with the profile and trip ride lists rather than deriving
    its own subset, so every ride card in the app carries the same facts — waiting time,
    distance, destination, give-up flag — and the one _ride_card.html macro can render
    all of them identically. Photos are attached per list, not per ride (see the caller).

    Importing it from user.py is safe in this direction only: user.py imports nothing
    from here, so there is no cycle to break.
    """
    return _extract_ride_info(ride, "recent")


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
    newest `limit` matching rides instead of scanning every ride in Python. The match is
    case-insensitive (SQL `lower()` = hitch/usernames.username_key), so a followed user's
    imported rides reach the feed under whatever spelling they carry.
    """
    if not followed_usernames:
        return []

    placeholders = ",".join(f":n{i}" for i in range(len(followed_usernames)))
    params = {f"n{i}": username_key(name) for i, name in enumerate(followed_usernames)}
    params["lim"] = limit
    sql = text(
        f"""
        SELECT re.id FROM ride_event re
        WHERE re.submission_time IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM json_each(json_extract(re.content, '$.hitchhikers')) je
            WHERE lower(json_extract(je.value, '$.nickname')) IN ({placeholders})
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


# How far back the Activities dot ever looks, in seconds. It bounds the badge query on
# the map's index route — the most-requested page in the app — to the slice of
# ride_event the created_at index can serve, rather than every ride a followed user has
# ever logged. Nothing the badge is about is lost: it reports *new* activity, and a
# month-old ride is not news.
#
# Measured against prod (~4.8k rides in the last 30 days): 53 ms for a viewer who last
# looked a month ago, 10 ms for a week, 2 ms for a day — against 556 ms unbounded. Only
# the worst case is on the page render, and only for someone who follows people and has
# stopped opening the feed.
BADGE_LOOKBACK_S = 30 * 24 * 3600


def _has_unseen_followed_rides(user, followed_usernames):
    """Has anyone `user` follows published a ride since they last opened /recent?

    Compared on `created_at` — the Nostr event's own epoch-seconds stamp, and an indexed
    column — not on `submission_time`, which is a string in the submitter's local
    wall-clock time and so cannot be ordered against a server timestamp at all. An edit
    republishes the ride under a fresh `created_at`, so an edited old ride counts as
    activity; it is activity, just not a new ride.

    Matches followed usernames against the nicknames in the ride's content JSON, the
    same case-insensitive way _followed_rides does — rides link to users by name, not by
    foreign key (hitch/usernames.py).
    """
    if not followed_usernames:
        return False
    since = max(user.recent_seen_at or 0, int(time.time()) - BADGE_LOOKBACK_S)
    placeholders = ",".join(f":n{i}" for i in range(len(followed_usernames)))
    params = {f"n{i}": username_key(name) for i, name in enumerate(followed_usernames)}
    params["since"] = since
    sql = text(
        f"""
        SELECT 1 FROM ride_event re
        WHERE re.created_at > :since
          AND EXISTS (
            SELECT 1 FROM json_each(json_extract(re.content, '$.hitchhikers')) je
            WHERE lower(json_extract(je.value, '$.nickname')) IN ({placeholders})
          )
        LIMIT 1
        """
    )
    return db.session.execute(sql, params).first() is not None


def activities_badge():
    """Whether the map's Activities button carries its dot.

    Two reasons, both saying the same thing — there is something on /recent worth
    opening:

    * the user follows nobody, so the whole point of the page is still news to them (it
      renders its follow suggestions in exactly that case, see `recent_spots`);
    * someone they follow has contributed since they last looked.

    Anonymous visitors never get one: they can't follow anyone and can't clear it, so it
    would be permanent noise.
    """
    if current_user.is_anonymous:
        return False
    followed = _followed_usernames()
    if not followed:
        return True
    return _has_unseen_followed_rides(current_user, followed)


def _suggested_hitchhikers(ride_cards, limit=3):
    """Follow suggestions for users who follow nobody yet: the most active hitchhikers
    among the recent ride cards. Only registered users are suggested — they have a
    profile page and can actually be followed (rides by unregistered nicknames can't)."""
    me = None if current_user.is_anonymous else current_user.username
    counts = {}
    for ride in ride_cards:
        name = ride.get("hitchhiker_name")
        # Skip anonymous rides and the viewer themselves (can't follow yourself).
        if not name or name == "Anonymous" or same_username(name, me):
            continue
        counts[name] = counts.get(name, 0) + 1
    if not counts:
        return []
    # Cards already print the account's own spelling, but match case-insensitively anyway so
    # a name this app never canonicalised (an unregistered stub that later registered) still
    # resolves to the one suggestion it should be.
    registered = {
        username_key(row[0])
        for row in db.session.query(User.username).filter(func.lower(User.username).in_([username_key(n) for n in counts])).all()
    }
    ranked = sorted(
        ((name, count) for name, count in counts.items() if username_key(name) in registered),
        key=lambda kv: kv[1],
        reverse=True,
    )[:limit]
    return [{"username": name, "ride_count": count} for name, count in ranked]


@main_bp.route("/help")
def help_volunteers():
    """Volunteer landing page — the one link the menu points at for "how do I help?".

    Linked from the menu sheet, so it inherits the 31 language mirrors every main_bp
    route gets. The ride count is read live rather than baked into the copy: a concrete,
    current number is what makes "we already collect this data" credible to someone
    weighing up a thesis, and a stale hardcoded one would quietly become a lie.
    """
    ride_count = db.session.query(func.count(RideEvent.id)).scalar() or 0
    return render_template(
        "help.html",
        # Rounded down to a round thousand: the exact figure changes every few minutes
        # and nobody reading a call for volunteers needs that precision.
        ride_count=ride_count // 1000 * 1000,
    )


@main_bp.route("/why-not-hitchhike")
def why_not_hitchhike():
    """Spots with a repeatable weekday pattern — same spot, same weekday, same faraway
    destination, and nobody waited long.

    The whole analysis is precomputed into dist/why_not_hitchhike.json by
    hitch/scripts/why_not_hitchhike.py (weekly, see deploy/cron.sh): it clusters every
    ride's destination against every other ride's from the same spot, far too heavy for a
    request. A missing file renders an empty page rather than raising, exactly like the
    leaderboard's precomputed inputs — a fresh checkout has never run the job.

    Weekday *names* are resolved here, not in the script: main_bp routes are mirrored in
    31 languages, so a name baked into the JSON would be wrong in 30 of them.
    """
    path = os.path.join(get_dirs()["dist"], "why_not_hitchhike.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}

    return render_template(
        "why_not_hitchhike.html",
        matches=data.get("matches", []),
        near_misses=data.get("near_misses", []),
        criteria=data.get("criteria", {}),
        coverage=data.get("coverage", {}),
        generated_at=data.get("generated_at"),
        weekdays=weekday_names(),
    )


@main_bp.route("/recent")
def recent_spots():
    """Activities page: rides from people you follow, then the last 100 added rides."""
    # Captured before the feed is read, and stored as "seen" after: a ride published
    # while this page renders is not on it, so it must still count as unseen next time.
    viewed_at = int(time.time())
    rides = (
        db.session.query(RideEvent)
        .filter(RideEvent.submission_time.isnot(None))
        .order_by(RideEvent.submission_time.desc())
        .limit(100)
        .all()
    )
    ride_list = attach_ride_images([_ride_to_card(ride) for ride in rides])

    followed_usernames = _followed_usernames()
    followed_rides = attach_ride_images(_followed_rides(followed_usernames))
    # When the user follows nobody yet, suggest active hitchhikers to follow instead.
    follow_suggestions = _suggested_hitchhikers(ride_list) if (not current_user.is_anonymous and not followed_usernames) else []

    # Opening the page is what clears the dot on the map's Activities button.
    if not current_user.is_anonymous:
        current_user.recent_seen_at = viewed_at
        db.session.commit()

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
    facts = stop_facts(content.get("stops"))
    pickup_lat = facts["pickup_lat"]
    pickup_lon = facts["pickup_lon"]
    dest_lat = facts["dest_lat"]
    dest_lon = facts["dest_lon"]
    departure_time = facts["departure_time"]
    arrival_time = facts["arrival_time"]
    waiting_minutes = facts["waiting_minutes"]

    signal_methods = []
    for sig in content.get("signals") or []:
        for method in sig.get("methods") or []:
            if method not in signal_methods:
                signal_methods.append(method)

    # What the sign said, from the first signal that names it (see the ride form).
    sign_content = next((sig.get("sign_content") for sig in (content.get("signals") or []) if sig.get("sign_content")), None)

    hitchhikers = [
        {"nickname": h.get("nickname") or "Anonymous", "gender": h.get("gender")} for h in (content.get("hitchhikers") or [])
    ]
    # Reasons to hitchhike are per person in the standard, but the page shows them as one
    # list: on a shared ride the interesting fact is why this group was on the road.
    hitchhike_reasons = []
    for h in content.get("hitchhikers") or []:
        for r in h.get("reasons_to_hitchhike") or []:
            label = REASON_TO_HITCHHIKE_DESCRIPTION_BY_CODE.get(r, r)
            if label not in hitchhike_reasons:
                hitchhike_reasons.append(label)

    ride_obj = content.get("ride")
    trip_reasons = []
    if isinstance(ride_obj, dict):
        trip_reasons = [RIDE_REASON_DESCRIPTION_BY_CODE.get(r, r) for r in (ride_obj.get("reasons") or [])]

    # A give-up's last stop is a planned destination, so it has no distance to report --
    # same rule show.py applies to every aggregate (see its no_ride cleanup).
    gave_up = bool(ride.no_ride) or content.get("no_ride") is not None
    distance_km = None if gave_up else haversine_km(pickup_lat, pickup_lon, dest_lat, dest_lon)

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
        "no_ride": gave_up,
        "rating": ride.rating,
        "comment": ride.comment,
        "wait": waiting_minutes,
        "signal_methods": signal_methods,
        "sign_content": sign_content,
        "hitchhike_reasons": hitchhike_reasons,
        "trip_reasons": trip_reasons,
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

    likes_count = RideLike.query.filter_by(ride_d_tag=d_tag).count()
    liked_by_me = (
        not current_user.is_anonymous and RideLike.query.filter_by(ride_d_tag=d_tag, user_id=current_user.id).first() is not None
    )
    comment_rows = (
        db.session.query(RideComment, User.username)
        .join(User, RideComment.user_id == User.id)
        .filter(RideComment.ride_d_tag == d_tag)
        .order_by(RideComment.created_at.asc())
        .all()
    )
    comments = [
        {
            "id": comment.id,
            "username": username,
            "body": comment.body,
            "created_at": comment.created_at,
            "is_own": not current_user.is_anonymous and comment.user_id == current_user.id,
        }
        for comment, username in comment_rows
    ]
    can_comment = _user_can_comment_on_ride(ride, current_user)

    # The share card links here, so the page needs its own preview rather than
    # base.html's site-wide blurb.
    spot_id = spot_id_for(pickup_lat, pickup_lon) if pickup_lat is not None and pickup_lon is not None else None
    og_title, og_description = _ride_preview_meta(ride_view, spot_id)
    ride_images = [{"url": image_url(img.filename), "width": img.width, "height": img.height} for img in images_for_ride(d_tag)]
    return render_template(
        "ride_detail.html",
        ride=ride_view,
        ride_images=ride_images,
        already_reported=already_reported,
        owner_deleted=owner_deleted,
        report_confirmed=request.args.get("reported") == "1",
        og_title=og_title,
        og_description=og_description,
        likes_count=likes_count,
        liked_by_me=liked_by_me,
        comments=comments,
        can_comment=can_comment,
        is_logged_in=not current_user.is_anonymous,
        # Whether the 5-tap claim easter egg is wired up on this page's Share button.
        # Only a hint for the UI — /claim-ride re-checks all three conditions itself.
        can_claim=(not current_user.is_anonymous and _ride_is_unclaimed(ride) and ride_is_replaceable(ride)),
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


@main_bp.route("/claim-ride/<d_tag>", methods=["POST"])
def claim_ride(d_tag):
    """Easter egg: put the logged-in user's name on an unattributed ride.

    Triggered by tapping the Share button on /ride/<d_tag> five times and confirming (see
    README).

    A lot of the map was logged without an account — people submitted anonymously before
    they registered, or their rides arrived in the hitchmap.com import. Claiming
    republishes the event with the user as its hitchhiker, so it counts on their profile,
    in their stats and their trips, and becomes editable from then on.

    Two guards, both necessary:
    * the ride must have no named hitchhiker — otherwise this would be a way to take
      someone else's ride off them;
    * the ride must be one we can replace on Nostr (`ride_is_replaceable`) — a foreign
      platform's ride would fork into a duplicate instead of changing hands.

    There is deliberately no proof that the claimer is the person who logged it: an
    anonymous ride carries no identity to check against, so the honest answer is that this
    is a low-stakes convenience. It is logged to the same IP trail as a submission.

    JSON in both directions — the ride page calls it with fetch and reloads on success.
    """
    if current_user.is_anonymous:
        return jsonify({"ok": False, "error": "not_logged_in"}), 401

    ride = db.session.query(RideEvent).filter_by(d=d_tag).first()
    if not ride:
        return jsonify({"ok": False, "error": "not_found"}), 404
    if not _ride_is_unclaimed(ride):
        return jsonify({"ok": False, "error": "already_claimed"}), 409
    if not ride_is_replaceable(ride):
        return jsonify({"ok": False, "error": "foreign_source", "source": ride_source(ride)}), 403

    try:
        record = HitchhikingRecord.model_validate(ride.content or {})
    except ValidationError:
        # Content we can't re-serialise can't be republished without losing fields.
        current_app.logger.exception("claim-ride: unparseable content for %s", d_tag)
        return jsonify({"ok": False, "error": "unparseable"}), 409

    # Replace the first hitchhiker slot (the submitter's) and keep the rest: a ride logged
    # with anonymous co-hitchhikers still had that many people in the car.
    claimer = construct_hitchhiker_from_current_user()
    record.hitchhikers = [claimer, *(record.hitchhikers or [])[1:]]

    poster = HitchhikingDataStandardToNostrPoster()
    try:
        # Original tags → same `d` and the original published_at, so this replaces the
        # ride rather than adding one.
        poster.post(ride_record=record, tags=ride.tags)
    finally:
        poster.close()
    _store_published_ride(poster.last_event)

    # Same abuse trail as a submission: claiming is a write to public data.
    log_ride_ip(d_tag)

    return jsonify({"ok": True, "hitchhiker_name": current_user.username, "url": f"/ride/{d_tag}"})


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


@main_bp.route("/like-ride/<d_tag>", methods=["POST"])
def like_ride(d_tag):
    """Toggle the current user's like on a ride."""
    if current_user.is_anonymous:
        return redirect(f"/login?next=/ride/{d_tag}")

    ride = db.session.query(RideEvent).filter_by(d=d_tag).first()
    if not ride:
        abort(404)

    existing = RideLike.query.filter_by(ride_d_tag=d_tag, user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
    else:
        # Only the first like on a ride notifies its owner — every later liker would just
        # push the owner's other notifications out of their 10-row window (notify_ride_like
        # dedupes on top of this, so an unlike/relike can't re-trigger it either).
        is_first_like = RideLike.query.filter_by(ride_d_tag=d_tag).count() == 0
        db.session.add(RideLike(ride_d_tag=d_tag, user_id=current_user.id))
        if is_first_like:
            for owner in _ride_owner_users(ride):
                if owner.id != current_user.id:
                    notify_ride_like(owner.id, current_user.username, d_tag)
    db.session.commit()
    return redirect(f"/ride/{d_tag}")


@main_bp.route("/comment-ride/<d_tag>", methods=["POST"])
def comment_ride(d_tag):
    """Add a comment to a ride.

    Only allowed if it's the commenter's own ride, or if the ride's owner already
    follows the commenter — see `_user_can_comment_on_ride`.
    """
    if current_user.is_anonymous:
        return redirect(f"/login?next=/ride/{d_tag}#comments")

    ride = db.session.query(RideEvent).filter_by(d=d_tag).first()
    if not ride:
        abort(404)
    if not _user_can_comment_on_ride(ride, current_user):
        abort(403)

    body = (request.form.get("body") or "").strip()[:2000]
    if body:
        db.session.add(RideComment(ride_d_tag=d_tag, user_id=current_user.id, body=body))
        db.session.commit()
        for owner in _ride_owner_users(ride):
            if owner.id != current_user.id:
                notify_ride_comment(owner.id, current_user.username, d_tag)
    return redirect(f"/ride/{d_tag}#comments")


@main_bp.route("/delete-ride-comment/<int:comment_id>", methods=["POST"])
def delete_ride_comment(comment_id):
    """Let a comment's author delete it."""
    if current_user.is_anonymous:
        abort(403)

    comment = db.session.get(RideComment, comment_id)
    if not comment:
        abort(404)
    if comment.user_id != current_user.id:
        abort(403)

    d_tag = comment.ride_d_tag
    db.session.delete(comment)
    db.session.commit()
    return redirect(f"/ride/{d_tag}#comments")


@main_bp.route("/ride-image", methods=["POST"])
def upload_ride_image():
    """Store one photo the moment the user picks it, before the ride exists.

    Uploading on pick rather than on submit is what makes the picker work at all: the
    ride form navigates the whole page away to the map to choose a pickup point, and a
    file input's selection cannot survive that — nor can a second trip to the file picker
    keep the first trip's files, since opening it replaces the entire FileList.

    The photo lands under the form's `draft_token` and is claimed by the submit
    (claim_draft_images). Editing an existing ride uses the same path, so cancelling an
    edit leaves the ride's photos exactly as they were.
    """
    draft_token = valid_draft_token(request.form.get("draft_token"))
    if not draft_token:
        return jsonify({"ok": False, "error": "Missing upload token."}), 400

    # Counted per draft, so no form can ever hold more than a ride is allowed. The submit
    # re-checks against the ride's own photos, which is the number that finally matters.
    if len(images_for_draft(draft_token)) >= MAX_IMAGES_PER_RIDE:
        return jsonify({"ok": False, "error": f"A ride can have at most {MAX_IMAGES_PER_RIDE} photos."}), 400

    try:
        prepared = prepare_upload(request.files.get("image"))
        row = store_draft_image(draft_token, prepared, None if current_user.is_anonymous else current_user.id)
    except RideImageError as err:
        return jsonify({"ok": False, "error": str(err)}), 400

    # Opportunistic housekeeping: an upload is the only thing that creates drafts, so it
    # is also the natural moment to clear out the ones nobody ever submitted.
    sweep_stale_drafts()

    return jsonify({"ok": True, "id": row.id, "url": image_url(row.filename)})


@main_bp.route("/ride-image/draft/<token>")
def draft_ride_images(token):
    """The photos held under one draft token, so the form can redraw its tiles.

    Needed because picking a pickup location navigates the page away and comes back: the
    token survives in sessionStorage, but the tiles have to be rebuilt from the server.
    Not under /ride-images/ — that prefix is the uploaded files themselves, served from
    dist/ by the catch-all route.
    """
    images = images_for_draft(token)
    return jsonify({"images": [{"id": img.id, "url": image_url(img.filename)} for img in images]})


@main_bp.route("/ride-image/<int:image_id>/delete", methods=["POST"])
def remove_ride_image(image_id):
    """Delete one photo — the little x on its tile.

    Two kinds of photo can be deleted, with a different key for each: one still under a
    draft token (the caller must present that token, which only the form that uploaded it
    has), and one already attached to a ride (the caller must be able to edit that ride).
    """
    row = db.session.get(RideImage, image_id)
    if row is None:
        # Idempotent on purpose: the tile is already gone from the user's point of view,
        # and a double-click must not surface an error.
        return jsonify({"ok": True})

    if row.draft_token:
        if valid_draft_token(request.form.get("draft_token")) != row.draft_token:
            abort(403)
    else:
        ride = db.session.query(RideEvent).filter_by(d=row.ride_d_tag).first()
        if not ride or not _user_owns_ride(ride, current_user):
            abort(403)

    delete_ride_image(row)
    return jsonify({"ok": True})


@main_bp.route("/ride", methods=["GET", "POST"])
def ride_form():
    """Dedicated ride form page."""
    if request.method == "GET":
        edit_d_tag = request.args.get("edit")
        ride_data = None
        # Photos of the ride being edited, so the form can show them with a "remove" box.
        # Filled only inside the ownership check below — a stranger passing ?edit=<d_tag>
        # gets a blank new-ride form and must not see that ride's pictures listed as theirs.
        ride_images = []

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
                    "sign_content": "",
                    "reasons_to_hitchhike": [],
                    "ride_reasons": [],
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

                # Why the driver was on the road at all (`ride.reasons`), as opposed to why
                # they stopped for a hitchhiker (`reasons_to_pick_up`, read above).
                ride_obj = content.get("ride") or {}
                if isinstance(ride_obj, dict):
                    ride_data["ride_reasons"] = [r for r in (ride_obj.get("reasons") or []) if r in ALLOWED_RIDE_REASONS]

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
                # Sign content is a property of the sign signal, so take it from the first
                # entry that actually names one rather than from signals[0] blindly.
                for sig in content.get("signals", []) or []:
                    if sig.get("sign_content"):
                        ride_data["sign_content"] = sig["sign_content"]
                        break

                # Requirement: co-hitchhikers already on a ride cannot be removed when editing,
                # only new ones can be added. "Already present" means either:
                # (a) in the nostr event's hitchhikers list (already accepted, published to Nostr), or
                # (b) in the CoHitchhiker table with accepted="open" (invited, pending response).
                current_nickname = current_user.username if not current_user.is_anonymous else None
                all_hitchhikers = content.get("hitchhikers", [])
                # Reasons to hitchhike belong to one person, so the form must show the
                # editor's own — never a co-hitchhiker's, which re-saving would then
                # publish as if the editor had claimed them.
                own_entry = next(
                    (h for h in all_hitchhikers if same_username(h.get("nickname"), current_nickname)),
                    None,
                )
                if own_entry:
                    ride_data["reasons_to_hitchhike"] = [
                        r for r in (own_entry.get("reasons_to_hitchhike") or []) if r in ALLOWED_REASONS_TO_HITCHHIKE
                    ]
                # The editor themselves is excluded case-insensitively: their ride may list
                # them under the spelling they used on the platform it was imported from, and
                # an exact compare would offer them to themselves as a locked co-hitchhiker.
                hitchhikers_on_nostr = {
                    h.get("nickname")
                    for h in all_hitchhikers
                    if h.get("nickname")
                    and not same_username(h.get("nickname"), current_nickname)
                    and h.get("nickname") != "Anonymous"
                }
                # Anonymous hitchhikers are always co-hitchhikers (creator must be
                # logged in to edit, so they are never "Anonymous" themselves). Their
                # gender round-trips through the form token so re-saving an edited ride
                # doesn't silently drop it.
                anon_tokens = [
                    anonymous_co_hitchhiker_token(h.get("gender")) for h in all_hitchhikers if h.get("nickname") == "Anonymous"
                ]
                pending_invites = {
                    c.co_hitchhiker
                    for c in db.session.query(CoHitchhiker).filter_by(nostr_ride_event_d_tag=edit_d_tag, accepted="open").all()
                }
                locked_co_hitchhikers = sorted(hitchhikers_on_nostr | pending_invites)
                all_co = locked_co_hitchhikers + anon_tokens
                ride_data["co_hitchhiker"] = ",".join(all_co)
                ride_data["co_hitchhiker_locked"] = ",".join(locked_co_hitchhikers)

                ride_images = [{"id": img.id, "url": image_url(img.filename)} for img in images_for_ride(edit_d_tag)]

        return render_template(
            "ride_form.html",
            ride_data=ride_data,
            ride_images=ride_images,
            max_ride_images=MAX_IMAGES_PER_RIDE,
            vehicle_kinds=VEHICLE_KIND_CHOICES,
            country_codes=ISO_3166_1_ALPHA_2,
            country_choices=COUNTRY_CHOICES,
            license_plate_country_choices=LICENSE_PLATE_COUNTRY_CHOICES,
            language_choices=LANGUAGE_CHOICES,
            gender_choices=GENDER_CHOICES,
            reason_to_pick_up_choices=REASON_TO_PICK_UP_CHOICES,
            ride_reason_choices=RIDE_REASON_CHOICES,
            reason_to_hitchhike_choices=REASON_TO_HITCHHIKE_CHOICES,
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
        data["ride_reasons"] = [r.strip() for r in (data.get("ride_reasons") or "").split(",") if r.strip()]
        data["reasons_to_hitchhike"] = [r.strip() for r in (data.get("reasons_to_hitchhike") or "").split(",") if r.strip()]
        # "I did not get a ride here" checkbox — an unchecked box submits no key at all.
        # The in-ride Give Up flow posts no_ride=1 for the same meaning.
        data["no_ride"] = str(data.get("no_ride", "")).strip() not in ("", "0", "false")
        # A give-up reached nobody: the destination stays (it is where the hitchhiker was
        # heading, and the stop still carries it), but nothing arrived there and no car
        # exists to describe. The form hides these fields once the box is ticked; dropping
        # them here as well is what makes that stick, since a hidden input still submits
        # whatever was typed before the tick — and an in-ride Give Up posts no_ride=1
        # through the same endpoint.
        if data["no_ride"]:
            data["arrival_datetime"] = ""
            for field in (
                "vehicle_kind",
                "vehicle_make",
                "vehicle_model",
                "vehicle_license_plate_country",
                "vehicle_license_plate_identifier",
                "driver_would_ride_again",
                "driver_origin_country",
                "driver_age",
                "driver_gender",
            ):
                data[field] = ""
            data["driver_reason_to_pick_up"] = []
            data["driver_languages"] = ""
            data["ride_reasons"] = []
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

        # What the sign said. Only kept when a sign was one of the chosen methods — the
        # field is hidden otherwise, and a stale value must not travel with the ride.
        sign_content = (data.get("sign_content") or "").strip()
        assert len(sign_content) <= 255, "Sign content must be <= 255 characters"
        data["sign_content"] = sign_content if "sign" in signals_selected else ""

        # Reasons to hitchhike (the "You" section) and the driver's reasons for the trip
        # itself — both enum allowlists, same shape as reason_to_pick_up below.
        for r in data["reasons_to_hitchhike"]:
            assert r in ALLOWED_REASONS_TO_HITCHHIKE, f"Invalid reason_to_hitchhike: {r}"
        for r in data["ride_reasons"]:
            assert r in ALLOWED_RIDE_REASONS, f"Invalid ride reason: {r}"

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
        existing_ride = None
        if edit_d_tag:
            existing_ride = db.session.query(RideEvent).filter_by(d=edit_d_tag).first()
            # Inride requests use fetch (no navigation), so return JSON instead of redirecting.
            if not existing_ride or not _user_owns_ride(existing_ride, current_user):
                if wants_json:
                    return jsonify({"ok": False, "error": "unauthorized"}), 400
                return redirect("/#error")  # User doesn't own this ride

        # Photos were already uploaded and stored while the form was being filled in (see
        # upload_ride_image); all the submit carries is the token to claim them under.
        draft_token = valid_draft_token(data.get("draft_token"))

        if edit_d_tag:
            # Create new record with updated form data to get updated fields
            # TODO: define license properly instead of using "xxx"
            # Keep the ride's original source: editing a ride imported from hitchmap.com
            # corrects it, it does not turn it into a ride that was recorded here. The
            # source is also what decides whether it stays editable (see ride_sources).
            updated_record = create_record_from_custom_object(
                custom_object=data, source=ride_source(existing_ride) or THIS_NOSTR_SOURCE, license=THIS_DATA_LICENSE
            )

            # post the updated event (maintaining all original tags including d tag)
            poster = HitchhikingDataStandardToNostrPoster()
            _ = poster.post(ride_record=updated_record, tags=existing_ride.tags)
            poster.close()
            _store_published_ride(poster.last_event)
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
            _store_published_ride(poster.last_event)

        # Abuse trail: pair the saved ride's d tag with the submitter's IP so a flood of
        # fake rides can be traced back to one source. Edits are logged too, since an
        # abuser can also vandalise a ride they own by editing it.
        log_ride_ip(d_tag)

        ### Photos
        # The d tag exists for the first time here, so this is the earliest moment the
        # form's already-uploaded photos can be attached to a ride. On an edit we only
        # reach this line once ownership was confirmed above.
        if draft_token:
            claim_draft_images(draft_token, d_tag)

        ### Co-hitchhikers
        # Requirement: co-hitchhikers already on a ride cannot be removed when editing, only new
        # ones can be added. We achieve this by only inserting co-hitchhikers not already in the DB.
        if "co_hitchhiker" in data and data["co_hitchhiker"] != "":
            current_username = current_user.username if not current_user.is_anonymous else None
            existing_co = {
                username_key(c.co_hitchhiker)
                for c in db.session.query(CoHitchhiker).filter_by(nostr_ride_event_d_tag=d_tag).all()
            }
            invited_user_ids = []
            for ch in data["co_hitchhiker"].split(","):
                username = ch.strip()
                if username == "" or is_anonymous_co_hitchhiker(username):
                    continue  # anonymous hitchhikers are handled in the Nostr event, not in CoHitchhiker
                if same_username(username, current_username):
                    continue  # skip self
                if username_key(username) in existing_co:
                    continue  # already present, cannot be removed so no need to re-add
                invited_user = find_user_ci(username)
                if not invited_user:
                    continue  # skip non-existent users
                co_hitchhiker = CoHitchhiker(
                    nostr_ride_event_d_tag=d_tag,
                    # Stored under the invited account's own spelling, since that is the name
                    # their accept/reject and their profile's pending list look themselves up by.
                    co_hitchhiker=invited_user.username,
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

        # A nudge only makes sense for a ride just created — an edit is not the moment to
        # ask someone to sign up, and the ride's anonymity was already decided. The client
        # shows each overlay at most once per browser and then falls through to #success.
        # The d tag travels in the URL because the full-page POST navigates away: the
        # success overlay's share card links to /ride/<d_tag>, which now resolves
        # immediately (see _store_published_ride). map.js strips the param once read.
        success_query = f"/?ride={quote(d_tag)}"
        if not edit_d_tag:
            if current_user.is_anonymous:
                return redirect(f"{success_query}#success-anon")
            if any(is_anonymous_co_hitchhiker(ch) for ch in data.get("co_hitchhiker", "").split(",")):
                return redirect(f"{success_query}#success-invite")
        return redirect(f"{success_query}#success")

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


def _last_generation_ts():
    """Epoch seconds of the DB snapshot the generated map files were built from.

    show.py writes dist/generated_at.json as its last act. Before the first run that
    does so, fall back to the rides index's mtime — that is LATER than the snapshot it
    was built from, so the fallback under-returns pending rides rather than
    double-showing rides that are already in the generated files. Returns None when
    nothing has been generated at all, in which case there is no map data to add to.

    generated_at.json is written ~400 lines after spots.json/rides_index.json/the
    per-spot files, so a run killed in between (this host OOM-kills the container — see
    CLAUDE.md) leaves it pointing at a STALE snapshot while the generated files already
    hold newer rides. Trusting that stale ts would let /pending_rides.json add those
    same rides' counts on top of a review_count that already includes them. In a healthy
    run generated_at.json is always the file written last, so if it is *older* than
    rides_index.json the previous run did not finish — treat it as absent and fall
    through to the mtime fallback, which under-returns and is therefore safe.
    """
    dist = get_dirs()["dist"]
    generated_at_path = os.path.join(dist, "generated_at.json")
    generated_at_ts = generated_at_mtime = None
    try:
        with open(generated_at_path) as f:
            generated_at_ts = float(json.load(f)["ts"])
        generated_at_mtime = os.path.getmtime(generated_at_path)
    except (OSError, ValueError, KeyError, TypeError):
        generated_at_ts = generated_at_mtime = None

    try:
        rides_index_mtime = os.path.getmtime(os.path.join(dist, "rides_index.json"))
    except OSError:
        rides_index_mtime = None

    if generated_at_ts is not None and rides_index_mtime is not None and generated_at_mtime < rides_index_mtime:
        return rides_index_mtime
    if generated_at_ts is not None:
        # Either healthy (newer than rides_index.json) or there is no rides_index.json
        # to compare against at all — nothing to detect staleness with, so trust it.
        return generated_at_ts
    return rides_index_mtime


def _hidden_ride_dtags(d_tags):
    """Which of these rides are hidden from the map by reports.

    Same rule show.py applies before generating anything: REPORTS_TO_HIDE distinct
    reporters agreeing on one reason, or a single owner-deletion row. Scoped to the
    d tags we are about to serve, since that is only ever a handful of rides.
    """
    if not d_tags:
        return set()
    rows = (
        db.session.query(RideReport.ride_d_tag, RideReport.reason, func.count().label("n"))
        .filter(RideReport.ride_d_tag.in_(list(d_tags)))
        .group_by(RideReport.ride_d_tag, RideReport.reason)
        .all()
    )
    return {r.ride_d_tag for r in rows if r.n >= REPORTS_TO_HIDE or r.reason == OWNER_DELETE_REASON}


def _images_by_ride(d_tags):
    """Photo URLs keyed by ride d tag, for the handful of rides we are about to serve.

    Ordered by id so the strip shows photos in upload order, the same order the
    per-spot files and the ride page use.
    """
    if not d_tags:
        return {}
    rows = db.session.query(RideImage).filter(RideImage.ride_d_tag.in_(list(d_tags))).order_by(RideImage.id.asc()).all()
    by_d_tag = {}
    for row in rows:
        by_d_tag.setdefault(row.ride_d_tag, []).append(image_url(row.filename))
    return by_d_tag


@main_bp.route("/pending_rides.json")
def pending_rides_json():
    """Rides logged since show.py last generated the map files.

    Served straight from the DB (like /proposed_spots.json) rather than from dist/, so a
    ride submitted seconds ago is on the map immediately instead of waiting up to 15
    minutes for the fetch and generate crons. Normally an empty array; at most it holds
    the last few minutes of rides, so it needs no caching of its own. map.js merges these
    into the markers and into the spot pane, deduping on the ride's d tag once the
    generated files catch up.
    """
    since = _last_generation_ts()
    if since is None:
        return jsonify([])

    rides = db.session.query(RideEvent).filter(RideEvent.created_at >= int(since)).all()
    hidden = _hidden_ride_dtags([r.d for r in rides if r.d])
    # One query for the whole pending set: a photo uploaded minutes ago is not in the
    # per-spot files yet, so without this the spot pane's image strip would lag a ride
    # by up to a show.py cycle even though the ride card itself is already there.
    images_by_d_tag = _images_by_ride([r.d for r in rides if r.d])
    entries = []
    for ride in rides:
        if ride.d in hidden:
            continue
        entry = ride_map_entry(ride, images_by_d_tag.get(ride.d))
        if entry is not None:
            entries.append(entry)
    return jsonify(entries)
