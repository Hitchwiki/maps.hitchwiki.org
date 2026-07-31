import io
import json
import os
import time
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import quote

import pandas as pd
import requests
from flask import (
    Blueprint,
    Response,
    current_app,
    g,
    has_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_security import current_user
from sqlalchemy import text

from hitch.blueprints.publish_ride import ANONYMOUS_NICKNAME, construct_hitchhiker_from_current_user
from hitch.blueprints.utils.hitchhiking_data_standard_pydantic_model import HitchhikingRecord
from hitch.blueprints.utils.notifications import notify_new_follower
from hitch.blueprints.utils.post_hitchhiking_ride_to_nostr import HitchhikingDataStandardToNostrPoster
from hitch.blueprints.utils.report_ride import OWNER_DELETE_REASON
from hitch.blueprints.utils.ride_gpx import rides_gpx
from hitch.blueprints.utils.ride_score import score_fields
from hitch.blueprints.utils.ride_sources import ride_is_replaceable
from hitch.extensions import db, security
from hitch.forms import UserEditForm
from hitch.helpers import get_db, get_dirs, haversine_np
from hitch.models import CoHitchhiker, Follow, Notification, RideEvent, RidePlace, RideReport, Trip, TripRide, User
from hitch.scripts.races import current_races
from hitch.translations import t

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

user_bp = Blueprint("user", __name__)


@user_bp.route("/edit-user", methods=["GET", "POST"])
def form():
    if current_user.is_anonymous:
        return redirect("/login")

    form = UserEditForm()
    # WTForms field labels/choices are set once at class-definition time (module import),
    # long before any request -- and so before g.lang exists -- so t() there would always
    # render English. Translate them here instead, per request, overwriting the field's
    # `.text`/`.choices` before render. Choice *values* (form.gender.data on submit) are
    # untouched, only the displayed label -- so this is safe regardless of language.
    # origin_country's ~250 pycountry names are left untranslated (a much bigger,
    # separate task, same as place names elsewhere in the app).
    form.gender.label.text = t("Gender")
    form.gender.choices = [(v, t(lbl)) for v, lbl in form.gender.choices]
    form.year_of_birth.label.text = t("Year of Birth")
    form.hitchhiking_since.label.text = t("Hitchhiking Since")
    form.origin_country.label.text = t("Where are you from?")
    form.origin_country.choices = [(v, t(lbl) if v == "" else lbl) for v, lbl in form.origin_country.choices]
    form.origin_city.label.text = t("Which city are you from?")
    form.hitchwiki_username.label.text = t("Hitchwiki Username")
    form.trustroots_username.label.text = t("Trustroots Username")
    form.email_notifications.label.text = t("Receive notifications and updates via email")
    form.nearby_hitchhikers_email.label.text = t("Email me about other hitchhikers who were close by")
    form.allow_messages.label.text = t("Let other hitchhikers message me (adds a Chat button to my profile)")
    form.message_email_notifications.label.text = t("Email me when I receive a new message")
    form.distance_unit.label.text = t("Distance units")
    form.distance_unit.choices = [(v, t(lbl)) for v, lbl in form.distance_unit.choices]
    form.submit.label.text = t("Submit")

    if form.validate_on_submit():
        updated_user = security.datastore.find_user(username=current_user.username)
        updated_user.gender = form.gender.data or None
        updated_user.year_of_birth = form.year_of_birth.data
        updated_user.hitchhiking_since = form.hitchhiking_since.data
        updated_user.origin_country = form.origin_country.data or None
        updated_user.origin_city = form.origin_city.data or None
        updated_user.hitchwiki_username = form.hitchwiki_username.data
        updated_user.trustroots_username = form.trustroots_username.data
        updated_user.email_notifications = form.email_notifications.data
        updated_user.nearby_hitchhikers_email = form.nearby_hitchhikers_email.data
        updated_user.allow_messages = form.allow_messages.data
        updated_user.message_email_notifications = form.message_email_notifications.data
        updated_user.distance_unit = form.distance_unit.data
        security.datastore.put(updated_user)
        security.datastore.commit()
        return redirect("/me")

    form.gender.data = current_user.gender
    form.year_of_birth.data = current_user.year_of_birth
    form.hitchhiking_since.data = current_user.hitchhiking_since
    form.origin_country.data = current_user.origin_country
    form.origin_city.data = current_user.origin_city
    form.hitchwiki_username.data = current_user.hitchwiki_username
    form.trustroots_username.data = current_user.trustroots_username
    form.email_notifications.data = current_user.email_notifications
    form.nearby_hitchhikers_email.data = current_user.nearby_hitchhikers_email
    form.allow_messages.data = current_user.allow_messages
    form.message_email_notifications.data = current_user.message_email_notifications
    form.distance_unit.data = current_user.distance_unit or "metric"

    return render_template("security/edit_user.html", form=form)


@user_bp.route("/user", methods=["GET"])
def get_user():
    """Endpoint to get the currently logged in user."""
    current_app.logger.info("Received request to get user.")

    # Check if the user is logged in
    if not current_user.is_anonymous:
        return jsonify({"logged_in": True, "username": current_user.username})
    else:
        return jsonify({"logged_in": False, "username": ""})


# The modal shows 10 rides and expands to the rest of this slice; beyond it we send the
# user to the full profile rather than shipping an unbounded ride list to every opener.
RIDES_IN_MODAL_CAP = 50


def _ride_places(d_tags):
    """Place names for the given rides, as {d_tag: RidePlace}.

    Looks up only the d_tags actually being rendered. An earlier version cached the whole
    corpus as a JSON blob; at ~70 000 rides that is ~7 MB on disk and ~33 MB of parsed
    dict resident in every waitress worker, to answer a question about 50 rides.

    Rows are absent until hitch/scripts/ride_places.py has run for a ride, so callers must
    treat a miss as "not geocoded yet" rather than an error.
    """
    tags = [t for t in d_tags if t]
    if not tags:
        return {}
    rows = RidePlace.query.filter(RidePlace.d_tag.in_(tags)).all()
    return {row.d_tag: row for row in rows}


def _ride_needs_detail(ride_info):
    """Whether this ride is worth topping up: editable AND either incomplete or missing
    its destination. Mirrors ridesNeedingDetails() in account.js so the avatar dot and the
    modal's "N rides could use more detail" line never disagree.

    Editable means type "own" — /ride?edit= only prefills rides we published, so an
    imported or co-hitchhiker ride has no way to be improved and must not be counted.
    """
    if ride_info.get("type") != "own":
        return False
    return ride_info.get("completion", 0) < 100 or ride_info.get("missing_destination")


@user_bp.route("/me/incomplete_rides.json", methods=["GET"])
def incomplete_rides_json():
    """How many of the user's rides still want more detail — for the avatar nudge dot.

    Its own endpoint, not part of /me.json, because account.js calls it on every page
    load (only when logged in) just to decide whether to light the dot, whereas /me.json
    is fetched only when the modal opens. Anonymous callers get 0 rather than a redirect.
    """
    # Anonymous users have no rides to nudge about; skip the query entirely.
    rides = [] if current_user.is_anonymous else _get_rides_for_user(current_user)
    count = sum(1 for ride in rides if _ride_needs_detail(ride))
    resp = jsonify({"count": count})
    # Per-user, like /me.json — never let a shared cache serve one user's count to another.
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@user_bp.route("/me.json", methods=["GET"])
def me_json():
    """Account data for the on-map account modal (issue #106).

    Anonymous callers get 200 {"logged_in": false} rather than the 302 to /login that
    /me serves: the modal renders its logged-out state from this response, and fetch()
    would silently follow the redirect and hand us a login page instead of JSON.
    """
    if current_user.is_anonymous:
        resp = jsonify({"logged_in": False})
    else:
        rides = _get_rides_for_user(current_user)
        visible = rides[:RIDES_IN_MODAL_CAP]
        # One bounded lookup for exactly the rides we are about to render.
        places = _ride_places([r.get("d_tag") for r in visible])
        shown = []
        for ride in visible:
            entry = {k: v for k, v in ride.items() if k not in ("submission_sort_key", "start_sort_key")}
            place = places.get(entry.get("d_tag"))
            entry["from_place"] = place.from_place if place else None
            entry["to_place"] = place.to_place if place else None
            # ISO alpha-2; the client renders it as a flag emoji.
            entry["from_cc"] = place.from_cc if place else None
            entry["to_cc"] = place.to_cc if place else None
            shown.append(entry)

        total_rides = current_user.total_rides or 0
        total_km = current_user.total_distance_km or 0
        partners = _distinct_partner_count(current_user.username)

        # Same ladders the /insights page renders, but only the tiers actually earned:
        # the modal celebrates what you have, and the full profile shows what's left.
        earned = [
            {"emoji": card["emoji"], "name": card["name"], "blurb": card["blurb"]}
            for card in _achievements({"rides": total_rides, "distance": total_km, "partners": partners})
            if card["earned"]
        ]

        resp = jsonify(
            {
                "logged_in": True,
                "username": current_user.username,
                "profile_url": "/me",
                "insights": {
                    "rides": total_rides,
                    "distance_km": total_km,
                    "waiting_min": current_user.total_waiting_time_min or 0,
                    "partners": partners,
                },
                "achievements": earned,
                "rides": shown,
                # Untruncated, so the UI can say "showing 50 of 231" and link to the profile.
                "rides_total": len(rides),
            }
        )
    # Per-user data. A shared cache storing this could serve one user's profile to
    # another — the exact failure mode the cache-control work had to fix once already.
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


# TODO: properly delete the user after their confirmation
@user_bp.route("/delete-user", methods=["GET"])
def delete_user():
    return f"To delete your account please send an email to {current_app.config['EMAIL']} with the subject 'Delete my account'."


@user_bp.route("/is_username_used/<username>", methods=["GET"])
def is_username_used(username):
    """Endpoint to check if a username is already used."""
    current_app.logger.info(f"Received request to check if username {username} is used.")

    user = security.datastore.find_user(username=username)

    if user:
        return jsonify({"used": True})
    else:
        return jsonify({"used": False})


@user_bp.route("/search_usernames", methods=["GET"])
def search_usernames():
    """Return usernames matching a query prefix, excluding the current user."""
    query = request.args.get("q", "").strip()
    if len(query) < 1:
        return jsonify([])

    exclude_username = None
    if not current_user.is_anonymous:
        exclude_username = current_user.username

    users = User.query.filter(User.username.ilike(f"{query}%")).limit(10).all()
    results = [u.username for u in users if u.username != exclude_username]
    return jsonify(results)


@user_bp.route("/me", methods=["GET"], defaults={"username": None, "is_me": True})
@user_bp.route("/account/<username>", methods=["GET"])
def show_account(username, is_me: bool = False):
    """Returns either the current account or the requested user

    Args:
        username: The user to show, None if current_user
        is_me: Whether the current_user should be shown, True if current_user
    """
    if is_me and current_user.is_anonymous:
        return redirect("/login")

    user = current_user if is_me else security.datastore.find_user(username=username)

    current_app.logger.info(
        f"Received request to show user account for {current_user.username}"
        if is_me
        else f"Received request to show user {username}."
    )

    # When the requested name doesn't belong to a registered user, still render the
    # account page using just the requested name as the username, so that rides
    # logged under that hitchhiker nickname (e.g. legacy / external sources) are
    # still browsable. Personal-profile fields are hidden via `user_known=False`.
    user_known = user is not None
    if not user_known:
        user = SimpleNamespace(
            username=username,
            gender=None,
            year_of_birth=None,
            hitchhiking_since=None,
            origin_city=None,
            origin_country=None,
            hitchwiki_username=None,
            trustroots_username=None,
        )

    # In-app notifications are private, so only load them when viewing your own page.
    # Capture them (newest first) before marking unread ones read, so the red bell on
    # the account button clears once the user has actually seen the list.
    notifications = []
    if is_me:
        notifications = (
            Notification.query.filter_by(user_id=current_user.id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .all()
        )
        if any(not n.is_read for n in notifications):
            Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
            db.session.commit()

    if is_me:
        rides_data = _get_rides_for_user(current_user)
    else:
        rides_data = _get_rides_for_user(user, include_pending_co=False, display_only=True)

    # Trips only exist for registered users (they hang off a user_id). Unregistered
    # hitchhiker stubs have no id, so skip the query for them.
    trips_data = _get_trips_for_user(user) if user_known else []

    single_source = _single_external_source(user.username)
    source_label = _EXTERNAL_SOURCE_LABELS.get(single_source)
    source_url_template = _EXTERNAL_SOURCE_PROFILE_URLS.get(single_source)
    source_url = source_url_template.format(username=quote(user.username, safe="")) if source_url_template else None
    # Unregistered stubs normally hide the Hitchwiki profile link, but for names whose rides
    # all came from Hitchwiki-derived sources the nickname *is* a Hitchwiki username, so keep it.
    show_hitchwiki_link = single_source in _HITCHWIKI_SOURCES

    age = (datetime.utcnow().year - user.year_of_birth) if user.year_of_birth else None

    # The follow button only makes sense on another registered user's page while logged
    # in. `can_follow` gates whether the button renders at all; `is_following` sets its
    # initial state so a reload reflects the stored relationship.
    can_follow = user_known and not is_me and not current_user.is_anonymous
    is_following = False
    if can_follow:
        is_following = Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first() is not None

    # The Chat button only shows on another registered user's page, while logged in, and
    # only if that user opted into receiving messages (allow_messages). Same gate the send
    # endpoint enforces server-side, so the button never appears where a POST would 403.
    can_message = user_known and not is_me and not current_user.is_anonymous and bool(user.allow_messages)

    return render_template(
        "security/account.html",
        user=user,
        is_me=is_me,
        rides=rides_data,
        trips=trips_data,
        notifications=notifications,
        user_known=user_known,
        source_label=source_label,
        source_url=source_url,
        show_hitchwiki_link=show_hitchwiki_link,
        age=age,
        can_follow=can_follow,
        is_following=is_following,
        can_message=can_message,
        # /account/<anything> answers 200 by design (see the stub above), which makes it
        # an unbounded URL space a crawler can wander forever -- and each page costs a
        # couple of seconds of database work. A name that belongs to no registered user
        # AND has no rides has nothing on it, so it is a soft 404: keep serving it to
        # whoever typed the URL, but keep it out of the index. Pages with rides on them,
        # registered or not, stay indexable -- those are real contributor profiles.
        noindex=not user_known and not rides_data,
    )


# Achievement ladders: (threshold, emoji, name, blurb). Each metric has several tiers;
# the user's progress bar always points at the lowest tier they haven't reached yet,
# and every tier below it renders as earned.
ACHIEVEMENT_LADDERS = [
    {
        "metric": "rides",
        "unit": "rides",
        "tiers": [
            (5, "👍", "Thumb Warmer", "Logged 5 rides — the thumb is officially calibrated."),
            (100, "🛣️", "Roadside Regular", "100 rides. Drivers start to recognise you."),
            (1000, "🏆", "Legend of the Hard Shoulder", "1000 rides. Songs will be written."),
        ],
    },
    {
        "metric": "distance",
        "unit": "km",
        "tiers": [
            (100, "🚗", "Out of Town", "100 km hitched — further than the bus goes."),
            (1000, "🌍", "Continental Drifter", "1000 km hitched, entirely on other people's fuel."),
            (10000, "🚀", "Quarter Way Round the World", "10 000 km — a quarter of the equator, thumb first."),
        ],
    },
    {
        "metric": "partners",
        "unit": "partners",
        "tiers": [
            (3, "🧍🧍", "Three's Company", "Hitchhiked with 3 different partners."),
            (10, "🎪", "Thumb Collective", "Hitchhiked with 10 different partners."),
        ],
    },
]


def _distinct_partner_count(username):
    """Number of distinct other hitchhikers this user has shared a logged ride with.

    A ride's `hitchhikers` list holds everyone who was on it, so partners are simply the
    other nicknames on rides where `username` appears. Unnamed co-riders are skipped: they
    are either missing a nickname or carry the "Anonymous" sentinel (same as show.py), and
    two anonymous co-riders can't be told apart, so counting them would be meaningless.
    """
    partners = set()
    for ride in _rides_by_hitchhiker(username):
        for h in (ride.content or {}).get("hitchhikers") or []:
            nickname = (h or {}).get("nickname") or ""
            if nickname.lower() not in ("", "anonymous", username.lower()):
                partners.add(nickname.lower())
    return len(partners)


def _ride_wait_minutes(ride):
    """Waiting time of a ride in minutes, or None. Same source as show.py: the first
    stop's ISO-8601 `waiting_duration` (e.g. "PT45M")."""
    stops = (ride.content or {}).get("stops") or []
    if not stops:
        return None
    duration = (stops[0].get("waiting_duration") or "").replace("PT", "").replace("M", "")
    try:
        return int(duration)
    except ValueError:
        return None


def _ride_duration_minutes(ride):
    """Time spent moving: the last stop's arrival minus the first stop's departure.

    Distinct from the waiting time, which is time spent stopped at the roadside. Either
    timestamp may be absent (the in-ride tracker records both; the historic form often
    does not), and a clock skew could make arrival precede departure — in every such case
    return None so the UI simply omits the figure rather than printing something wrong.
    """
    stops = (ride.content or {}).get("stops") or []
    if len(stops) < 2:
        return None
    departure = stops[0].get("departure_time")
    arrival = stops[-1].get("arrival_time")
    if not departure or not arrival:
        return None
    start = pd.to_datetime(departure, errors="coerce", utc=True)
    end = pd.to_datetime(arrival, errors="coerce", utc=True)
    if pd.isna(start) or pd.isna(end):
        return None
    minutes = (end - start).total_seconds() / 60
    return round(minutes) if minutes > 0 else None


def _ride_completion_pct(ride):
    """How complete this ride's driver/vehicle detail is, 0-100.

    Reuses the canonical weights (ride_score) rather than re-deriving a score, so the
    number a user sees on their ride list is the same one the in-ride sheet's meters
    showed while they logged it. The stored Nostr record uses the data-standard's shape
    (an occupant with was_driver, and mode_of_transportation), so map it back onto the
    scorer's field names. Age is scored on presence: we store year_of_birth, not an age.
    """
    content = ride.content or {}
    occupants = content.get("occupants") or []
    driver = next((o for o in occupants if o.get("was_driver")), {})
    transport = content.get("mode_of_transportation") or {}

    return score_fields(
        {
            "driver_reason_to_pick_up": driver.get("reasons_to_pick_up") or [],
            "driver_gender": driver.get("gender") or "",
            "driver_age": driver.get("year_of_birth") or "",
            "driver_origin_country": driver.get("origin_country") or "",
            "driver_languages": driver.get("languages") or [],
            "vehicle_kind": transport.get("kind") or "",
            "vehicle_license_plate_country": transport.get("license_plate_country") or "",
        }
    )["pct"]


def _ride_distance_km(info):
    """Pickup→destination distance of a ride in km, or None when it has no destination.

    Mirrors show.py: great-circle distance scaled by the road-detour factor, with rides
    under 1 km discarded as unrealistically short (they are treated as having no
    destination there, so a record must not be built out of one).
    """
    coords = (info["pickup_lat"], info["pickup_lon"], info["destination_lat"], info["destination_lon"])
    if any(c is None for c in coords):
        return None
    distance = float(haversine_np(*coords))
    return distance if distance >= 1 else None


def _ride_records(username):
    """The user's personal bests: their single longest ride and their single longest wait.

    Returns a dict of {"distance": record, "wait": record}, either of which is None when no
    ride carries that figure. Each record names the ride so the page can link to it.
    """
    records = {"distance": None, "wait": None}
    for ride in _rides_by_hitchhiker(username):
        info = _extract_ride_info(ride, "own")
        for key, value in (("distance", _ride_distance_km(info)), ("wait", _ride_wait_minutes(ride))):
            if value is None:
                continue
            best = records[key]
            if best is None or value > best["value"]:
                records[key] = {"value": value, "d_tag": info["d_tag"], "created": info["created"]}
    return records


def _achievements(values):
    """Turn raw per-metric totals into a flat list of achievement cards.

    `values` maps a ladder's metric name to the user's current total. Every tier gets a
    card so locked ones stay visible as a goal; `progress` is the share of the tier's
    threshold reached, clamped to 1 so an earned tier shows a full bar.
    """
    cards = []
    for ladder in ACHIEVEMENT_LADDERS:
        current = values.get(ladder["metric"], 0) or 0
        for threshold, emoji, name, blurb in ladder["tiers"]:
            cards.append(
                {
                    "emoji": emoji,
                    "name": t(name),
                    "blurb": t(blurb),
                    "current": min(current, threshold),
                    "target": threshold,
                    "unit": t(ladder["unit"]),
                    "earned": current >= threshold,
                    "progress": min(current / threshold, 1.0),
                }
            )
    return cards


@user_bp.route("/insights/<username>", methods=["GET"])
def show_insights(username):
    """Full insights page for a user: lifetime totals plus the achievement ladders.

    Only registered users have the precomputed lifetime totals (show.py writes them onto
    the `user` row), so an unknown hitchhiker nickname has nothing to show here.
    """
    user = security.datastore.find_user(username=username)
    if user is None:
        return redirect(url_for("user.show_account", username=username))

    total_rides = user.total_rides or 0
    total_km = user.total_distance_km or 0
    partners = _distinct_partner_count(user.username)

    return render_template(
        "insights.html",
        user=user,
        is_me=not current_user.is_anonymous and current_user.id == user.id,
        total_rides=total_rides,
        total_km=total_km,
        total_waiting_min=user.total_waiting_time_min or 0,
        partners=partners,
        records=_ride_records(user.username),
        achievements=_achievements({"rides": total_rides, "distance": total_km, "partners": partners}),
    )


def _toggle_follow(username, follow):
    """Shared follow/unfollow handler. Returns JSON with the resulting follow state."""
    if current_user.is_anonymous:
        return jsonify({"error": "login_required"}), 401

    target = security.datastore.find_user(username=username)
    if target is None:
        return jsonify({"error": "user_not_found"}), 404
    # Following yourself is meaningless; reject it so it never lands in the table.
    if target.id == current_user.id:
        return jsonify({"error": "cannot_follow_self"}), 400

    existing = Follow.query.filter_by(follower_id=current_user.id, followed_id=target.id).first()
    if follow and existing is None:
        db.session.add(Follow(follower_id=current_user.id, followed_id=target.id))
        db.session.commit()
        # Only notify on a genuinely new follow (not on repeat clicks), so the target
        # doesn't get a fresh notification each time someone re-follows them.
        notify_new_follower(target.id, current_user.username)
    elif not follow and existing is not None:
        db.session.delete(existing)
        db.session.commit()

    return jsonify({"following": follow})


@user_bp.route("/follow/<username>", methods=["POST"])
def follow_user(username):
    """Make the logged-in user follow `username`."""
    return _toggle_follow(username, follow=True)


@user_bp.route("/unfollow/<username>", methods=["POST"])
def unfollow_user(username):
    """Make the logged-in user stop following `username`."""
    return _toggle_follow(username, follow=False)


@user_bp.route("/contributors", methods=["GET"])
def contributors():
    """Legacy contributor ranking, superseded by /leaderboard.

    It counted rows in `points` -- the legacy hitchmap.com review table, which no
    longer exists in the production database, so every request 500s (Search Console
    reports these under "Server error (5xx)", once per language mirror). The page is
    linked from nowhere and cannot be repaired without the table; /leaderboard is the
    ranking built from the ride data we actually hold, so send callers there. A 301
    rather than a 404 because the URL is old enough to have inbound links.
    """
    return redirect(url_for(f"{request.blueprint}.leaderboard"), code=301)


@user_bp.route("/claim-review/<review_id>", methods=["GET", "POST"])
def claim_review(review_id: int):
    """Endpoint to claim a review."""
    current_app.logger.info(f"Received request to claim review {review_id}.")

    if current_user.is_anonymous:
        return redirect("/login")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "create table if not exists claims"
        + "(id integer primary key, "
        + "user_id integer, "
        + "review_id integer, "
        + "timestamp timestamp default current_timestamp)"
    )

    # Insert or replace existing entry
    query_result = cursor.execute(f"select user_id from points where id = {review_id}").fetchall()
    if len(query_result) == 0:
        error_message = "Review not found."
    if len(query_result) > 1:
        error_message = "Multiple reviews found."
    elif query_result[0][0] is not None:
        error_message = "Review already claimed."
    else:
        error_message = None

    if error_message:
        conn.close()
        return render_template("security/failed.html", message=error_message)

    claims_today = cursor.execute(
        f"select count(*) from claims where user_id = {current_user.id} and date(timestamp) = date('now')"
    ).fetchone()
    num_claims = claims_today[0] if claims_today else 0
    if num_claims >= current_app.config["MAX_CLAIMS_PER_DAY"]:
        reply = render_template(
            "security/failed.html", message=f"You can only claim {current_app.config['MAX_CLAIMS_PER_DAY']} reviews per day."
        )
    else:
        cursor.execute(f"update points set user_id = {current_user.id} where id = {review_id}")
        cursor.execute(f"insert or replace into claims (user_id, review_id) values ({current_user.id}, {review_id})")
        conn.commit()
        message = f"{num_claims + 1}/{current_app.config['MAX_CLAIMS_PER_DAY']} reviews claimed today."
        reply = render_template("security/success.html", message=message)

    conn.close()

    return reply


def _extract_ride_info(ride, ride_type):
    """Extract display info from a RideEvent row."""
    content = ride.content if ride.content else {}
    stops = content.get("stops") or []
    pickup_lat, pickup_lon = None, None
    destination_lat, destination_lon = None, None
    if stops:
        coords = stops[0].get("location", {})
        pickup_lat = coords.get("latitude")
        pickup_lon = coords.get("longitude")
        if len(stops) > 1:
            coords = stops[-1].get("location", {})
            destination_lat = coords.get("latitude")
            destination_lon = coords.get("longitude")
    # Display the user-supplied submission time (RFC 9557) on the card; leave it
    # blank when the ride has none rather than falling back to the Nostr event's
    # publish time (`created_at`), which is a different concept.
    submission_dt = pd.to_datetime(ride.submission_time, errors="coerce", utc=True) if ride.submission_time else None
    submission_display = submission_dt.strftime("%Y-%m-%d %H:%M") if submission_dt is not None and pd.notna(submission_dt) else ""
    submission_sort_key = submission_dt.value if submission_dt is not None and pd.notna(submission_dt) else None
    # When the ride actually happened (first stop's departure_time, RFC 9557) — a different
    # concept from submission_time, which is when the record was written. Trips are ordered
    # by this one, so a journey logged days afterwards still reads in the order it was
    # hitched, and a batch of rides typed in one sitting doesn't collapse into upload order.
    # None when the ride never recorded a start time; such a ride can't join a trip at all.
    departure = stops[0].get("departure_time") if stops else None
    start_dt = pd.to_datetime(departure, errors="coerce", utc=True) if departure else None
    start_display = start_dt.strftime("%Y-%m-%d %H:%M") if start_dt is not None and pd.notna(start_dt) else ""
    start_sort_key = start_dt.value if start_dt is not None and pd.notna(start_dt) else None
    info = {
        "type": ride_type,
        "d_tag": ride.d,
        "created": submission_display,
        "submission_sort_key": submission_sort_key,
        "start": start_display,
        "start_sort_key": start_sort_key,
        "rating": int(ride.rating) if ride.rating else 0,
        "comment": ride.comment or "",
        "pickup_lat": pickup_lat,
        "pickup_lon": pickup_lon,
        "destination_lat": destination_lat,
        "destination_lon": destination_lon,
    }
    # Surfaced by the account modal's ride list. None means "not recorded", and the UI
    # omits the stat rather than printing a misleading zero. _ride_distance_km reads the
    # coords off the info dict, so it has to run once the dict exists.
    info["wait_min"] = _ride_wait_minutes(ride)
    info["ride_min"] = _ride_duration_minutes(ride)
    distance = _ride_distance_km(info)
    info["distance_km"] = round(distance, 1) if distance is not None else None
    info["completion"] = _ride_completion_pct(ride)
    # A ride that never recorded where it ended is incomplete data the user can still fix,
    # so the modal flags it. A `no_ride` record is a give-up: the hitchhiker was never
    # picked up, so having no destination is correct there and must not be flagged. The
    # UI still labels it, just as a fact rather than a problem — hence both flags.
    gave_up = content.get("no_ride") is not None
    info["gave_up"] = gave_up
    info["missing_destination"] = destination_lat is None and not gave_up
    return info


def _norm_nickname(s):
    """MediaWiki-style: first letter is case-insensitive so "John" matches "john" and vice versa."""
    return (s[:1].upper() + s[1:]) if s else s


def _request_cached(key, build):
    """Memoize `build()` under `key` for the lifetime of one request.

    The profile views ask the same expensive question more than once per request:
    /account/<username> resolves _rides_by_hitchhiker twice (the ride list and the
    external-source badge), and _owner_deleted_dtags once per trip on top of that.

    Safe because nothing here is written and re-read within a single request — deleting a
    ride (main.py `delete_ride`) commits and redirects, so the next read of the deleted
    set is already a new request. Outside a request context the value is simply rebuilt,
    so scripts and tests importing these helpers are unaffected.
    """
    if not has_request_context():
        return build()
    cache = g.setdefault("_profile_query_cache", {})
    if key not in cache:
        cache[key] = build()
    return cache[key]


def _owner_deleted_dtags():
    """D-tags of rides their author deleted.

    Deleting a ride cannot remove the event from the Nostr relays, so the RideEvent row
    survives every fetch_nostr rebuild and "deleted" only means "stop showing it" (see
    OWNER_DELETE_REASON). show.py drops these from the map data; every profile-side view
    has to drop them too, or the owner keeps seeing a ride they deleted.
    """

    def build():
        rows = db.session.query(RideReport.ride_d_tag).filter_by(reason=OWNER_DELETE_REASON).all()
        return {d_tag for (d_tag,) in rows}

    return _request_cached("owner_deleted_dtags", build)


def _rides_by_hitchhiker(username):
    """RideEvent rows listing `username` among their hitchhikers, newest first.

    Rides deleted by their author are excluded.

    Cached per request: the json_each pre-filter below cannot use an index (it walks the
    `hitchhikers` array of every one of ~79k rides, ~2 s), and a single account page needs
    the answer more than once.
    """
    return _request_cached(("rides_by_hitchhiker", username), lambda: _query_rides_by_hitchhiker(username))


def _query_rides_by_hitchhiker(username):
    # Pre-filter in SQL using JSON1 so we don't load and JSON-parse every RideEvent in Python.
    # This is a permissive case-insensitive match; the Python filter below still applies the
    # exact MediaWiki-style _norm_nickname comparison for correctness.
    candidates = (
        db.session.query(RideEvent)
        .filter(
            text(
                "EXISTS (SELECT 1 FROM json_each(ride_event.hitchhikers) "
                "WHERE lower(json_extract(value, '$.nickname')) = lower(:uname))"
            )
        )
        .params(uname=username)
        .order_by(RideEvent.created_at.desc())
        .all()
    )
    normalized_username = _norm_nickname(username)
    deleted = _owner_deleted_dtags()
    return [
        ride
        for ride in candidates
        if ride.d not in deleted
        and normalized_username in [_norm_nickname(h.get("nickname")) for h in ((ride.content or {}).get("hitchhikers") or [])]
    ]


# Nostr `source` values of rides imported from other hitchhiking platforms, mapped to the
# short badge shown after a hitchhiker's name. Only applied when every ride under that name
# came from a single one of these sources, so visitors know the name is an external stub
# (e.g. a legacy hitchmap.com contributor) rather than a Hitchwiki Maps account.
_EXTERNAL_SOURCE_LABELS = {"hitchmap.com": "Hitchmap", "triphopping.com": "Triphopping"}

# Sources that host a public profile page per contributor, so the badge after the name can
# link back to the original account. `{username}` is filled with the URL-quoted nickname.
# Rendered nofollow+ugc: the nickname comes from user-submitted ride data, so we neither
# vouch for the target nor want to pass ranking to an unbounded set of external profiles.
_EXTERNAL_SOURCE_PROFILE_URLS = {"hitchmap.com": "https://hitchmap.com/account/{username}"}

# Sources whose ride nicknames are Hitchwiki usernames. A stub page for such a name is
# really that person's Hitchwiki account, so we still link to their Hitchwiki profile even
# though they never registered a Hitchwiki Maps account.
_HITCHWIKI_SOURCES = {"hitchwiki.org", "liftershalte.info"}


def _single_external_source(username):
    """The one source of a name whose rides all come from a single source, else None."""
    rides = _rides_by_hitchhiker(username)
    if not rides:
        return None
    sources = {ride.source for ride in rides}
    return next(iter(sources)) if len(sources) == 1 else None


def _get_rides_for_user(user, include_pending_co=True, display_only=False):
    """Return merged list of own rides and pending co-hitchhiker rides, newest first.

    `user` may be a real User object or any object with a `.username` attribute
    (e.g. a stub for an unregistered hitchhiker name found only in ride events).
    """
    username = user.username
    own_rides = []
    for ride in _rides_by_hitchhiker(username):
        # "own" is what puts an Edit link on the card, so it tracks what we can actually
        # republish — rides logged here plus the imports we own the Nostr key for — not
        # just rides whose source is this site. `display_only` is someone else's profile.
        ride_type = "own" if not display_only and ride_is_replaceable(ride) else "own_external"
        own_rides.append(_extract_ride_info(ride, ride_type))

    co_rides = []
    if include_pending_co:
        pending = CoHitchhiker.query.filter_by(co_hitchhiker=username, accepted="open").all()
        deleted = _owner_deleted_dtags()
        for ch in pending:
            if ch.nostr_ride_event_d_tag in deleted:
                continue
            ride = db.session.query(RideEvent).filter_by(d=ch.nostr_ride_event_d_tag).first()
            if ride:
                co_rides.append(_extract_ride_info(ride, "co_hitchhiker"))

    combined = own_rides + co_rides
    # Rides without a submission_time sort to the bottom regardless of direction:
    # `has_time=False` ranks before `True` when reverse=True, so those entries land last.
    combined.sort(
        key=lambda r: (r["submission_sort_key"] is not None, r["submission_sort_key"] or 0),
        reverse=True,
    )
    for r in combined:
        del r["submission_sort_key"]
    # `start_sort_key` deliberately survives: the trip builder filters on it to decide
    # which rides may be picked at all (see _selectable_rides_for_current_user).
    return combined


def _rides_for_trip(trip_id):
    """Resolve a trip's member d-tags into ride-info dicts, oldest first.

    Ordered by when each ride was *hitched* (`start_sort_key`), not by when it was
    submitted: legs of one journey are often typed up afterwards in whatever order they
    come to mind, and only the ride's own start time puts them back in travel order.
    Oldest first, because a trip is read the way it was travelled — first leg at the top,
    matching the route line drawn above it, which runs start → finish.
    Rides whose d-tag no longer resolves to a RideEvent (e.g. deleted on Nostr) and rides
    their author deleted are omitted. The internal `start_sort_key` is kept here (unlike
    `submission_sort_key` in _get_rides_for_user) because the trip route/date-span helpers
    need it to order rides chronologically. A ride with no start time can no longer be
    added to a trip, but rows predating that rule may still exist, so it is still handled.
    """
    members = TripRide.query.filter_by(trip_id=trip_id).all()
    deleted = _owner_deleted_dtags()
    wanted = [member.ride_d_tag for member in members if member.ride_d_tag not in deleted]
    # One query for the whole trip rather than one per member ride: a long trip is dozens
    # of rides, and a round trip to SQLite each is what made /account/<user> take 20 s for
    # the site's biggest trip (before `ride_event.d` was indexed, ~0.3 s apiece).
    by_dtag = {}
    for ride in db.session.query(RideEvent).filter(RideEvent.d.in_(wanted)).all() if wanted else []:
        by_dtag.setdefault(ride.d, ride)
    rides = [_extract_ride_info(ride, "trip") for d_tag in wanted if (ride := by_dtag.get(d_tag))]
    # `is None` ranks False (dated) before True, so undated legacy rides trail the
    # sequence instead of claiming the "first leg" slot at the top.
    rides.sort(key=lambda r: (r["start_sort_key"] is None, r["start_sort_key"] or 0))
    return rides


def _trip_date_span(rides):
    """Human-readable date range covering a trip's rides, or '' if none are dated.

    start_sort_key is epoch nanoseconds (pandas Timestamp.value)."""
    keys = [r["start_sort_key"] for r in rides if r.get("start_sort_key")]
    if not keys:
        return ""
    start, end = pd.Timestamp(min(keys)), pd.Timestamp(max(keys))
    if start.date() == end.date():
        return start.strftime("%-d %b %Y")
    if start.year != end.year:
        return f"{start.strftime('%-d %b %Y')} – {end.strftime('%-d %b %Y')}"
    if start.month != end.month:
        return f"{start.strftime('%-d %b')} – {end.strftime('%-d %b %Y')}"
    return f"{start.strftime('%-d')} – {end.strftime('%-d %b %Y')}"


def _trip_route_points(rides):
    """Ordered [{lat, lon}] tracing the trip oldest→newest.

    Each ride contributes its pickup then destination (when present); consecutive
    duplicate coordinates are collapsed so a shared spot isn't drawn twice.

    Same ordering as the ride list (_rides_for_trip), so the line and the cards below it
    tell the story in the same direction; undated legacy rides sort last either way."""
    ordered = sorted(rides, key=lambda r: (r.get("start_sort_key") is None, r.get("start_sort_key") or 0))
    pts = []
    for r in ordered:
        for lat, lon in ((r["pickup_lat"], r["pickup_lon"]), (r["destination_lat"], r["destination_lon"])):
            if lat is None or lon is None:
                continue
            p = {"lat": lat, "lon": lon}
            if not pts or pts[-1] != p:
                pts.append(p)
    return pts


def _trip_preview_description(owner, date_span, rides):
    parts = []
    if owner:
        parts.append(f"Trip by {owner.username}")
    else:
        parts.append("Hitchhiking trip")
    if date_span:
        parts.append(date_span)
    parts.append(f"{len(rides)} ride{'' if len(rides) == 1 else 's'}")
    return " · ".join(parts)


def _get_trips_for_user(user):
    """Return the user's trips (newest first) with rides, date span and route points.

    Each trip is a dict: {id, name, rides, date_span, points}. `points` drives the
    little route-map thumbnail on the profile; `date_span` labels it.
    """
    trips = Trip.query.filter_by(user_id=user.id).order_by(Trip.created_at.desc()).all()
    result = []
    for trip in trips:
        rides = _rides_for_trip(trip.id)
        result.append(
            {
                "id": trip.id,
                "name": trip.name,
                "rides": rides,
                "date_span": _trip_date_span(rides),
                "points": _trip_route_points(rides),
            }
        )
    return result


def _selectable_rides_for_current_user():
    """Rides the current user may put in a trip, plus how many were held back.

    Their own logged rides (incl. external), excluding pending co-hitchhiker invitations
    they haven't accepted — and excluding any ride with no recorded start time. A trip is
    ordered and drawn by when each ride was hitched, so a ride that never recorded that
    has no place in the sequence: it would land at one end of the list and pull the route
    line to whichever spot happened to sort first. The count of held-back rides is
    returned so the builder can say why a ride is missing instead of silently dropping it.
    """
    own = [r for r in _get_rides_for_user(current_user) if r["type"] in ("own", "own_external")]
    selectable = [r for r in own if r["start_sort_key"] is not None]
    return selectable, len(own) - len(selectable)


@user_bp.route("/create-trip", methods=["GET"])
def create_trip():
    """Render the trip builder for a brand-new trip."""
    if current_user.is_anonymous:
        return redirect("/login")
    rides, undated = _selectable_rides_for_current_user()
    return render_template("security/edit_trip.html", trip=None, rides=rides, undated_count=undated, selected_dtags=[])


@user_bp.route("/edit-trip/<int:trip_id>", methods=["GET"])
def edit_trip(trip_id):
    """Render the trip builder pre-filled for an existing trip (owner only)."""
    if current_user.is_anonymous:
        return redirect("/login")
    trip = db.session.get(Trip, trip_id)
    if trip is None or trip.user_id != current_user.id:
        return redirect("/me")
    selected = [tr.ride_d_tag for tr in TripRide.query.filter_by(trip_id=trip.id).all()]
    rides, undated = _selectable_rides_for_current_user()
    return render_template("security/edit_trip.html", trip=trip, rides=rides, undated_count=undated, selected_dtags=selected)


@user_bp.route("/save-trip", methods=["POST"])
def save_trip():
    """Create or update a trip and its ride membership, then redirect to the trip page."""
    if current_user.is_anonymous:
        return redirect("/login")

    trip_id = request.form.get("trip_id", type=int)
    name = (request.form.get("name") or "").strip() or "Untitled trip"
    description = (request.form.get("description") or "").strip() or None

    # Only accept d-tags that actually belong to the current user's rides, so a crafted
    # POST can't attach someone else's ride to a trip. dict.fromkeys de-dupes while
    # preserving order (the unique (trip_id, d_tag) constraint would otherwise trip up).
    # The same set also enforces the start-time rule (a ride with no recorded start time
    # is not selectable), so a hand-rolled POST can't smuggle an undated ride in either.
    # An older trip that already held one loses it on the next save — deliberate: the
    # membership rule is the same one everywhere rather than grandfathered per trip.
    valid_dtags = {r["d_tag"] for r in _selectable_rides_for_current_user()[0]}
    selected = [d for d in dict.fromkeys(request.form.getlist("ride_d_tags")) if d in valid_dtags]

    if trip_id:
        trip = db.session.get(Trip, trip_id)
        if trip is None or trip.user_id != current_user.id:
            return redirect("/me")
        trip.name = name
        trip.description = description
        # Membership is replaced wholesale on every save — simpler than diffing.
        TripRide.query.filter_by(trip_id=trip.id).delete()
    else:
        trip = Trip(user_id=current_user.id, name=name, description=description)
        db.session.add(trip)
        db.session.flush()  # assign trip.id before we reference it below

    for d_tag in selected:
        db.session.add(TripRide(trip_id=trip.id, ride_d_tag=d_tag))
    db.session.commit()

    return redirect(f"/trip/{trip.id}")


# ── Auto-grouped trips (in-ride tracker) ──────────────────────────────────────
# A tracked journey that produced more than one ride is grouped into a trip without
# being asked: those rides are consecutive legs of one hitch by construction, so making
# someone rebuild that grouping by hand in /create-trip is busywork. inride.js posts to
# /auto-trip once the journey's rides have all reached the server.

# Ceiling on the rides one auto-trip may contain. A real journey is a handful of legs;
# the cap stops a crafted POST sweeping an unbounded slice of the ride table into one page.
AUTO_TRIP_MAX_RIDES = 40
# Only recently published rides can be auto-grouped. The tracker posts within seconds of
# the last leg (or, offline, whenever the device next reconnects), so a generous window
# still covers every honest case while keeping historical rides out of reach.
AUTO_TRIP_MAX_AGE_S = 30 * 24 * 3600

# Photon's reverse lookup answers with the nearest *feature*, which at a roadside pickup
# is usually a street or a POI; its `city` field is filled in exactly then, so prefer that
# over `name`. Same preference order as route_preview.place_label — but deliberately with
# no reverse_geocoder fallback: that library loads a ~30 MB table into the process, and
# unlike route_preview (a short-lived subprocess) this runs inside the waitress workers,
# which this host has been OOM-killed over before.
_PLACE_TYPES = {"city", "town", "village", "hamlet", "municipality", "locality", "district", "county", "state"}
_PLACE_TIMEOUT_S = 4
_PLACE_USER_AGENT = "maps.hitchwiki.org trip naming (+https://maps.hitchwiki.org)"


def _place_label(lat, lon):
    """Nearest settlement name for a coordinate, or None when it can't be resolved."""
    try:
        response = requests.get(
            "https://photon.komoot.io/reverse",
            params={"lat": lat, "lon": lon, "lang": "en", "limit": 1},
            headers={"User-Agent": _PLACE_USER_AGENT},
            timeout=_PLACE_TIMEOUT_S,
        )
        response.raise_for_status()
        props = response.json()["features"][0]["properties"]
        if props.get("type") in _PLACE_TYPES and props.get("name"):
            return props["name"]
        for key in ("city", "locality", "district", "county", "state", "country"):
            if props.get(key):
                return props[key]
        return props.get("name") or None
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None


def _auto_trip_name(rides):
    """Generic name for an auto-grouped trip: "<start> → <end>, <Month Year>".

    Collapses to "<start>, <Month Year>" when both ends resolve to the same place or the
    journey never recorded where it ended, and to "Hitchhiking trip, <Month Year>" when
    nothing reverse-geocodes (Photon down, or a coordinate far from any settlement). The
    owner can rename it afterwards — this only has to beat "Untitled trip".
    """
    ordered = sorted(rides, key=lambda r: (r.get("start_sort_key") is None, r.get("start_sort_key") or 0))
    points = _trip_route_points(ordered)
    start = _place_label(points[0]["lat"], points[0]["lon"]) if points else None
    end = _place_label(points[-1]["lat"], points[-1]["lon"]) if len(points) > 1 else None

    where = f"{start} → {end}" if start and end and end != start else (start or "Hitchhiking trip")
    keys = [r["start_sort_key"] for r in ordered if r.get("start_sort_key")]
    when = pd.Timestamp(min(keys)) if keys else pd.Timestamp.now()
    # Trip.name is VARCHAR(255); place names are short but the cap keeps a pathological
    # Photon answer from being silently truncated by the database instead.
    return f"{where}, {when.strftime('%B %Y')}"[:255]


def _ride_hitchhiker_nicknames(ride):
    """Nicknames listed on a ride event ("Anonymous" for an unattributed one)."""
    return [(h or {}).get("nickname") for h in ((ride.content or {}).get("hitchhikers") or [])]


def _may_auto_group(ride, user):
    """Whether `user` (possibly anonymous) may put `ride` into an auto-trip.

    A logged-in hitchhiker has to be listed on the ride. An anonymous visitor has no
    identity to check against, so the only rides they can group are ones with no named
    hitchhiker at all — which is exactly what an anonymous journey produces, and stops a
    crafted POST bundling someone else's attributed rides onto a trip page.
    """
    nicknames = _ride_hitchhiker_nicknames(ride)
    if user.is_anonymous:
        return bool(nicknames) and all(n == ANONYMOUS_NICKNAME for n in nicknames)
    return _norm_nickname(user.username) in [_norm_nickname(n) for n in nicknames if n]


def _trip_payload(trip, created):
    return {"ok": True, "trip_id": trip.id, "name": trip.name, "url": f"/trip/{trip.id}", "created": created}


@user_bp.route("/auto-trip", methods=["POST"])
def auto_trip():
    """Group the rides of one finished in-ride journey into a trip. Form in, JSON out.

    Returns the existing trip untouched when any of the rides is already in one, so the
    client's offline retry can repeat the call without minting duplicate trips.
    """
    raw = [d.strip() for d in (request.form.get("ride_d_tags") or "").split(",")]
    d_tags = [d for d in dict.fromkeys(raw) if d][:AUTO_TRIP_MAX_RIDES]
    if len(d_tags) < 2:
        return jsonify({"ok": False, "error": "need at least two rides"}), 400

    # Already grouped — this is a repeat of a call that did land. Hand back the same trip
    # rather than creating a second one holding the same rides.
    already = TripRide.query.filter(TripRide.ride_d_tag.in_(d_tags)).first()
    if already:
        trip = db.session.get(Trip, already.trip_id)
        if trip:
            return jsonify(_trip_payload(trip, created=False))

    cutoff = int(time.time()) - AUTO_TRIP_MAX_AGE_S
    rides = [
        ride
        for d_tag in d_tags
        if (ride := db.session.query(RideEvent).filter_by(d=d_tag).first()) is not None
        and (ride.created_at or 0) >= cutoff
        and _may_auto_group(ride, current_user)
    ]
    # Same rule the manual builder enforces: a trip is ordered by when each ride was
    # hitched, so a ride with no start time can't be in one. The tracker records a start
    # time for every leg it logs, so this only bites a leg whose clock data went missing.
    infos = [info for ride in rides if (info := _extract_ride_info(ride, "trip"))["start_sort_key"] is not None]
    dated = {info["d_tag"] for info in infos}
    rides = [ride for ride in rides if ride.d in dated]
    if len(rides) < 2:
        return jsonify({"ok": False, "error": "no groupable rides"}), 400

    trip = Trip(
        # None for an anonymous journey: there is no account to own it. See models.Trip.
        user_id=None if current_user.is_anonymous else current_user.id,
        name=_auto_trip_name(infos),
        description=None,
    )
    db.session.add(trip)
    db.session.flush()  # assign trip.id before we reference it below
    for ride in rides:
        db.session.add(TripRide(trip_id=trip.id, ride_d_tag=ride.d))
    db.session.commit()
    return jsonify(_trip_payload(trip, created=True))


@user_bp.route("/delete-trip/<int:trip_id>", methods=["POST"])
def delete_trip(trip_id):
    """Delete a trip and its ride membership (owner only)."""
    if current_user.is_anonymous:
        return redirect("/login")
    trip = db.session.get(Trip, trip_id)
    if trip and trip.user_id == current_user.id:
        TripRide.query.filter_by(trip_id=trip.id).delete()
        db.session.delete(trip)
        db.session.commit()
    return redirect("/me")


@user_bp.route("/trip/<int:trip_id>", methods=["GET"])
def show_trip(trip_id):
    """Public trip detail page: name, date span, a route map and all the trip's rides."""
    trip = db.session.get(Trip, trip_id)
    if trip is None:
        return redirect("/")
    # An auto-grouped anonymous trip has no user_id; session.get(User, None) is an error,
    # not a miss, so the guard has to come first. The template already renders ownerless.
    owner = db.session.get(User, trip.user_id) if trip.user_id else None
    is_owner = not current_user.is_anonymous and current_user.id == trip.user_id
    rides = _rides_for_trip(trip.id)
    date_span = _trip_date_span(rides)
    return render_template(
        "security/trip.html",
        trip=trip,
        owner=owner,
        rides=rides,
        is_owner=is_owner,
        date_span=date_span,
        points=_trip_route_points(rides),
        preview_description=_trip_preview_description(owner, date_span, rides),
        preview_image_url=url_for("user.trip_preview_image", trip_id=trip.id, _external=True),
    )


@user_bp.route("/trip/<int:trip_id>/preview.png", methods=["GET"])
def trip_preview_image(trip_id):
    """Social preview image for a trip.

    Link preview crawlers do not execute the Leaflet JavaScript on the trip page,
    so this endpoint renders a small static route map server-side for og:image.
    """
    trip = db.session.get(Trip, trip_id)
    if trip is None:
        return redirect("/")

    owner = db.session.get(User, trip.user_id) if trip.user_id else None
    rides = _rides_for_trip(trip.id)
    points = _trip_route_points(rides)
    description = _trip_preview_description(owner, _trip_date_span(rides), rides)
    png = _render_trip_preview_png(trip.name, description, points)
    response = send_file(png, mimetype="image/png", max_age=3600)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


# Social-preview image geometry.
PREVIEW_W, PREVIEW_H = 1200, 630
PREVIEW_FOOTER_H = 122
TILE_SIZE = 256
PREVIEW_BG = (233, 229, 217)  # fallback fill where tiles are missing


def _render_trip_preview_png(title, description, points):
    """Render the og:image: a real OSM-tiled map with the trip's road route drawn on it.

    Crawlers don't run the page's Leaflet JS, so we stitch OSM tiles and draw the
    OSRM road geometry server-side. Any network failure degrades gracefully (missing
    tiles leave the paper-coloured fill; failed routing falls back to straight lines).
    """
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (PREVIEW_W, PREVIEW_H), PREVIEW_BG)

    if points:
        zoom = _pick_preview_zoom(points)
        # Center the route in the area above the footer.
        world = [_lonlat_to_world(p["lon"], p["lat"], zoom) for p in points]
        cx = (min(w[0] for w in world) + max(w[0] for w in world)) / 2
        cy = (min(w[1] for w in world) + max(w[1] for w in world)) / 2
        origin_x = cx - PREVIEW_W / 2
        origin_y = cy - (PREVIEW_H - PREVIEW_FOOTER_H) / 2

        _paste_tiles(img, zoom, origin_x, origin_y)

        draw = ImageDraw.Draw(img, "RGBA")

        # Route geometry following actual roads (OSRM), or the waypoints as a fallback.
        geometry = _osrm_route_geometry(points) or [(p["lon"], p["lat"]) for p in points]
        route_px = [_world_to_px(_lonlat_to_world(lon, lat, zoom), origin_x, origin_y) for lon, lat in geometry]
        if len(route_px) > 1:
            draw.line(route_px, fill=(255, 255, 255, 235), width=11, joint="curve")
            draw.line(route_px, fill=(45, 125, 210, 255), width=6, joint="curve")

        # Spot markers: green start, red end, blue in between.
        marker_px = [_world_to_px(w, origin_x, origin_y) for w in world]
        for idx, (x, y) in enumerate(marker_px):
            color = (47, 179, 68) if idx == 0 else (217, 72, 72) if idx == len(marker_px) - 1 else (45, 125, 210)
            _draw_marker(draw, x, y, color)
    else:
        draw = ImageDraw.Draw(img, "RGBA")
        title_font, _, _ = _preview_fonts()
        draw.text((PREVIEW_W / 2, 280), "No route points yet", fill=(112, 107, 96), font=title_font, anchor="mm")

    _draw_preview_footer(img, title, description)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _draw_marker(draw, x, y, color):
    draw.ellipse([x - 11, y - 11, x + 11, y + 11], fill=(255, 255, 255, 255))
    draw.ellipse([x - 7, y - 7, x + 7, y + 7], fill=color + (255,))


