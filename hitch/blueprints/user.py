import io
import json
import os
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file, url_for
from flask_security import current_user
from sqlalchemy import text

from hitch.blueprints.publish_ride import construct_hitchhiker_from_current_user
from hitch.blueprints.utils.hitchhiking_data_standard_pydantic_model import HitchhikingRecord
from hitch.blueprints.utils.notifications import notify_new_follower
from hitch.blueprints.utils.post_hitchhiking_ride_to_nostr import HitchhikingDataStandardToNostrPoster
from hitch.extensions import db, security
from hitch.forms import UserEditForm
from hitch.helpers import get_db, get_dirs
from hitch.models import CoHitchhiker, Follow, Notification, RideEvent, Trip, TripRide, User

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

THIS_NOSTR_SOURCE = os.getenv("THIS_NOSTR_SOURCE", "maps.hitchwiki.org")

user_bp = Blueprint("user", __name__)


@user_bp.route("/edit-user", methods=["GET", "POST"])
def form():
    if current_user.is_anonymous:
        return redirect("/login")

    form = UserEditForm()

    if form.validate_on_submit():
        updated_user = security.datastore.find_user(username=current_user.username)
        updated_user.gender = form.gender.data
        updated_user.year_of_birth = form.year_of_birth.data
        updated_user.hitchhiking_since = form.hitchhiking_since.data
        updated_user.origin_country = form.origin_country.data
        updated_user.origin_city = form.origin_city.data
        updated_user.hitchwiki_username = form.hitchwiki_username.data
        updated_user.trustroots_username = form.trustroots_username.data
        updated_user.email_notifications = form.email_notifications.data
        updated_user.nearby_hitchhikers_email = form.nearby_hitchhikers_email.data
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

    age = (datetime.utcnow().year - user.year_of_birth) if user.year_of_birth else None

    # The follow button only makes sense on another registered user's page while logged
    # in. `can_follow` gates whether the button renders at all; `is_following` sets its
    # initial state so a reload reflects the stored relationship.
    can_follow = user_known and not is_me and not current_user.is_anonymous
    is_following = False
    if can_follow:
        is_following = (
            Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first() is not None
        )

    return render_template(
        "security/account.html",
        user=user,
        is_me=is_me,
        rides=rides_data,
        trips=trips_data,
        notifications=notifications,
        user_known=user_known,
        age=age,
        can_follow=can_follow,
        is_following=is_following,
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
    query = """select
            u.username AS hitchhiker,
            COUNT(*) AS total_contributions
        from points p left join user u on p.user_id = u.id
        where p.user_id is not null
        group by p.user_id
        order by total_contributions desc"""
    overall_contributions = pd.read_sql(
        query,
        get_db(),
    )
    overall_contributions.index = overall_contributions.index + 1

    query = """select
            u.username AS hitchhiker,
            COUNT(*) AS total_contributions
        from points p left join user u on p.user_id = u.id
        where p.user_id is not null
            and strftime('%Y-%m', p.datetime) = strftime('%Y-%m', 'now')
        group by p.user_id
        order by total_contributions desc;"""
    monthly_contributions = pd.read_sql(
        query,
        get_db(),
    )
    monthly_contributions.index = monthly_contributions.index + 1

    return render_template(
        "security/contributors.html",
        is_logged_in=not current_user.is_anonymous,
        overall_contributions=overall_contributions.to_html(),
        short_overall_contributions=overall_contributions.head(10).to_html(),
        monthly_contributions=monthly_contributions.to_html(),
        short_monthly_contributions=monthly_contributions.head(10).to_html(),
    )


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
    return {
        "type": ride_type,
        "d_tag": ride.d,
        "created": submission_display,
        "submission_sort_key": submission_sort_key,
        "rating": int(ride.rating) if ride.rating else 0,
        "comment": ride.comment or "",
        "pickup_lat": pickup_lat,
        "pickup_lon": pickup_lon,
        "destination_lat": destination_lat,
        "destination_lon": destination_lon,
    }


def _get_rides_for_user(user, include_pending_co=True, display_only=False):
    """Return merged list of own rides and pending co-hitchhiker rides, newest first.

    `user` may be a real User object or any object with a `.username` attribute
    (e.g. a stub for an unregistered hitchhiker name found only in ride events).
    """
    username = user.username
    # Pre-filter in SQL using JSON1 so we don't load and JSON-parse every RideEvent in Python.
    # This is a permissive case-insensitive match; the Python loop below still applies the
    # exact MediaWiki-style _norm comparison for correctness.
    candidate_query = (
        db.session.query(RideEvent)
        .filter(
            text(
                "EXISTS (SELECT 1 FROM json_each(ride_event.hitchhikers) "
                "WHERE lower(json_extract(value, '$.nickname')) = lower(:uname))"
            )
        )
        .params(uname=username)
        .order_by(RideEvent.created_at.desc())
    )
    all_rides = candidate_query.all()

    # MediaWiki-style: first letter is case-insensitive so "John" matches "john" and vice versa
    def _norm(s):
        return (s[:1].upper() + s[1:]) if s else s

    normalized_username = _norm(username)
    own_rides = []
    for ride in all_rides:
        content = ride.content if ride.content else {}
        nicknames = [_norm(h.get("nickname")) for h in (content.get("hitchhikers") or [])]
        if normalized_username in nicknames:
            ride_type = "own_external" if display_only or content.get("source") != THIS_NOSTR_SOURCE else "own"
            own_rides.append(_extract_ride_info(ride, ride_type))

    co_rides = []
    if include_pending_co:
        pending = CoHitchhiker.query.filter_by(co_hitchhiker=username, accepted="open").all()
        for ch in pending:
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
    return combined


def _rides_for_trip(trip_id):
    """Resolve a trip's member d-tags into ride-info dicts, newest first.

    Rides whose d-tag no longer resolves to a RideEvent (e.g. deleted on Nostr) are
    omitted. The internal `submission_sort_key` is kept here (unlike _get_rides_for_user)
    because the trip route/date-span helpers need it to order rides chronologically.
    """
    members = TripRide.query.filter_by(trip_id=trip_id).all()
    rides = [
        _extract_ride_info(ride, "trip")
        for member in members
        if (ride := db.session.query(RideEvent).filter_by(d=member.ride_d_tag).first())
    ]
    rides.sort(
        key=lambda r: (r["submission_sort_key"] is not None, r["submission_sort_key"] or 0),
        reverse=True,
    )
    return rides


def _trip_date_span(rides):
    """Human-readable date range covering a trip's rides, or '' if none are dated.

    submission_sort_key is epoch nanoseconds (pandas Timestamp.value)."""
    keys = [r["submission_sort_key"] for r in rides if r.get("submission_sort_key")]
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
    duplicate coordinates are collapsed so a shared spot isn't drawn twice."""
    ordered = sorted(
        rides, key=lambda r: (r.get("submission_sort_key") is not None, r.get("submission_sort_key") or 0)
    )
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
    """Rides the current user may put in a trip: their own logged rides (incl. external),
    excluding pending co-hitchhiker invitations they haven't accepted."""
    return [r for r in _get_rides_for_user(current_user) if r["type"] in ("own", "own_external")]


@user_bp.route("/create-trip", methods=["GET"])
def create_trip():
    """Render the trip builder for a brand-new trip."""
    if current_user.is_anonymous:
        return redirect("/login")
    return render_template(
        "security/edit_trip.html", trip=None, rides=_selectable_rides_for_current_user(), selected_dtags=[]
    )


@user_bp.route("/edit-trip/<int:trip_id>", methods=["GET"])
def edit_trip(trip_id):
    """Render the trip builder pre-filled for an existing trip (owner only)."""
    if current_user.is_anonymous:
        return redirect("/login")
    trip = db.session.get(Trip, trip_id)
    if trip is None or trip.user_id != current_user.id:
        return redirect("/me")
    selected = [tr.ride_d_tag for tr in TripRide.query.filter_by(trip_id=trip.id).all()]
    return render_template(
        "security/edit_trip.html", trip=trip, rides=_selectable_rides_for_current_user(), selected_dtags=selected
    )


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
    valid_dtags = {r["d_tag"] for r in _selectable_rides_for_current_user()}
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
    owner = db.session.get(User, trip.user_id)
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

    owner = db.session.get(User, trip.user_id)
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
        route_px = [
            _world_to_px(_lonlat_to_world(lon, lat, zoom), origin_x, origin_y) for lon, lat in geometry
        ]
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
    draw.text(
        (PREVIEW_W - 72, PREVIEW_H - 36), "maps.hitchwiki.org", fill=(102, 102, 102), font=small_font, anchor="rm"
    )


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

    CoHitchhiker.query.filter_by(
        nostr_ride_event_d_tag=ride_d_tag, co_hitchhiker=current_user.username
    ).update({"accepted": "no"})
    db.session.commit()

    return redirect("/me")


@user_bp.route("/my-rides", methods=["GET"])
def my_rides():
    return redirect("/me")


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
    rows = db.session.execute(
        text(
            "SELECT lower(json_extract(value, '$.nickname')) AS nick, COUNT(*) AS n "
            "FROM ride_event, json_each(ride_event.hitchhikers) "
            "WHERE json_extract(value, '$.nickname') IS NOT NULL "
            "GROUP BY nick"
        )
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
