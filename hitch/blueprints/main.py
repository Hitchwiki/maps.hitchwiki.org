import math
import os
from datetime import datetime, timezone

import pandas as pd
import requests
from flask import (
    Blueprint,
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
from hitch.models import CoHitchhiker, RideEvent
from hitch.scripts.routing import routing

main_bp = Blueprint("main", __name__)

THIS_NOSTR_SOURCE = os.getenv("THIS_NOSTR_SOURCE", "yourdomain.com")


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
@main_bp.route("/", defaults={"map_variation": None})
@main_bp.route("/<any(light, with_destination):map_variation>")
@main_bp.route("/<any(index, light, with_destination):map_variation>.html")
def render_map(map_variation):
    return render_template("map.html", map_variation=map_variation)


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
                    if len(stops) > 0:
                        first_stop = stops[0]
                        coords = first_stop.get("location", {}) or first_stop.get("coordinates", {})
                        ride_data["pickup_lat"] = coords.get("latitude", "")
                        ride_data["pickup_lon"] = coords.get("longitude", "")
                    if len(stops) > 1:
                        last_stop = stops[-1]
                        coords = last_stop.get("location", {}) or last_stop.get("coordinates", {})
                        ride_data["destination_lat"] = coords.get("latitude", "")
                        ride_data["destination_lon"] = coords.get("longitude", "")

                # Extract other fields from content if available
                if "wait" in content:
                    ride_data["wait"] = content["wait"]
                if "signal" in content:
                    ride_data["signal"] = content["signal"]
                if "datetime_ride" in content:
                    ride_data["datetime_ride"] = content["datetime_ride"]
                if "co_hitchhiker" in content:
                    ride_data["co_hitchhiker"] = content["co_hitchhiker"]

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
    assert signal in ["thumb", "sign", "ask", "ask-sign", None], (
        f"Signal must be one of thumb, sign, ask, ask-sign, the signal is {signal}."
    )

    datetime_ride = data["datetime_ride"]

    now = str(datetime.now(timezone.utc))

    ip = request.headers.getlist("X-Real-IP")[-1] if request.headers.getlist("X-Real-IP") else request.remote_addr

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

    # for _i in range(10):
    #     resp = requests.get(
    #         "https://nominatim.openstreetmap.org/reverse",
    #         {
    #             "lat": lat,
    #             "lon": lon,
    #             "format": "json",
    #             "zoom": 3,
    #             "email": current_app.config["EMAIL"],
    #         },
    #     )
    #     if resp.ok:
    #         break
    #     else:
    #         current_app.logger.info(resp)

    # res = resp.json()
    # country = "XZ" if "error" in res else res["address"]["country_code"].upper()

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
        updated_record = create_record_from_custom_object(custom_object=data, source=THIS_NOSTR_SOURCE, license="xxx")

        # post the updated event (maintaining all original tags including d tag)
        poster = HitchhikingDataStandardToNostrPoster()
        _ = poster.post(ride_record=updated_record, tags=existing_ride.tags)
        poster.close()
        d_tag = edit_d_tag  # Keep the same d_tag
    else:
        # This is a new ride - normal flow
        record = create_record_from_custom_object(custom_object=data, source=THIS_NOSTR_SOURCE, license="xxx")

        poster = HitchhikingDataStandardToNostrPoster()
        d_tag = poster.post(ride_record=record)
        poster.close()

    ### Co-hitchhikers
    # TODO: verify that all usernames exist in User table
    if "co_hitchhiker" in data and data["co_hitchhiker"] != "":
        for ch in data["co_hitchhiker"].split(","):
            if ch.strip() != "":
                co_hitchhiker = CoHitchhiker(
                    nostr_ride_event_d_tag=d_tag,
                    co_hitchhiker=ch.strip(),
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
