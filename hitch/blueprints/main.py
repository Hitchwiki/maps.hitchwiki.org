import math
import os
import re
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
)
from flask_security import current_user

from hitch.blueprints.publish_ride import create_record_from_custom_object
from hitch.blueprints.utils.post_hitchhiking_ride_to_nostr import HitchhikingDataStandardToNostrPoster
from hitch.extensions import db
from hitch.helpers import get_db
from hitch.models import CoHitchhiker, RideEvent, RoutingSearch, User
from hitch.scripts.routing import routing

main_bp = Blueprint("main", __name__)

THIS_NOSTR_SOURCE = os.getenv("THIS_NOSTR_SOURCE", "yourdomain.com")
THIS_DATA_LICENSE=os.getenv("THIS_DATA_LICENSE", "odbl")

def _user_owns_ride(ride, user):
    """Check if the current user owns this ride."""
    if user.is_anonymous:
        return False

    # Check if source matches our source
    content = ride.content or {}
    if content.get("source") != "maps.hitchwiki.org":
        return False

    # Check if current user is one of the hitchhikers
    hitchhikers = content.get("hitchhikers", [])
    user_nicknames = [hitchhiker.get("nickname") for hitchhiker in hitchhikers]
    return user.username in user_nicknames


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
        hide_account_button=current_app.config.get("HIDE_ACCOUNT_BUTTON", False)
    )