def _draw_preview_footer(img, title, description):
    from PIL import Image, ImageDraw

    title_font, desc_font, small_font = _preview_fonts()
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle([0, PREVIEW_H - PREVIEW_FOOTER_H, PREVIEW_W, PREVIEW_H], fill=(255, 255, 255, 235))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"), (0, 0))

    draw = ImageDraw.Draw(img)
    draw.text((72, PREVIEW_H - 78), _truncate_text(title, 60), fill=(34, 34, 34), font=title_font)
    draw.text((72, PREVIEW_H - 36), _truncate_text(description, 95), fill=(85, 85, 85), font=desc_font)
    draw.text((PREVIEW_W - 72, PREVIEW_H - 36), "maps.hitchwiki.org", fill=(102, 102, 102), font=small_font, anchor="rm")


def _preview_fonts():
    from matplotlib import font_manager
    from PIL import ImageFont

    try:
        bold = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans", weight="bold"))
        regular = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans"))
        return ImageFont.truetype(bold, 40), ImageFont.truetype(regular, 26), ImageFont.truetype(regular, 22)
    except Exception:
        default = ImageFont.load_default()
        return default, default, default


def _osrm_route_geometry(points):
    """Fetch the driving route geometry (list of (lon, lat)) through the trip's spots.

    Returns None on any failure so the caller can fall back to straight segments.
    """
    if len(points) < 2:
        return None
    sampled = _sample_evenly(points, 25)  # keep the OSRM demo URL and load reasonable
    coords = ";".join(f"{p['lon']},{p['lat']}" for p in sampled)
    url = f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson"
    try:
        import requests

        resp = requests.get(url, timeout=8, headers={"User-Agent": "hitchmap-trip-preview"})
        data = resp.json()
        return [(c[0], c[1]) for c in data["routes"][0]["geometry"]["coordinates"]]
    except Exception:
        return None


