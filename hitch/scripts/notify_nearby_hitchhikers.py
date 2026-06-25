"""Daily job: email opted-in users about other registered hitchhikers whose rides
were logged near theirs in the last few days.

Runs once a day at midnight (deploy/cron.sh). The flow:

  1. Take every ride from the last 3 days. A ride's effective time is its actual ride
     time (the first stop's `departure_time`); only when a ride has no ride time do
     we fall back to when it was added (`created_at`, the Nostr publish epoch). So a
     trip that happened in the window counts even if it was logged later, while an
     old trip logged recently does not.
  2. Map each ride to the registered, non-anonymous user(s) behind it (hitchhiker
     nickname -> User, matched case-insensitively, same as the leaderboard).
  3. For every pair of rides whose START points OR DESTINATIONS are within 100 km
     of each other, the users behind those two rides count as "near" each other.
  4. For each user who ticked "Email me about other hitchhikers who were close by"
     (and hasn't globally opted out of email), send one email listing the profiles
     of all other users they were near in the window — but only if they weren't already
     emailed within the last window. Because the job runs daily over a 3-day window, the
     same encounter would otherwise be reported up to 3 days in a row; throttling to one
     email per 3 days per user (tracked via user.nearby_hitchhikers_email_last_sent)
     ensures a user isn't notified repeatedly about the same encounter.

A rolling window (rather than a strict calendar day) is used deliberately: the job
fires at 00:00, so it covers the days that just ended, and a rolling window sidesteps
the midnight boundary edge case cleanly.
"""

import logging
import sqlite3
import time
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt

from flask import current_app

from hitch.blueprints.utils.notifications import notify_nearby_hitchhikers
from hitch.blueprints.utils.send_nearby_hitchhikers_email import send_nearby_hitchhikers_email
from hitch.extensions import db
from hitch.helpers import get_db
from hitch.models import RideEvent, User

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

# Rides whose start points OR destinations are closer than this count as "near".
PROXIMITY_KM = 100.0

# Window of rides to consider: the last 3 days' worth, ending now.
WINDOW_SECONDS = 3 * 24 * 60 * 60

# OAuth users with no real email get a synthetic, undeliverable address — never mail those.
_SYNTHETIC_EMAIL_SUFFIX = "@hitchwiki.oauth"

BASE_URL = "https://maps.hitchwiki.org"


def _ensure_column():
    """Idempotently add the user.nearby_hitchhikers_email column.

    There is no migration framework, so a fresh column won't exist on the prod DB
    until added by hand. Doing it here keeps both this job and the edit-profile form
    working even if the manual ALTER was missed. A re-add raises OperationalError.
    """
    conn = get_db()
    for ddl, name in (
        ("ALTER TABLE user ADD COLUMN nearby_hitchhikers_email BOOLEAN NOT NULL DEFAULT 0", "nearby_hitchhikers_email"),
        ("ALTER TABLE user ADD COLUMN nearby_hitchhikers_email_last_sent INTEGER", "nearby_hitchhikers_email_last_sent"),
    ):
        try:
            conn.execute(ddl)
            conn.commit()
            logger.info(f"Added missing column user.{name}")
        except sqlite3.OperationalError:
            pass  # column already exists


def _haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two lat/lon points."""
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


def _parse_ride_time(value):
    """Parse a stop's departure_time into epoch seconds, or None if absent/unparseable.

    Values are ISO 8601 (usually naive, e.g. '2026-06-21T13:43:00'), but may carry a
    'Z'/offset or an RFC 9557 bracketed zone suffix like '...[Europe/Berlin]'. Naive
    values are treated as UTC — a few hours of zone skew is immaterial over a multi-day window.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    # Drop an RFC 9557 bracketed timezone/calendar suffix that fromisoformat can't read.
    if "[" in text:
        text = text[: text.index("[")]
    text = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _coord(stop):
    """Return (lat, lon) from a ride stop, or None if it lacks valid coordinates."""
    location = (stop or {}).get("location") or {}
    lat = location.get("latitude")
    lon = location.get("longitude")
    if lat is None or lon is None:
        return None
    return (lat, lon)


