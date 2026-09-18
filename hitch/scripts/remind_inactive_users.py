"""Daily job: email users who signed up but haven't logged a single ride yet, nudging
them to explore the map and log their current or past rides. Also emails users who
*have* logged rides but have gone quiet, nudging them to add their latest trip.

Runs once a day (deploy/cron.sh). The zero-ride flow:

  1. Consider every registered user who still has zero logged rides (`total_rides == 0`,
     recomputed from ride nicknames by show.py) and who opted into email (the global
     `email_notifications` toggle), skipping synthetic / undeliverable OAuth addresses.
  2. Send the reminder at two milestones after signup (`create_datetime`): once at 7
     days, once more at 30 days if they're still at zero rides. After the 30-day nudge
     we stop — a user gets at most two of these emails, ever.
  3. `inactive_reminder_stage` records the last milestone sent (0 → none, 7 → 7-day,
     30 → final), so a daily run never re-sends a stage. The moment a user logs a ride
     `total_rides` goes positive and they drop out of the query, so someone who logs a
     ride between day 7 and day 30 never receives the second reminder.

A user who signs up and only sees this job run after they've already passed 30 days
(zero rides the whole time) jumps straight to the final stage — see the stage pick in
`run()`: we always send the *highest* milestone they've reached but not yet been sent,
so we never spam a backlog of two emails at once.

The lapsed-logger flow (`run_lapsed()`) is a separate cohort with its own gate:

  1. Consider users with `total_rides >= 1` whose most recent ride (`last_ride_at`,
     recomputed alongside total_rides by show.py) is 28-56 days old — long enough that
     they've plausibly gone quiet, short enough the nudge is still relevant to a trip
     they might still be on or just back from.
  2. Same opt-in (`email_notifications`) and synthetic-address gates as the zero-ride
     flow, same SparkPost template family (`_LAPSED_STAGE`), reusing `inactive_reminder
     .html`/`.txt`'s existing stage-branch structure rather than new content.
  3. `lapsed_reminder_sent_for` stores the `last_ride_at` value at the time we last sent
     this user a lapsed nudge (not a milestone count, since this cohort can lapse more
     than once). We send only when it's NULL or older than the user's current
     `last_ride_at` — one email per lapse. Logging a new ride moves `last_ride_at`
     forward, which re-arms eligibility next time they go quiet.
"""

import logging
import sqlite3
import time
from datetime import timezone

from flask import current_app

from hitch.blueprints.utils.send_inactive_reminder_email import send_inactive_reminder_email
from hitch.extensions import db
from hitch.helpers import get_db
from hitch.models import User

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

# OAuth users with no real email get a synthetic, undeliverable address — never mail those.
_SYNTHETIC_EMAIL_SUFFIX = "@hitchwiki.oauth"

# Reminder milestones in days since signup, ascending. A user at zero rides gets the
# 7-day nudge, then (if still at zero) the 30-day nudge, then nothing more.
_STAGES = (7, 30)

# Stage value for the lapsed-logger reminder (users with >=1 ride who've gone quiet).
# Deliberately outside _STAGES's range so it can't collide with the zero-ride
# progression logic above, while still keying the same stage-branching template family.
_LAPSED_STAGE = 100

# Window (days since last ride) a lapsed-logger reminder fires in: old enough the user
# has plausibly gone quiet, not so old the nudge feels irrelevant to a trip they might
# still be wrapping up.
_LAPSED_MIN_DAYS = 28
_LAPSED_MAX_DAYS = 56

_DAY_SECONDS = 24 * 60 * 60