def _sample_evenly(items, max_count):
    if len(items) <= max_count:
        return items
    step = (len(items) - 1) / (max_count - 1)
    return [items[round(i * step)] for i in range(max_count)]


def _pick_preview_zoom(points):
    """Largest tile zoom at which the route bbox fits the on-image map area (with margins)."""
    if len(points) < 2:
        return 11
    inner_w = PREVIEW_W - 140
    inner_h = PREVIEW_H - PREVIEW_FOOTER_H - 120
    for zoom in range(18, 0, -1):
        world = [_lonlat_to_world(p["lon"], p["lat"], zoom) for p in points]
        bbox_w = max(w[0] for w in world) - min(w[0] for w in world)
        bbox_h = max(w[1] for w in world) - min(w[1] for w in world)
        if bbox_w <= inner_w and bbox_h <= inner_h:
            return zoom
    return 1


def _lonlat_to_world(lon, lat, zoom):
    """Web-mercator world pixel coordinates (top-left origin) at a given tile zoom."""
    import math

    lat = max(min(float(lat), 85.05112878), -85.05112878)
    n = 2**zoom
    x = (float(lon) + 180.0) / 360.0 * n * TILE_SIZE
    rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(rad) + 1.0 / math.cos(rad)) / math.pi) / 2.0 * n * TILE_SIZE
    return x, y