def _build_ride_records(cutoff, now, users_by_lower):
    """Return a list of {users: set[int], start, dest} for in-window rides whose
    hitchhikers map to registered, non-anonymous users.

    A ride is in-window when its effective time falls in [cutoff, now]. The effective
    time is the actual ride time (first stop's departure_time) when present, otherwise
    the time the ride was added (created_at).
    """
    # Pre-filter generously in SQL: a logged ride is published at or after it happened,
    # so created_at >= the ride's true instant. We widen by one extra window to absorb
    # timezone skew from treating naive departure_times as UTC; the precise [cutoff, now]
    # check below (on the effective time) does the real filtering.
    rides = RideEvent.query.filter(RideEvent.created_at >= cutoff - WINDOW_SECONDS).all()

    records = []
    for ride in rides:
        content = ride.content if isinstance(ride.content, dict) else {}
        stops = content.get("stops") or []
        if not stops:
            continue

        # Prefer the actual ride time; fall back to the added time only when absent.
        ride_time = _parse_ride_time(stops[0].get("departure_time"))
        effective = ride_time if ride_time is not None else ride.created_at
        if effective < cutoff or effective > now:
            continue

        # Resolve every hitchhiker nickname on the ride to a registered user.
        user_ids = set()
        for hitchhiker in content.get("hitchhikers") or []:
            nickname = (hitchhiker.get("nickname") or "").strip()
            if not nickname or nickname.lower() == "anonymous":
                continue
            user = users_by_lower.get(nickname.lower())
            if user is not None:
                user_ids.add(user.id)
        if not user_ids:
            continue

        start = _coord(stops[0])
        if start is None:
            continue
        dest = _coord(stops[-1]) if len(stops) > 1 else None

        records.append({"users": user_ids, "start": start, "dest": dest})

    logger.info(f"{len(records)} in-window rides with registered hitchhikers")
    return records


def _build_proximity_map(records):
    """Return {user_id -> set[user_id]} of users who were near each other.

    Two rides are "near" if their start points OR their destinations are within
    PROXIMITY_KM. The number of rides per day is small, so the O(n^2) scan is fine.
    """
    near = {}
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            a, b = records[i], records[j]

            close = _haversine_km(*a["start"], *b["start"]) < PROXIMITY_KM
            if not close and a["dest"] and b["dest"]:
                close = _haversine_km(*a["dest"], *b["dest"]) < PROXIMITY_KM
            if not close:
                continue

            # Every cross pair of (distinct) users behind the two rides is now near.
            for u in a["users"]:
                for v in b["users"]:
                    if u != v:
                        near.setdefault(u, set()).add(v)
                        near.setdefault(v, set()).add(u)
    return near


def _profile_for(user):
    """Build the template dict describing a nearby user."""
    location = ", ".join(part for part in (user.origin_city, user.origin_country) if part)
    return {
        "username": user.username,
        "profile_url": f"{BASE_URL}/account/{user.username}",
        "location": location,
        "hitchhiking_since": user.hitchhiking_since,
    }


def run():
    _ensure_column()

    if not current_app.config.get("SPARKPOST_API_KEY"):
        logger.warning("SPARKPOST_API_KEY not set — skipping nearby-hitchhikers emails")
        return

    now = int(time.time())
    cutoff = now - WINDOW_SECONDS

    # Map every registered username (lowercased) to its User for nickname resolution.
    all_users = User.query.all()
    users_by_lower = {u.username.lower(): u for u in all_users if u.username}

    records = _build_ride_records(cutoff, now, users_by_lower)
    near = _build_proximity_map(records)
    logger.info(f"{len(near)} users were near at least one other user")

    sent = 0
    for user_id, nearby_ids in near.items():
        user = db.session.get(User, user_id)
        if user is None:
            continue
        # Require the explicit opt-in; also honour the global email switch as a hard
        # opt-out, and never mail synthetic / missing addresses.
        if not user.nearby_hitchhikers_email or not user.email_notifications:
            continue
        if not user.email or user.email.endswith(_SYNTHETIC_EMAIL_SUFFIX):
            continue
        # Throttle: the job runs daily over a 3-day window, so the same encounter recurs
        # for up to 3 days. Only email a user if they haven't been emailed in the last
        # window, so they aren't notified repeatedly about the same encounter.
        last_sent = user.nearby_hitchhikers_email_last_sent
        if last_sent is not None and now - last_sent < WINDOW_SECONDS:
            continue

        nearby_users = [db.session.get(User, vid) for vid in nearby_ids]
        profiles = [_profile_for(u) for u in sorted(filter(None, nearby_users), key=lambda u: u.username.lower())]
        if not profiles:
            continue

        try:
            send_nearby_hitchhikers_email(user, profiles)
            # Record the send so the throttle above suppresses repeat emails about the
            # same encounter on the next daily runs within the window.
            user.nearby_hitchhikers_email_last_sent = now
            db.session.commit()
            # Mirror the email in-app so the encounter is also recorded in the profile.
            notify_nearby_hitchhikers(user.id, [p["username"] for p in profiles])
            sent += 1
            logger.info(f"Sent nearby-hitchhikers email to {user.username} <{user.email}> ({len(profiles)} profiles)")
        except Exception:
            # One bad send must not abort the rest of the run; roll back any pending
            # timestamp write so the session stays usable for the next user.
            db.session.rollback()
            logger.exception(f"Failed to send nearby-hitchhikers email to {user.username}")

    logger.info(f"Done — {sent} emails sent")


run()
