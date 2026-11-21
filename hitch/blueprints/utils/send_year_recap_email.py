"""One-time "your year recap is ready" notice, sent via SparkPost.

Same transport as the inactive-user reminder. Who gets it (opt-in, non-synthetic,
logged a ride that year, not yet sent) is decided by hitch/scripts/send_year_recap_email.py.
"""

from datetime import datetime

from flask import render_template

from hitch.blueprints.utils.send_welcome_email import _send_via_sparkpost
from hitch.extensions import db
from hitch.models import User

# OAuth users with no real email get a synthetic, undeliverable address — never mail those.
_SYNTHETIC_EMAIL_SUFFIX = "@hitchwiki.oauth"


def send_year_recap_email(user, year):
    name = user.username or "there"
    html = render_template("email/year_recap.html", name=name, username=user.username, year=year)
    text = render_template("email/year_recap.txt", name=name, username=user.username, year=year)
    return _send_via_sparkpost(
        user.email, name, f"Your {year} recap is ready", html, text, transactional=False, campaign=f"year-recap-{year}"
    )


def eligible_users(year):
    """Users who should get the `year` recap notice (see module docstring)."""
    start = datetime(year, 1, 1)
    end = datetime(year + 1, 1, 1)
    candidates = User.query.filter(
        db.func.coalesce(User.total_rides, 0) >= 1,
        User.last_ride_at >= start,
        User.last_ride_at < end,
    ).all()
    return [
        u
        for u in candidates
        if u.email_notifications
        and u.email
        and not u.email.endswith(_SYNTHETIC_EMAIL_SUFFIX)
        and u.username
        and u.recap_email_sent_year != year
    ]