def _world_to_px(world, origin_x, origin_y):
    return (world[0] - origin_x, world[1] - origin_y)


def _paste_tiles(img, zoom, origin_x, origin_y):
    """Download the OSM tiles covering the view window and paste them into `img`."""
    import math
    from concurrent.futures import ThreadPoolExecutor

    n = 2**zoom
    tx_min = math.floor(origin_x / TILE_SIZE)
    tx_max = math.floor((origin_x + PREVIEW_W) / TILE_SIZE)
    ty_min = math.floor(origin_y / TILE_SIZE)
    ty_max = math.floor((origin_y + PREVIEW_H) / TILE_SIZE)

    jobs = []
    for tx in range(tx_min, tx_max + 1):
        for ty in range(ty_min, ty_max + 1):
            if ty < 0 or ty >= n:
                continue
            jobs.append((tx, ty))

    def fetch(job):
        tx, ty = job
        return job, _fetch_tile(zoom, tx % n, ty)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for (tx, ty), tile in pool.map(fetch, jobs):
            if tile is None:
                continue
            px = int(round(tx * TILE_SIZE - origin_x))
            py = int(round(ty * TILE_SIZE - origin_y))
            img.paste(tile, (px, py))


def _fetch_tile(zoom, x, y):
    from PIL import Image

    url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
    try:
        import requests

        resp = requests.get(url, timeout=5, headers={"User-Agent": "hitchmap-trip-preview"})
        if resp.status_code != 200:
            return None
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception:
        return None


