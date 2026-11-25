"""ONE-SHOT (not cron): "Your <year> recap is ready" email to accounts that logged rides that year.

DRY RUN BY DEFAULT: prints only the aggregate eligible count and sends nothing. To send,
set RECAP_EMAIL_SEND=1 (and optionally RECAP_EMAIL_YEAR, default: the current year).
It must only be run after the maintainers have approved the exact email text.

Who gets it (same gates as the inactive-user reminder):
  - opted in to email (`email_notifications`), real address (no `@hitchwiki.oauth` synthetic one);
  - `last_ride_at` falls in the recap year. That column is the newest ride's *submission* time,
    so this is a proxy for "has a ride in the year": it can include someone whose only 2026
    entry is a back-logged old trip (the recap page then shows its own empty state) and miss
    someone who logged a 2026 ride and then a later-year one. Good enough for a notice.
  - not already sent for this year (`recap_email_sent_year`), so a re-run never double-sends.
"""

import logging
import os
import sqlite3
import time
from datetime import datetime, timezone

from flask import current_app

from hitch.blueprints.utils.send_year_recap_email import eligible_users, send_year_recap_email
from hitch.extensions import db
from hitch.helpers import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

# Gap between sends, so one run does not burst the SparkPost account the newsletter shares.
_SEND_PAUSE_S = 0.2


def _ensure_column():
    """No migration framework: add user.recap_email_sent_year if prod does not have it yet."""
    try:
        get_db().execute("ALTER TABLE user ADD COLUMN recap_email_sent_year INTEGER")
        get_db().commit()
        logger.info("Added missing column user.recap_email_sent_year")
    except sqlite3.OperationalError:
        pass


_LEAK_MARKERS = ("{{", "{%", "%(", "Traceback", "NaN", "None rides")


def _preflight(users, year):
    """Dry-run only: render every recipient's recap page + share image, log aggregates (no names)."""
    from urllib.parse import quote

    from hitch.blueprints.user import _year_recap

    statuses, png_statuses, times = {}, {}, []
    zero = leaks = 0
    client = current_app.test_client()
    for u in users:
        path = f"/insights/{quote(u.username, safe='')}/{year}"
        t0 = time.perf_counter()
        try:
            r = client.get(path)
            code = r.status_code
            body = r.get_data(as_text=True) if code == 200 else ""
        except Exception:
            code, body = "exception", ""
        times.append((time.perf_counter() - t0) * 1000)
        statuses[code] = statuses.get(code, 0) + 1
        if any(m in body for m in _LEAK_MARKERS):
            leaks += 1
        try:
            if _year_recap(u.username, year)["rides"] == 0:
                zero += 1
        except Exception:
            zero += 1
        try:
            pc = client.get(path + ".png").status_code
        except Exception:
            pc = "exception"
        png_statuses[pc] = png_statuses.get(pc, 0) + 1
    times.sort()
    n = len(times)
    p50 = times[n // 2] if n else 0
    p95 = times[min(n - 1, int(n * 0.95))] if n else 0
    logger.info(
        f"PREFLIGHT {n} recipients: page status {statuses}, png status {png_statuses}, "
        f"{zero} with 0 rides in {year}, {leaks} with template-leak strings, p50 {p50:.0f} ms, p95 {p95:.0f} ms"
    )


def run():
    _ensure_column()
    year = int(os.environ.get("RECAP_EMAIL_YEAR") or datetime.now(timezone.utc).year)
    users = eligible_users(year)
    # Aggregate only: never log addresses or names in a dry run.
    logger.info(f"{len(users)} accounts eligible for the {year} recap email")
    # last_ride_at is a submission-time proxy; the recap page counts by ride start. Preflight
    # 2026-11-25 found 18 of 145 whose page shows 0 rides: do not mail those an empty page.
    from hitch.blueprints.user import _year_recap

    with_rides = [u for u in users if _year_recap(u.username, year)["rides"] > 0]
    logger.info(f"{len(users) - len(with_rides)} of them have 0 rides in {year} on the recap page: skipped")
    users = with_rides
    # Aggregate reach check: of everyone who logged a ride in the year, how many the email can't reach.
    from hitch.models import User

    start, end = datetime(year, 1, 1), datetime(year + 1, 1, 1)
    loggers = User.query.filter(User.last_ride_at >= start, User.last_ride_at < end).all()
    no_optin = sum(1 for u in loggers if not u.email_notifications)
    no_email = sum(1 for u in loggers if not u.email or u.email.endswith("@hitchwiki.oauth"))
    logger.info(f"{len(loggers)} accounts with last ride in {year}: {no_optin} opted out, {no_email} no real email")

    if os.environ.get("RECAP_EMAIL_PREFLIGHT") == "1" and os.environ.get("RECAP_EMAIL_SEND") != "1":
        _preflight(users, year)

    if os.environ.get("RECAP_EMAIL_SEND") != "1":
        logger.info("Dry run: nothing sent. Set RECAP_EMAIL_SEND=1 to send.")
        return
    if not current_app.config.get("SPARKPOST_API_KEY"):
        logger.warning("SPARKPOST_API_KEY not set — not sending")
        return

    sent = 0
    for user in users:
        try:
            send_year_recap_email(user, year)
            user.recap_email_sent_year = year
            db.session.commit()
            sent += 1
        except Exception:
            db.session.rollback()
            logger.exception(f"Failed to send recap email to {user.username}")
        time.sleep(_SEND_PAUSE_S)
    logger.info(f"Done — {sent} recap emails sent")


run()
