import os

import pandas as pd
from flask import Blueprint, current_app, jsonify, redirect, render_template, request
from flask_security import current_user
from sqlalchemy import text

from hitch.blueprints.publish_ride import construct_hitchhiker_from_current_user
from hitch.blueprints.utils.hitchhiking_data_standard_pydantic_model import HitchhikingRecord
from hitch.blueprints.utils.post_hitchhiking_ride_to_nostr import HitchhikingDataStandardToNostrPoster
from hitch.extensions import db, security
from hitch.forms import UserEditForm
from hitch.helpers import get_db
from hitch.models import CoHitchhiker, RideEvent

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
    from hitch.models import User

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

    # TODO: Proper 404
    if user is None:
        return "User not found."

    if is_me:
        rides_data = _get_rides_for_user(current_user)
    else:
        rides_data = _get_rides_for_user(user, include_pending_co=False, display_only=True)

    return render_template("security/account.html", user=user, is_me=is_me, rides=rides_data)


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
    return {
        "type": ride_type,
        "d_tag": ride.d,
        "created": pd.to_datetime(ride.created_at, unit="s").strftime("%Y-%m-%d %H:%M") if ride.created_at else "N/A",
        "created_at": ride.created_at or 0,
        "rating": int(ride.rating) if ride.rating else 0,
        "comment": ride.comment or "",
        "pickup_lat": pickup_lat,
        "pickup_lon": pickup_lon,
        "destination_lat": destination_lat,
        "destination_lon": destination_lon,
    }


def _get_rides_for_user(user, include_pending_co=True, display_only=False):
    """Return merged list of own rides and pending co-hitchhiker rides, newest first."""
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
        .params(uname=user.username)
        .order_by(RideEvent.created_at.desc())
    )
    all_rides = candidate_query.all()

    # MediaWiki-style: first letter is case-insensitive so "John" matches "john" and vice versa
    def _norm(s):
        return (s[:1].upper() + s[1:]) if s else s

    normalized_username = _norm(user.username)
    own_rides = []
    for ride in all_rides:
        content = ride.content if ride.content else {}
        nicknames = [_norm(h.get("nickname")) for h in (content.get("hitchhikers") or [])]
        if normalized_username in nicknames:
            ride_type = "own_external" if display_only or content.get("source") != THIS_NOSTR_SOURCE else "own"
            own_rides.append(_extract_ride_info(ride, ride_type))

    co_rides = []
    if include_pending_co:
        pending = CoHitchhiker.query.filter_by(co_hitchhiker=user.username, accepted="open").all()
        for ch in pending:
            ride = db.session.query(RideEvent).filter_by(d=ch.nostr_ride_event_d_tag).first()
            if ride:
                co_rides.append(_extract_ride_info(ride, "co_hitchhiker"))

    combined = own_rides + co_rides
    combined.sort(key=lambda r: r["created_at"], reverse=True)
    for r in combined:
        del r["created_at"]
    return combined


@user_bp.route("/co-hitchhiking-rides", methods=["GET", "POST"])
def co_hitchhiking_rides():
    return redirect("/me")


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
    from hitch.models import User

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