@main_bp.route("/recent")
def recent_spots():
    """Show the last 100 added rides in card format."""
    rides = (
        db.session.query(RideEvent)
        .filter(RideEvent.submission_time.isnot(None))
        .order_by(RideEvent.submission_time.desc())
        .limit(100)
        .all()
    )
    ride_list = []
    for ride in rides:
        content = ride.content if ride.content else {}
        stops = content.get("stops") or []
        pickup_lat, pickup_lon = None, None
        if stops:
            coords = stops[0].get("location", {})
            pickup_lat = coords.get("latitude")
            pickup_lon = coords.get("longitude")
        hitchhikers = content.get("hitchhikers") or []
        nickname = hitchhikers[0].get("nickname", "Anonymous") if hitchhikers else "Anonymous"
        ride_list.append(
            {
                "d_tag": ride.d,
                "created": pd.to_datetime(ride.created_at, unit="s").strftime("%Y-%m-%d %H:%M") if ride.created_at else "N/A",
                "rating": int(ride.rating) if ride.rating else 0,
                "comment": ride.comment or "",
                "pickup_lat": pickup_lat,
                "pickup_lon": pickup_lon,
                "hitchhiker_name": nickname,
            }
        )
    return render_template("recent.html", rides=ride_list)


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
            last_loc = (stops[-1].get("location") or {})
            dest_lat = last_loc.get("latitude")
            dest_lon = last_loc.get("longitude")

    signal_methods = []
    for sig in content.get("signals") or []:
        for method in sig.get("methods") or []:
            if method not in signal_methods:
                signal_methods.append(method)

    hitchhikers = [
        {"nickname": h.get("nickname") or "Anonymous", "gender": h.get("gender")}
        for h in (content.get("hitchhikers") or [])
    ]

    distance_km = None
    if pickup_lat is not None and dest_lat is not None and pickup_lon is not None and dest_lon is not None:
        # Haversine
        lat1, lon1, lat2, lon2 = map(math.radians, [pickup_lat, pickup_lon, dest_lat, dest_lon])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        distance_km = 2 * 6371 * math.asin(math.sqrt(a))

    submission_dt = None
    if ride.submission_time:
        submission_dt = ride.submission_time
    elif ride.created_at:
        submission_dt = datetime.utcfromtimestamp(ride.created_at).isoformat() + "Z"

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
        "submission_time": submission_dt,
        "source": content.get("source") or ride.source,
        "distance_km": distance_km,
        "is_owner": _user_owns_ride(ride, current_user),
    }
    return render_template("ride_detail.html", ride=ride_view)


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
                    "pickup_lat": "",
                    "pickup_lon": "",
                    "destination_lat": "",
                    "destination_lon": "",
                    "wait": "",
                    "signal": "",
                    "datetime_ride": "",
                    "co_hitchhiker": "",
                }

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

                # Extract signal from signals[0].methods
                signals = content.get("signals", [])
                if signals:
                    methods = signals[0].get("methods", [])
                    signal_map = {
                        ("sign",): "sign",
                        ("thumb",): "thumb",
                        ("asking",): "ask",
                    }
                    ride_data["signal"] = signal_map.get(tuple(methods), "")

                # Requirement: co-hitchhikers already on a ride cannot be removed when editing,
                # only new ones can be added. "Already present" means either:
                # (a) in the nostr event's hitchhikers list (already accepted, published to Nostr), or
                # (b) in the CoHitchhiker table with accepted="open" (invited, pending response).
                current_nickname = current_user.username if not current_user.is_anonymous else None
                all_hitchhikers = content.get("hitchhikers", [])
                hitchhikers_on_nostr = {
                    h.get("nickname") for h in all_hitchhikers
                    if h.get("nickname") and h.get("nickname") != current_nickname and h.get("nickname") != "Anonymous"
                }
                # Anonymous hitchhikers are always co-hitchhikers (creator must be
                # logged in to edit, so they are never "Anonymous" themselves)
                anon_count = sum(1 for h in all_hitchhikers if h.get("nickname") == "Anonymous")
                pending_invites = {
                    c.co_hitchhiker for c in db.session.query(CoHitchhiker).filter_by(
                        nostr_ride_event_d_tag=edit_d_tag, accepted="open"
                    ).all()
                }
                locked_co_hitchhikers = sorted(hitchhikers_on_nostr | pending_invites)
                all_co = locked_co_hitchhikers + ["Anonymous"] * anon_count
                ride_data["co_hitchhiker"] = ",".join(all_co)
                ride_data["co_hitchhiker_locked"] = ",".join(locked_co_hitchhikers)

        return render_template("ride_form.html", ride_data=ride_data)

    # POST request - process the form submission (same logic as experience route)
    data = request.form
    # make the ImmutableMultiDict into a normal dict
    data = data.to_dict(flat=True)
    rating = int(data["rate"])
    data["wait"] = int(data["wait"]) if data["wait"] != "" else None
    wait = data["wait"]
    assert wait is None or wait >= 0, f"Wait time must be non-negative, the wait time is {wait}."
    assert rating in range(1, 6), f"Rating must be between 1 and 5, the rating is {rating}."
    comment = None if data["comment"] == "" else data["comment"]
    assert comment is None or len(comment) < 10000, (
        f"Comment must be less than 10000 characters, the comment length is {len(comment)}."
    )

    signal = data["signal"] if data["signal"] != "null" else None
    assert signal in ["thumb", "sign", "ask", None], (
        f"Signal must be one of thumb, sign, ask - the signal is {signal}."
    )


    # TODO: store IP and nostr event d tag pairs in a db table to prevent abuse
    # ip = request.headers.getlist("X-Real-IP")[-1] if request.headers.getlist("X-Real-IP") else request.remote_addr

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
        if not existing_ride or not _user_owns_ride(existing_ride, current_user):
            return redirect("/#error")  # User doesn't own this ride

        # Create new record with updated form data to get updated fields
        # TODO: define license properly instead of using "xxx"
        updated_record = create_record_from_custom_object(custom_object=data, source=THIS_NOSTR_SOURCE, license=THIS_DATA_LICENSE)

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
        d_tag = poster.post(ride_record=record)
        poster.close()

    ### Co-hitchhikers
    # Requirement: co-hitchhikers already on a ride cannot be removed when editing, only new
    # ones can be added. We achieve this by only inserting co-hitchhikers not already in the DB.
    if "co_hitchhiker" in data and data["co_hitchhiker"] != "":
        current_username = current_user.username if not current_user.is_anonymous else None
        existing_co = {
            c.co_hitchhiker for c in db.session.query(CoHitchhiker).filter_by(nostr_ride_event_d_tag=d_tag).all()
        }
        for ch in data["co_hitchhiker"].split(","):
            username = ch.strip()
            if username == "" or username == "Anonymous":
                continue  # anonymous hitchhikers are handled in the Nostr event, not in CoHitchhiker
            if username == current_username:
                continue  # skip self
            if username in existing_co:
                continue  # already present, cannot be removed so no need to re-add
            if not User.query.filter_by(username=username).first():
                continue  # skip non-existent users
            co_hitchhiker = CoHitchhiker(
                nostr_ride_event_d_tag=d_tag,
                co_hitchhiker=username,
                accepted="open",
            )
            db.session.add(co_hitchhiker)
        db.session.commit()

    return redirect("/#success")


