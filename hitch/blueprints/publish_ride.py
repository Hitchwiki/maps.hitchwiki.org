"""
An example of how to take a ride that was just recorded
e.g. on a hitchhiking application with opinionated fields that were collected by the application,
transform it into the defined standard and to post it to Nostr so that others can access it.
"""

import logging

import pandas as pd
from flask_security import current_user

from hitch.blueprints.utils.hitchhiking_data_standard_pydantic_model import (
    Hitchhiker,
    HitchhikingRecord,
    Location,
    Signal,
    Stop,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

### Define functions that create the objects demanded by this standard from the possibly unique data that is used in your dataset


def map_signal(signal: str) -> Signal:
    if signal is None or pd.isna(signal) or signal == "":
        return None

    if signal == "sign":
        return Signal(
            methods=["sign"],
        )
    elif signal == "thumb":
        return Signal(
            methods=["thumb"],
        )
    elif signal == "ask":
        return Signal(
            methods=["asking"],
        )
    else:
        return None


def map_gender(gender: str) -> str | None:
    if gender is None or pd.isna(gender) or gender == "":
        return None

    gender_map = {
        "Male": "male",
        "Female": "female",
        "Non-Binary": "non_binary",
        "Prefer not to say": "prefer_not_to_say",
    }
    return gender_map.get(gender)


def construct_hitchhiker_from_current_user() -> Hitchhiker:
    hitchhiker = Hitchhiker(
        origin_location=current_user.origin_city if hasattr(current_user, "origin_city") else None,
        origin_country=current_user.origin_country if hasattr(current_user, "origin_country") else None,
        year_of_birth=current_user.year_of_birth if hasattr(current_user, "year_of_birth") else None,
        gender=map_gender(current_user.gender) if hasattr(current_user, "gender") else None,
        languages=None,
        was_driver=None,
        nickname=current_user.username,
        hitchhiking_since=current_user.hitchhiking_since if hasattr(current_user, "hitchhiking_since") else None,
        reasons_to_hitchhike=None,
    )

    return hitchhiker


### Define one function that takes single rides from your dataset and builds objects that follow this standard from them
### Again, here the function is a bit special because we are dealing with multiple datasets actually


def create_record_from_custom_object(custom_object: dict, source: str, license: str) -> HitchhikingRecord:
    """Caters for setup of hitchmap.com on 2025/08/31."""
    lat = float(custom_object["pickup_lat"]) if custom_object.get("pickup_lat") else None
    lon = float(custom_object["pickup_lon"]) if custom_object.get("pickup_lon") else None
    dest_lat = float(custom_object["destination_lat"]) if custom_object.get("destination_lat") else None
    dest_lon = float(custom_object["destination_lon"]) if custom_object.get("destination_lon") else None

    stops = [
        Stop(
            location=Location(
                latitude=lat,
                longitude=lon,
                is_exact=True,
            ),
            departure_time=pd.to_datetime(custom_object["datetime_ride"]).strftime("%Y-%m-%dT%H:%M:%S")
            if pd.notna(custom_object["datetime_ride"]) and custom_object["datetime_ride"] != ""
            else None,
            arrival_time=None,
            waiting_duration=f"PT{int(custom_object['wait'])}M" if pd.notna(custom_object["wait"]) else None,
        ),
    ]
    if pd.notna(dest_lat) and pd.notna(dest_lon):
        stops.append(
            Stop(
                location=Location(
                    latitude=dest_lat,
                    longitude=dest_lon,
                    is_exact=False,
                )
            )
        )

    # logger.info(custom_object["signal"], type(custom_object["signal"]))
    signals = (
        [map_signal(custom_object["signal"])]
        if custom_object["signal"] != "" and custom_object["signal"] is not None and custom_object["signal"] != "null"
        else None
    )
    # logger.info(f"mapped signals: {signals}", type(signals), type(signals[0]) if signals is not None else None)
    if signals is not None and len(signals) == 1 and pd.notna(custom_object["wait"]):
        signals = [Signal(methods=signals[0].methods, duration=f"PT{int(custom_object['wait'])}M")]

    hitchhiker = Hitchhiker(nickname="Anonymous") if current_user.is_anonymous else construct_hitchhiker_from_current_user()

    now = pd.Timestamp.now()

    record = HitchhikingRecord(
        version="0.0.0",
        stops=stops,
        rating=int(custom_object["rate"]),
        hitchhikers=[hitchhiker],
        comment=None if custom_object["comment"] == "" else custom_object["comment"],
        signals=signals,
        occupants=None,
        mode_of_transportation=None,
        ride=None,
        declined_rides=None,
        source=source,
        license=license,
        submission_time=now.strftime("%Y-%m-%dT%H:%M:%S"),
    )

    return record
