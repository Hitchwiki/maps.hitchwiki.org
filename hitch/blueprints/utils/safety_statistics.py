"""Per-ride rows behind /hitchhiking-safety, the "would you accept this ride again?" page.

Deliberately NOT an aggregate. The page lets a visitor describe the people who were
hitchhiking — up to four of them, each by gender, age and hitchhiking experience — and
then breaks the answer down by driver, place, time, vehicle and wait. That is a
combinatorial question: any cube precomputed here would either explode (four person
slots x gender x age band x experience band is millions of cells, nearly all empty) or
silently limit which questions the page can answer. Only ~1.1k of ~84k rides carry an
answer at all, so shipping one compact row per answered ride is both smaller than an
aggregate and open-ended — the client filters and counts.

`summarise_rows` takes raw ``(id, d, hitchhikers, occupants, stops, mode_of_transportation,
signals, rating, submission_time, no_ride, would_ride_again)`` database rows so it can be
unit-tested without an app context, exactly like wait_time_statistics.
"""

import json
import math
import re
from collections import Counter

KNOWN_GENDERS = ("female", "male", "non_binary", "prefer_not_to_say")
# Same strict PT<n>M shape ride_facts accepts: an invented wait is worse than none.
WAIT_RE = re.compile(r"^PT(\d+)M$")
YEAR_RE = re.compile(r"^(\d{4})-\d{2}-\d{2}")
HOUR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ](\d{2}):")
# A year_of_birth outside this range is a typo or a joke, not a person; keeping it would
# put a 400-year-old in an age band and make that band's rate meaningless.
MIN_BIRTH_YEAR, MAX_BIRTH_YEAR = 1900, 2020
EARTH_RADIUS_KM = 6371


def _json_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
    return value


def _dicts(value):
    value = _json_value(value)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _gender(person):
    gender = person.get("gender")
    return gender if gender in KNOWN_GENDERS else None


def _birth_year(person):
    year = person.get("year_of_birth")
    return year if isinstance(year, int) and MIN_BIRTH_YEAR <= year <= MAX_BIRTH_YEAR else None


def _since(person):
    year = person.get("hitchhiking_since")
    return year if isinstance(year, int) and MIN_BIRTH_YEAR <= year <= MAX_BIRTH_YEAR else None


def _ride_year(stops, submission_time):
    """The calendar year the ride happened in, used to turn a birth year into an age.

    Departure time first, submission time only as a fallback: a ride logged in January
    about a trip the previous summer would otherwise age everyone by a year. Both are
    local wall-clock stamps, which is what we want — nobody's age depends on the offset.
    """
    for stamp in (_departure_time(stops), submission_time):
        match = YEAR_RE.match(stamp or "")
        if match:
            return int(match.group(1))
    return None


def _departure_time(stops):
    stops = _dicts(stops)
    return stops[0].get("departure_time") if stops else None


def _hour(stops):
    """Hour of day the ride started, or None.

    Only ``departure_time`` counts — never the submission-time fallback above. This
    column answers "is a night ride different?", and a submission stamp is when someone
    typed the ride in, which is frequently the evening of a morning ride.
    """
    match = HOUR_RE.match(_departure_time(stops) or "")
    hour = int(match.group(1)) if match else None
    return hour if hour is not None and 0 <= hour <= 23 else None


def _wait_minutes(stops):
    stops = _dicts(stops)
    if not stops:
        return None
    match = WAIT_RE.fullmatch(stops[0].get("waiting_duration") or "")
    return int(match.group(1)) if match else None


def _coords(stops):
    stops = _dicts(stops)
    if not stops:
        return (None, None), (None, None)
    first = (stops[0].get("location") or {}) if isinstance(stops[0], dict) else {}
    last = (stops[-1].get("location") or {}) if len(stops) > 1 else {}
    return (first.get("latitude"), first.get("longitude")), (last.get("latitude"), last.get("longitude"))


def pickup_coords(stops):
    """(lat, lon) of where the hitchhiker was picked up, or (None, None).

    Public because the cron script reverse-geocodes these into countries; the geocoder
    itself stays out of this module (and out of any web worker) — see the script.
    """
    return _coords(stops)[0]


def _distance_km(start, end):
    if None in start or None in end:
        return None
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [start[0], start[1], end[0], end[1]])
    dlat, dlon = rlat2 - rlat1, rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return round(2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a)), 1)


def _driver(occupants):
    return next((o for o in _dicts(occupants) if o.get("was_driver")), None)


