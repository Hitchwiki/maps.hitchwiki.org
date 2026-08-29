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
    KindEnum,
    Location,
    ModeOfTranportation,
    NoRide,
    Occupant,
    Ride,
    Signal,
    Stop,
)

ALLOWED_VEHICLE_KINDS = [k.value for k in KindEnum]

# Co-hitchhikers travel as a comma-separated string of usernames. A co-hitchhiker without
# an account is the literal "Anonymous", optionally suffixed with ":male" / ":female" when
# the submitter told us that person's gender (so it reaches Nostr as the hitchhiker's
# `gender`). Usernames are [a-zA-Z0-9]+, so the colon can never collide with a real one.
ANONYMOUS_NICKNAME = "Anonymous"
ANONYMOUS_CO_HITCHHIKER_GENDERS = ("male", "female")


def is_anonymous_co_hitchhiker(token: str) -> bool:
    """True for "Anonymous" and its gendered variants ("Anonymous:female")."""
    return (token or "").strip().split(":", 1)[0] == ANONYMOUS_NICKNAME


def anonymous_co_hitchhiker_gender(token: str) -> str | None:
    """Gender encoded in an anonymous token, or None when unstated (or not one we accept)."""
    parts = (token or "").strip().split(":", 1)
    gender = parts[1].strip() if len(parts) == 2 else ""
    return gender if gender in ANONYMOUS_CO_HITCHHIKER_GENDERS else None


