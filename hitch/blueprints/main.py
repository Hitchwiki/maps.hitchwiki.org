import math
import os
from datetime import datetime, timezone

import pandas as pd
import requests
from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
)
from flask_security import current_user

from hitch.blueprints.publish_ride import create_record_from_custom_object
from hitch.blueprints.utils.post_hitchhiking_ride_to_nostr import HitchhikingDataStandardToNostrPoster
from hitch.extensions import db
from hitch.helpers import get_db
from hitch.models import CoHitchhiker

main_bp = Blueprint("main", __name__)

THIS_NOSTR_SOURCE = os.getenv("THIS_NOSTR_SOURCE", "yourdomain.com")


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
    """Dedicated ride form page after destination selection."""
    if request.method == "GET":
        # Get ride data from URL parameters passed from JavaScript
        coords = request.args.get('coords', '')
        destination_given = request.args.get('destination_given', 'false') == 'true'
        
        # Parse coordinates for display
        dest_text = "unknown destination"
        if coords:
            parts = coords.split(',')
            if len(parts) >= 4 and destination_given:
                try:
                    lat, lon, dest_lat, dest_lon = map(float, parts[:4])
                    dest_text = f"{dest_lat:.4f}, {dest_lon:.4f}"
                except (ValueError, TypeError):
                    pass
        
        # Prepare context for the form
        context = {
            'coords': coords,
            'destination_given': destination_given,
            'dest_text': dest_text
        }
        
        return render_template("ride_form.html", **context)
    
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
    assert comment is None or len(comment) < 10000, f"Comment must be less than 10000 characters, the comment length is {len(comment)}."

    signal = data["signal"] if data["signal"] != "null" else None
    assert signal in ["thumb", "sign", "ask", "ask-sign", None], f"Signal must be one of thumb, sign, ask, ask-sign, the signal is {signal}."

    datetime_ride = data["datetime_ride"]

    now = str(datetime.now(timezone.utc))

    ip = request.headers.getlist("X-Real-IP")[-1] if request.headers.getlist("X-Real-IP") else request.remote_addr

    lat, lon, dest_lat, dest_lon = map(float, data["coords"].split(","))

    assert -90 <= lat <= 90, f"Invalid latitude: {lat}"
    assert -180 <= lon <= 180, f"Invalid longitude: {lon}"
    assert (-90 <= dest_lat <= 90 and -180 <= dest_lon <= 180) or (math.isnan(dest_lat) and math.isnan(dest_lon)), (
        f"Invalid destination coordinates: {dest_lat}, {dest_lon}"
    )

    for _i in range(10):
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            {
                "lat": lat,
                "lon": lon,
                "format": "json",
                "zoom": 3,
                "email": current_app.config["EMAIL"],
            },
        )
        if resp.ok:
            break
        else:
            current_app.logger.info(resp)

    res = resp.json()
    country = "XZ" if "error" in res else res["address"]["country_code"].upper()

    ride_row = {
        "rating": rating,
        "wait": wait,
        "comment": comment,
        "nickname": None,
        "datetime": now,
        "ip": ip,
        "reviewed": False,
        "banned": False,
        "lat": lat,
        "dest_lat": dest_lat,
        "lon": lon,
        "dest_lon": dest_lon,
        "country": country,
        "signal": signal,
        "ride_datetime": datetime_ride,
        "user_id": current_user.id if not current_user.is_anonymous else None,
    }

    ### Publish ride to Nostr
    poster = HitchhikingDataStandardToNostrPoster()
    record = create_record_from_custom_object(custom_object=data, source="maps.hitchwiki.org", license="xxx")
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