def _signal_methods(signals):
    methods = []
    for signal in _dicts(signals):
        for method in signal.get("methods") or []:
            if isinstance(method, str) and method not in methods:
                methods.append(method)
    return methods


def _person_row(person, ride_year):
    """[gender, age_at_ride, years_of_experience] — each entry None when not recorded.

    Age is stored rather than the birth year so the client never has to know the ride's
    year to apply an age filter, and so a hitchhiker who logged rides over several years
    lands in the band they were actually in at the time.
    """
    birth_year, since = _birth_year(person), _since(person)
    age = ride_year - birth_year if (ride_year and birth_year and 0 <= ride_year - birth_year <= 120) else None
    experience = ride_year - since if (ride_year and since and 0 <= ride_year - since <= 100) else None
    return [_gender(person), age, experience]


def summarise_rows(rows, countries=None):
    """Build the page's payload from raw ride rows.

    ``countries`` is an optional ``{ride_id: "DE"}`` mapping: reverse geocoding needs a
    ~30 MB offline index, which belongs in the cron script, not in this pure module (and
    not in a web worker — see CLAUDE.md).

    A ride is included only when the hitchhiker actually answered the question. The
    answer is per-driver and the standard allows several occupants, but the form asks it
    of the driver, so that is whose row this is.
    """
    countries = countries or {}
    coverage = Counter()
    negative_totals = Counter()
    rides = []
    hitchhiker_keys = set()

    for (
        ride_id,
        d_tag,
        hitchhikers,
        occupants,
        stops,
        mode_of_transportation,
        signals,
        rating,
        submission_time,
        no_ride,
        would_ride_again,
    ) in rows:
        coverage["rows_read"] += 1
        if would_ride_again is None:
            coverage["no_answer"] += 1
            continue
        # A give-up record has no driver to answer about; if one still carries the flag,
        # it is not an accepted ride and does not belong in an "again?" rate.
        if no_ride:
            coverage["no_ride_excluded"] += 1
            continue

        people = _dicts(hitchhikers)
        ride_year = _ride_year(stops, submission_time)
        driver = _driver(occupants) or {}
        driver_birth_year = _birth_year(driver)
        start, end = _coords(stops)
        vehicle = _json_value(mode_of_transportation)
        negatives = [e for e in (driver.get("negative_experiences") or []) if isinstance(e, str)]
        positives = [e for e in (driver.get("positive_experiences") or []) if isinstance(e, str)]
        # Nicknames are already public on every ride card; they are carried so the page
        # can print how many *people* a rate rests on, not just how many rides. A rate of
        # 40 rides from one prolific hitchhiker is a fact about that hitchhiker.
        names = sorted({(p.get("nickname") or "").strip() or "Anonymous" for p in people}) or ["Anonymous"]
        hitchhiker_keys.update(n for n in names if n != "Anonymous")

        row = {
            "w": 1 if would_ride_again else 0,
            # The page links every "no" answer to its own ride page: 32 answers in the
            # whole corpus is few enough that a reader can and should read them, and a
            # rate with no way through to the rides behind it is not evidence.
            "d": d_tag,
            "p": [_person_row(person, ride_year) for person in people] or [[None, None, None]],
            "dg": _gender(driver),
            "da": (ride_year - driver_birth_year) if (ride_year and driver_birth_year) else None,
            "y": ride_year,
            "h": _hour(stops),
            "wt": _wait_minutes(stops),
            "km": _distance_km(start, end),
            "v": vehicle.get("kind") if isinstance(vehicle, dict) else None,
            "s": _signal_methods(signals),
            "r": rating if isinstance(rating, int) else None,
            "cc": countries.get(ride_id),
            "u": names,
        }
        if negatives:
            row["n"] = negatives
        if positives:
            row["pos"] = positives
        # Empty lists/None cost ~1.1k x a few bytes each; dropping them keeps the file
        # the page downloads small without changing what the client can ask.
        rides.append({key: value for key, value in row.items() if value not in (None, [], {})})

        coverage["rides_used"] += 1
        coverage["yes"] += 1 if would_ride_again else 0
        coverage["with_gender"] += 1 if any(p[0] for p in row["p"]) else 0
        coverage["with_age"] += 1 if any(p[1] is not None for p in row["p"]) else 0
        coverage["with_driver_gender"] += 1 if row["dg"] else 0
        coverage["multi_person"] += 1 if len(people) > 1 else 0
        for experience in negatives:
            negative_totals[experience] += 1

    coverage["named_hitchhikers"] = len(hitchhiker_keys)
    return {
        "coverage": dict(coverage),
        "negative_experiences": dict(negative_totals.most_common()),
        "rides": rides,
    }