def _truncate_text(value, max_len):
    value = str(value or "")
    return value if len(value) <= max_len else value[: max_len - 1].rstrip() + "…"


# TODO: check if all data from the new co-hitchhiker added to the new event and that no data was lost
@user_bp.route("/accept-co-hitchhiking-ride/<ride_d_tag>", methods=["GET", "POST"])
def accept_co_hitchhiker(ride_d_tag: str):
    if current_user.is_anonymous:
        return redirect("/login")

    conn = get_db()
    cursor = conn.cursor()

    # TODO: only allow if the current user is actually listed as co-hitchhiker
    cursor.execute(
        "UPDATE co_hitchhiker SET accepted = 'yes' WHERE nostr_ride_event_d_tag = ? and co_hitchhiker = ?",
        (ride_d_tag, current_user.username),
    )
    conn.commit()
    conn.close()

    ### Update the Nostr event

    # Find the nostr event
    ride_row = db.session.query(RideEvent).filter_by(d=ride_d_tag).first()

    # manipulate it
    ride_record: dict = HitchhikingRecord.model_validate(ride_row.content)
    this_hitchhiker = construct_hitchhiker_from_current_user()
    print(f"Adding co-hitchhiker {this_hitchhiker} to ride {ride_d_tag}")
    ride_record.hitchhikers.append(this_hitchhiker)
    # post the updated event
    poster = HitchhikingDataStandardToNostrPoster()
    _ = poster.post(ride_record=ride_record, tags=ride_row.tags)
    poster.close()

    return redirect("/me")