def anonymous_co_hitchhiker_token(gender: str | None) -> str:
    """Inverse of the above — used when re-filling the edit form from a stored ride."""
    return f"{ANONYMOUS_NICKNAME}:{gender}" if gender in ANONYMOUS_CO_HITCHHIKER_GENDERS else ANONYMOUS_NICKNAME


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
    elif signal == "unsolicited":
        return Signal(
            methods=["unsolicited"],
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


def construct_hitchhiker_from_current_user(reasons_to_hitchhike: list[str] | None = None) -> Hitchhiker:
    hitchhiker = Hitchhiker(
        origin_location=current_user.origin_city if hasattr(current_user, "origin_city") else None,
        origin_country=current_user.origin_country if hasattr(current_user, "origin_country") else None,
        year_of_birth=current_user.year_of_birth if hasattr(current_user, "year_of_birth") else None,
        gender=map_gender(current_user.gender) if hasattr(current_user, "gender") else None,
        languages=None,
        was_driver=None,
        nickname=current_user.username,
        hitchhiking_since=current_user.hitchhiking_since if hasattr(current_user, "hitchhiking_since") else None,
        reasons_to_hitchhike=list(reasons_to_hitchhike) if reasons_to_hitchhike else None,
    )

    return hitchhiker


### Define one function that takes single rides from your dataset and builds objects that follow this standard from them
### Again, here the function is a bit special because we are dealing with multiple datasets actually


def foreign_coordinate_intermediate_stops(raw_stops: list) -> list[Stop]:
    """Intermediate stops from a ride's *raw* Nostr content that carry a real coordinate.

    `create_record_from_custom_object` always rebuilds a ride's stops from scratch out of
    form fields, and this form has no coordinate picker for an intermediate stop (see the
    comment above) -- it only ever produces label-only ones. So on an edit, resubmitting
    without this would silently drop the coordinate on any intermediate stop that reached
    the ride some other way (a different Nostr client publishing to the same relay/kind).
    Currently 0/1,732 real rides have such a stop (verified 2026-08-22), so this guards
    against a scenario that hasn't happened yet rather than one already seen in the wild.
    """
    out = []
    for stop in (raw_stops or [])[1:-1]:
        if not isinstance(stop, dict):
            continue
        location = stop.get("location") or {}
        lat, lon = location.get("latitude"), location.get("longitude")
        if lat is None or lon is None:
            continue  # label-only or malformed -- not this form's job to preserve
        out.append(
            Stop(
                location=Location(latitude=lat, longitude=lon, is_exact=bool(location.get("is_exact", True))),
                label=stop.get("label"),
                arrival_time=stop.get("arrival_time"),
                departure_time=stop.get("departure_time"),
                waiting_duration=stop.get("waiting_duration"),
            )
        )
    return out


def create_record_from_custom_object(custom_object: dict, source: str, license: str) -> HitchhikingRecord:
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
    # Stops between pickup and destination: free-text labels only ("onsen", "their
    # grandparents' house"), no coordinate picker -- a hitchhiker recalling a detour after
    # the fact rarely has the exact spot, and the point (a Matrix chat question this
    # answers) is the story, not a pin. Only meaningful with a real destination: a stop
    # "along the way" to nowhere recorded isn't a waypoint, it's just more trip.
    if pd.notna(dest_lat) and pd.notna(dest_lon):
        for label in custom_object.get("ride_stops") or []:
            stops.append(Stop(location=None, label=label))

    if pd.notna(dest_lat) and pd.notna(dest_lon):
        arrival_dt = custom_object.get("arrival_datetime")
        arrival_time = (
            pd.to_datetime(arrival_dt).strftime("%Y-%m-%dT%H:%M:%S")
            if arrival_dt is not None and pd.notna(arrival_dt) and arrival_dt != ""
            else None
        )
        stops.append(
            Stop(
                location=Location(
                    latitude=dest_lat,
                    longitude=dest_lon,
                    is_exact=True,  # assume that our UI allows to select the destination accurately
                ),
                arrival_time=arrival_time,
            )
        )

    # "signal" may arrive as a list (multi-select checkboxes), a single string (legacy),
    # or empty/None. Normalize to a list of allowed values, map to standard method names,
    # and emit a single Signal carrying every chosen method (plus the wait duration if set).
    raw_signal = custom_object.get("signal")
    if isinstance(raw_signal, str):
        raw_signal = [raw_signal]
    elif raw_signal is None:
        raw_signal = []
    method_map = {"sign": "sign", "thumb": "thumb", "ask": "asking", "unsolicited": "unsolicited"}
    methods = []
    for s in raw_signal:
        m = method_map.get(s)
        if m and m not in methods:
            methods.append(m)
    if methods:
        duration = f"PT{int(custom_object['wait'])}M" if pd.notna(custom_object.get("wait")) else None
        # What the sign said is only meaningful when a sign was actually used — the form
        # hides the field otherwise, and a leftover value from a de-selected chip must not
        # be published as if it had been held up.
        sign_content = (custom_object.get("sign_content") or "").strip() or None
        signals = [Signal(methods=methods, duration=duration, sign_content=sign_content if "sign" in methods else None)]
    else:
        signals = None

    # Why *this* person hitchhiked on *this* ride — asked in the form's "You" section.
    # It belongs to the submitting hitchhiker only: a co-hitchhiker's reasons are theirs
    # to state, and an anonymous co-hitchhiker never gets asked at all.
    reasons_to_hitchhike = custom_object.get("reasons_to_hitchhike") or []
    hitchhiker = (
        Hitchhiker(nickname=ANONYMOUS_NICKNAME, reasons_to_hitchhike=list(reasons_to_hitchhike) or None)
        if current_user.is_anonymous
        else construct_hitchhiker_from_current_user(reasons_to_hitchhike)
    )

    # Build hitchhikers list: the current user plus any anonymous co-hitchhikers. Named
    # co-hitchhikers are not published here — they only join the event once they accept
    # the invite (see accept_co_hitchhiker in user.py).
    hitchhikers = [hitchhiker]
    co_hitchhiker_str = custom_object.get("co_hitchhiker", "")
    if co_hitchhiker_str:
        hitchhikers.extend(
            Hitchhiker(nickname=ANONYMOUS_NICKNAME, gender=anonymous_co_hitchhiker_gender(token))
            for token in co_hitchhiker_str.split(",")
            if is_anonymous_co_hitchhiker(token)
        )

    now = pd.Timestamp.now()

    # Build mode_of_transportation only when a kind is provided. Per the standard,
    # `kind` is the only required field of the vehicle object — other fields stay free text.
    vehicle_kind = (custom_object.get("vehicle_kind") or "").strip()
    mode_of_transportation = None
    if vehicle_kind in ALLOWED_VEHICLE_KINDS:
        country = (custom_object.get("vehicle_license_plate_country") or "").strip().upper() or None
        mode_of_transportation = ModeOfTranportation(
            kind=vehicle_kind,
            make=(custom_object.get("vehicle_make") or "").strip() or None,
            model=(custom_object.get("vehicle_model") or "").strip() or None,
            license_plate_country=country,
            license_plate_identifier=(custom_object.get("vehicle_license_plate_identifier") or "").strip() or None,
        )

    # Build driver Occupant from optional driver-info fields. If at least one field
    # is set we emit an occupant entry with was_driver=True so downstream consumers
    # know the info refers to the person who picked up the hitchhiker.
    driver_reasons = custom_object.get("driver_reason_to_pick_up") or []
    driver_country = (custom_object.get("driver_origin_country") or "").strip().upper() or None
    driver_yob = custom_object.get("driver_year_of_birth")
    driver_gender = (custom_object.get("driver_gender") or "").strip() or None
    driver_languages = custom_object.get("driver_languages") or []
    # Tristate: True / False / None (unanswered). `is not None` because an explicit
    # "no" is falsy but still an answer worth publishing.
    driver_would_ride_again = custom_object.get("driver_would_ride_again")
    if driver_reasons or driver_country or driver_yob or driver_gender or driver_languages or driver_would_ride_again is not None:
        occupants = [
            Occupant(
                origin_country=driver_country,
                year_of_birth=int(driver_yob) if driver_yob else None,
                gender=driver_gender,
                languages=list(driver_languages) or None,
                was_driver=True,
                reasons_to_pick_up=list(driver_reasons) or None,
                would_ride_again=driver_would_ride_again,
            )
        ]
    else:
        occupants = None

    # The trip the driver was on anyway (`ride.reasons`), asked next to the driver info.
    # Only emitted when answered — an empty Ride object would claim nothing.
    ride_reasons = custom_object.get("ride_reasons") or []
    ride = Ride(reasons=list(ride_reasons)) if ride_reasons else None

    # The hitchhiker never got picked up here. We don't ask why yet, so the reasons list is
    # empty — its presence alone is what marks the record as a no-ride.
    no_ride = NoRide(reasons=[]) if custom_object.get("no_ride") else None

    record = HitchhikingRecord(
        version="0.0.0",
        stops=stops,
        rating=int(custom_object["rate"]),
        hitchhikers=hitchhikers,
        comment=None if custom_object["comment"] == "" else custom_object["comment"],
        signals=signals,
        occupants=occupants,
        mode_of_transportation=mode_of_transportation,
        ride=ride,
        declined_rides=None,
        no_ride=no_ride,
        source=source,
        license=license,
        submission_time=now.strftime("%Y-%m-%dT%H:%M:%S"),
    )

    return record