def _ensure_column():
    """Idempotently add the user.inactive_reminder_stage column.

    There is no migration framework, so a fresh column won't exist on the prod DB until
    added by hand. Doing it here keeps this job working even if the manual ALTER was
    missed. A re-add raises OperationalError, which we swallow.
    """
    conn = get_db()
    try:
        conn.execute("ALTER TABLE user ADD COLUMN inactive_reminder_stage INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        logger.info("Added missing column user.inactive_reminder_stage")
    except sqlite3.OperationalError:
        pass  # column already exists


def _ensure_lapsed_column():
    """Idempotently add the user.lapsed_reminder_sent_for and user.last_ride_at columns.

    Same rationale as _ensure_column above — no migration framework, so this keeps the
    job working even if the manual ALTER on prod was missed. last_ride_at is normally
    added by show.py (which also writes it), but this job queries it directly and runs
    only once a day, so it can't assume a show.py run has already added the column
    since the deploy that introduced it.
    """
    conn = get_db()
    for col, coltype in (("lapsed_reminder_sent_for", "DATETIME"), ("last_ride_at", "DATETIME")):
        try:
            conn.execute(f"ALTER TABLE user ADD COLUMN {col} {coltype}")
            conn.commit()
            logger.info(f"Added missing column user.{col}")
        except sqlite3.OperationalError:
            pass  # column already exists


def _account_age_days(user, now):
    """Whole days since the account was created, or None if we can't tell.

    Flask-Security stores `create_datetime` as a naive UTC datetime. We treat a missing
    value as "unknown age" and skip the user rather than guess.
    """
    created = user.create_datetime
    if created is None:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (now - int(created.timestamp())) / _DAY_SECONDS


def _stage_to_send(age_days, already_sent):
    """Return the milestone to send now, or None.

    We send the *highest* milestone the user has reached (age >= milestone) that is
    strictly greater than what they've already been sent. This way a user who first
    becomes visible to the job well past 30 days gets a single 30-day email, not a
    7-day one followed by a 30-day one on consecutive days.
    """
    candidate = None
    for milestone in _STAGES:
        if age_days >= milestone and milestone > already_sent:
            candidate = milestone
    return candidate


def run():
    _ensure_column()

    if not current_app.config.get("SPARKPOST_API_KEY"):
        logger.warning("SPARKPOST_API_KEY not set — skipping inactive-user reminders")
        return

    now = int(time.time())

    # Only users with zero logged rides are candidates; total_rides is recomputed by
    # show.py from ride nicknames, so it's the same "0 rides" the profile shows.
    candidates = User.query.filter(
        db.func.coalesce(User.total_rides, 0) == 0,
        User.inactive_reminder_stage < _STAGES[-1],
    ).all()
    logger.info(f"{len(candidates)} users with zero rides not yet at the final reminder stage")

    sent = 0
    for user in candidates:
        # Gate on the global email switch and never mail synthetic / missing addresses,
        # exactly like the welcome email.
        if not user.email_notifications:
            continue
        if not user.email or user.email.endswith(_SYNTHETIC_EMAIL_SUFFIX):
            continue

        age_days = _account_age_days(user, now)
        if age_days is None:
            continue

        stage = _stage_to_send(age_days, user.inactive_reminder_stage or 0)
        if stage is None:
            continue

        try:
            send_inactive_reminder_email(user, stage)
            # Advance the stage so a later daily run never re-sends this milestone.
            user.inactive_reminder_stage = stage
            db.session.commit()
            sent += 1
            logger.info(f"Sent {stage}-day reminder to {user.username} <{user.email}>")
        except Exception:
            # One bad send must not abort the rest of the run; roll back the pending
            # stage write so the session stays usable for the next user.
            db.session.rollback()
            logger.exception(f"Failed to send inactive-user reminder to {user.username}")

    logger.info(f"Done — {sent} reminder emails sent")


def run_lapsed():
    _ensure_lapsed_column()

    if not current_app.config.get("SPARKPOST_API_KEY"):
        logger.warning("SPARKPOST_API_KEY not set — skipping lapsed-logger reminders")
        return

    now = int(time.time())

    # Only users with at least one logged ride are candidates for this cohort — the
    # zero-ride flow above already covers users who've never logged one.
    candidates = User.query.filter(db.func.coalesce(User.total_rides, 0) >= 1, User.last_ride_at.isnot(None)).all()

    sent = 0
    for user in candidates:
        # Same gates as the zero-ride flow: global opt-in, never mail a synthetic
        # OAuth address.
        if not user.email_notifications:
            continue
        if not user.email or user.email.endswith(_SYNTHETIC_EMAIL_SUFFIX):
            continue

        last_ride_at = user.last_ride_at
        if last_ride_at.tzinfo is None:
            last_ride_at = last_ride_at.replace(tzinfo=timezone.utc)
        days_since = (now - int(last_ride_at.timestamp())) / _DAY_SECONDS
        if not (_LAPSED_MIN_DAYS <= days_since <= _LAPSED_MAX_DAYS):
            continue

        # One email per lapse: skip if we already sent for this exact last_ride_at.
        # A new ride moves last_ride_at forward and re-arms eligibility.
        if user.lapsed_reminder_sent_for is not None and user.lapsed_reminder_sent_for == user.last_ride_at:
            continue

        try:
            send_inactive_reminder_email(user, _LAPSED_STAGE)
            user.lapsed_reminder_sent_for = user.last_ride_at
            db.session.commit()
            sent += 1
            logger.info(f"Sent lapsed-logger reminder to {user.username} <{user.email}>")
        except Exception:
            db.session.rollback()
            logger.exception(f"Failed to send lapsed-logger reminder to {user.username}")

    logger.info(f"Done — {sent} lapsed-logger reminder emails sent")


run()
run_lapsed()
