import io
import os
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file, url_for
from flask_security import current_user
from sqlalchemy import text

from hitch.blueprints.publish_ride import construct_hitchhiker_from_current_user
from hitch.blueprints.utils.hitchhiking_data_standard_pydantic_model import HitchhikingRecord
from hitch.blueprints.utils.post_hitchhiking_ride_to_nostr import HitchhikingDataStandardToNostrPoster
from hitch.extensions import db, security
from hitch.forms import UserEditForm
from hitch.helpers import get_db
from hitch.models import CoHitchhiker, Follow, RideEvent, Trip, TripRide, User

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


def _render_trip_preview_png(title, description, points):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure(figsize=(12, 6.3), dpi=100, facecolor="#f4f1ea")
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(0, 1200)
    ax.set_ylim(0, 630)

    # Subtle paper-map background.
    ax.add_patch(_plot_rect(0, 0, 1200, 630, "#f4f1ea"))
    for x in range(-100, 1300, 90):
        ax.plot([x, x + 260], [0, 630], color="#e1ddd2", linewidth=1.2, alpha=0.55)
    for y in range(20, 660, 80):
        ax.plot([0, 1200], [y, y + 35], color="#e8e3d7", linewidth=1, alpha=0.7)

    map_box = (72, 86, 1056, 420)
    if points:
        route = _project_trip_points(points, map_box)
        if len(route) > 1:
            xs, ys = zip(*route)
            ax.plot(
                xs,
                ys,
                color="#ffffff",
                linewidth=12,
                solid_capstyle="round",
                solid_joinstyle="round",
                alpha=0.95,
            )
            ax.plot(xs, ys, color="#2d7dd2", linewidth=7, solid_capstyle="round", solid_joinstyle="round")
        for idx, (x, y) in enumerate(route):
            marker_color = "#2fb344" if idx == 0 else ("#d94848" if idx == len(route) - 1 else "#2d7dd2")
            ax.scatter([x], [y], s=190, color="#ffffff", linewidth=0, zorder=4)
            ax.scatter([x], [y], s=94, color=marker_color, edgecolors="#ffffff", linewidths=2.5, zorder=5)
    else:
        ax.text(600, 292, "No route points yet", ha="center", va="center", fontsize=30, color="#706b60")

    ax.add_patch(_plot_rect(0, 508, 1200, 122, "#ffffff", alpha=0.9))
    ax.text(
        72,
        585,
        _truncate_text(title, 70),
        ha="left",
        va="center",
        fontsize=34,
        fontweight="bold",
        color="#222222",
    )
    ax.text(72, 538, _truncate_text(description, 110), ha="left", va="center", fontsize=21, color="#555555")
    ax.text(1128, 538, "maps.hitchwiki.org", ha="right", va="center", fontsize=18, color="#666666")

    buf = io.BytesIO()
    canvas.print_png(buf)
    buf.seek(0)
    return buf


def _plot_rect(x, y, width, height, color, alpha=1):
    from matplotlib.patches import Rectangle

    return Rectangle((x, y), width, height, facecolor=color, edgecolor="none", alpha=alpha)


def _project_trip_points(points, box):
    left, bottom, width, height = box
    mercator = [(_lon_to_x(p["lon"]), _lat_to_y(p["lat"])) for p in points]
    xs = [p[0] for p in mercator]
    ys = [p[1] for p in mercator]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    if max_x == min_x:
        max_x += 0.01
        min_x -= 0.01
    if max_y == min_y:
        max_y += 0.01
        min_y -= 0.01

    scale = min(width / (max_x - min_x), height / (max_y - min_y)) * 0.78
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    out = []
    for x, y in mercator:
        px = left + width / 2 + (x - cx) * scale
        py = bottom + height / 2 + (y - cy) * scale
        out.append((px, py))
    return out


def _lon_to_x(lon):
    return float(lon)


def _lat_to_y(lat):
    import math

    lat = max(min(float(lat), 85.05112878), -85.05112878)
    rad = math.radians(lat)
    return math.log(math.tan(math.pi / 4 + rad / 2))


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
    return render_template("leaderboard.html", users=ranked, ride_counts=ride_counts)