@user_bp.route("/reject-co-hitchhiking-ride/<ride_d_tag>", methods=["POST"])
def reject_co_hitchhiker(ride_d_tag: str):
    if current_user.is_anonymous:
        return redirect("/login")

    CoHitchhiker.query.filter_by(nostr_ride_event_d_tag=ride_d_tag, co_hitchhiker=current_user.username).update(
        {"accepted": "no"}
    )
    db.session.commit()

    return redirect("/me")


@user_bp.route("/my-rides", methods=["GET"])
def my_rides():
    return redirect("/me")


def _download_filename(username, extension):
    """A safe download filename. The username reaches a Content-Disposition header, and
    nicknames are free text — anything outside this set would let a crafted name inject
    header syntax or path separators."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in username) or "rides"
    return f"hitchwiki-maps-{safe}.{extension}"


@user_bp.route("/me/downloads", methods=["GET"])
def my_downloads():
    """Private export page: your own rides, in formats you can take elsewhere.

    Only ever renders for the logged-in user's own data — there is no
    /account/<username>/downloads counterpart, because a person's full ride
    records (exact coordinates, times, driver details) are theirs to export,
    even though each individual ride is public on the map.
    """
    if current_user.is_anonymous:
        return redirect("/login")

    rides = _rides_by_hitchhiker(current_user.username)
    with_destination = sum(1 for r in rides if len((r.content or {}).get("stops") or []) > 1)
    return render_template(
        "security/downloads.html",
        user=current_user,
        ride_count=len(rides),
        route_count=with_destination,
        waypoint_count=len(rides) - with_destination,
    )


@user_bp.route("/me/rides.gpx", methods=["GET"])
def my_rides_gpx():
    """Every ride logged under the current user's name, as GPX."""
    if current_user.is_anonymous:
        return redirect("/login")

    rides = _rides_by_hitchhiker(current_user.username)
    body = rides_gpx(rides, current_user.username)
    return Response(
        body,
        mimetype="application/gpx+xml",
        headers={
            "Content-Disposition": f'attachment; filename="{_download_filename(current_user.username, "gpx")}"',
            # Private data behind a login — never let a shared proxy hold a copy.
            "Cache-Control": "private, no-store",
        },
    )