# Report duplicates
@main_bp.route("/report-duplicate", methods=["POST"])
def report_duplicate():
    data = request.form

    now = str(datetime.datetime.utcnow())

    ip = request.headers.getlist("X-Real-IP")[-1] if request.headers.getlist("X-Real-IP") else request.remote_addr

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


@main_bp.route("/route", methods=["POST"])
def calculate_route():
    """Calculate route between two points using the routing algorithm."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        start = data.get("start")  # [lat, lon]
        end = data.get("end")  # [lat, lon]

        if not start or not end:
            return jsonify({"error": "Both start and end coordinates are required"}), 400

        if len(start) != 2 or len(end) != 2:
            return jsonify({"error": "Coordinates must be [latitude, longitude] arrays"}), 400

        try:
            start_coords = (float(start[0]), float(start[1]))
            end_coords = (float(end[0]), float(end[1]))
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid coordinate format"}), 400

        # Validate coordinate ranges (now start[0] is lat, start[1] is lon)
        if not (-90 <= start[0] <= 90 and -180 <= start[1] <= 180):
            return jsonify({"error": "Invalid start coordinates"}), 400
        if not (-90 <= end[0] <= 90 and -180 <= end[1] <= 180):
            return jsonify({"error": "Invalid end coordinates"}), 400

        # Log the search request
        db.session.add(RoutingSearch(
            start_lat=start_coords[0], start_lon=start_coords[1],
            start_name=data.get("start_name", "")[:255],
            end_lat=end_coords[0], end_lon=end_coords[1],
            end_name=data.get("end_name", "")[:255],
        ))
        db.session.commit()

        # Call the routing function
        try:
            _, route, total_time_minutes = routing(A=start_coords, B=end_coords)

            # Check if we got valid results
            if not route or len(route) < 2:
                return jsonify(
                    {"error": "No route found between these points. Try coordinates closer to areas with hitchhiking activity."}
                ), 404

            # Format the route for the frontend
            route_coords = [[coord[0], coord[1]] for coord in route]  # [lat, lon] format

            # Convert time to more readable format
            hours = int(total_time_minutes // 60)
            minutes = int(total_time_minutes % 60)

            return jsonify(
                {
                    "route": route_coords,
                    "total_time_hours": hours,
                    "total_time_formatted": f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m",
                    "num_stops": len(route),
                }
            )

        except Exception as routing_error:
            error_msg = str(routing_error)
            if "not found in graph" in error_msg:
                return jsonify(
                    {
                        "error": """No hitchhiking data found near your start or end point.
                        Try coordinates closer to major cities or highways where hitchhikers are active."""
                    }
                ), 404
            else:
                raise  # Re-raise other routing errors

    except Exception as e:
        current_app.logger.error(f"Routing error: {str(e)}")
        return jsonify({"error": "Internal server error during route calculation"}), 500