@user_bp.route("/me/rides.json", methods=["GET"])
def my_rides_json():
    """The same rides as the raw signed Nostr events.

    The lossless companion to the GPX: GPX can only carry what fits a waypoint or
    a route (plus our extensions), while this is byte-for-byte what was published,
    signature included, so it can be verified or re-imported elsewhere.
    """
    if current_user.is_anonymous:
        return redirect("/login")

    rides = _rides_by_hitchhiker(current_user.username)
    payload = [
        {
            "id": r.id,
            "kind": r.kind,
            "pubkey": r.pubkey,
            "sig": r.sig,
            "created_at": r.created_at,
            "tags": r.tags,
            "content": r.content,
        }
        for r in rides
    ]
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=1),
        mimetype="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{_download_filename(current_user.username, "json")}"',
            "Cache-Control": "private, no-store",
        },
    )


def _read_leaderboard_json(filename):
    """Read a precomputed leaderboard file from dist/. show.py regenerates these every
    minute so /leaderboard doesn't scan and haversine every ride on each request (that
    made the page slow). Returns [] if the file isn't generated yet."""
    path = os.path.join(get_dirs()["dist"], filename)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


@user_bp.route("/leaderboard", methods=["GET"])
def leaderboard():
    """Show all users sorted by number of rides, highest first."""
    all_users = User.query.order_by(User.username).all()

    # Count rides per nickname directly in SQL via json_each — avoids loading every
    # RideEvent into Python and JSON-parsing each one. Group case-insensitively, which
    # is at least as permissive as the previous MediaWiki-style first-letter rule.
    # Rides deleted by their author still exist on Nostr (and so in ride_event), but must
    # not count towards anyone's total.
    rows = db.session.execute(
        text(
            "SELECT lower(json_extract(value, '$.nickname')) AS nick, COUNT(*) AS n "
            "FROM ride_event, json_each(ride_event.hitchhikers) "
            "WHERE json_extract(value, '$.nickname') IS NOT NULL "
            "AND ride_event.d NOT IN (SELECT ride_d_tag FROM ride_report WHERE reason = :deleted) "
            "GROUP BY nick"
        ),
        {"deleted": OWNER_DELETE_REASON},
    ).all()
    counts_by_lower = {nick: n for nick, n in rows if nick}

    ride_counts = {u.username: counts_by_lower.get(u.username.lower(), 0) for u in all_users}
    ranked = sorted(all_users, key=lambda u: ride_counts[u.username], reverse=True)
    return render_template(
        "leaderboard.html",
        users=ranked,
        ride_counts=ride_counts,
        longest_rides=_read_leaderboard_json("longest_rides.json"),
        longest_24h=_read_leaderboard_json("longest_24h.json"),
    )


@user_bp.route("/races", methods=["GET"])
def races():
    """Podiums for the city-to-city races defined in RACES.md.

    Standings are precomputed by show.py into dist/races.json — ranking every hitchhiker's
    ride chains per race is far too heavy for a request. Which races are *shown* is decided
    here rather than there, so a race opens and closes on its date instead of on the next
    cron run: only races running now or starting within the next month.
    """
    return render_template("races.html", races=current_races(_read_leaderboard_json("races.json")))
