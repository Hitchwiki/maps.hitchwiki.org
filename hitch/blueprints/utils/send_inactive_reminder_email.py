"""Reminder email for users who signed up but haven't logged a ride yet, sent via SparkPost.

Reuses the same SparkPost transport as the welcome email
(`send_welcome_email._send_via_sparkpost`). The gating / who-to-send-to logic
(account age, ride count, opt-out, throttling) lives in the
`remind_inactive_users` script; this module only renders and sends one reminder.
"""

from flask import render_template

# Reuse the shared SparkPost transmission helper rather than duplicating it.
from hitch.blueprints.utils.send_welcome_email import _send_via_sparkpost

# Per-stage subject line. The 7-day nudge is a gentle "get started"; the 30-day one
# is the last nudge, so it reads a little differently.
_SUBJECTS = {
    7: "Log your first ride on the Hitchwiki Map",
    30: "Still hitchhiking? Add your rides to the map",
}


def send_inactive_reminder_email(user, stage):
    """Render and send the stage-`stage` inactive-user reminder to `user`.

    `stage` is the milestone in days (7 or 30); it selects both the subject and the
    template copy. Raises on send failure.
    """
    name = user.username or "there"
    html = render_template("email/inactive_reminder.html", name=name, stage=stage)
    text = render_template("email/inactive_reminder.txt", name=name, stage=stage)
    # Non-transactional: this is a recurring nudge, not a one-time account email, so it
    # must honour list-unsubscribe suppression on SparkPost's side.
    return _send_via_sparkpost(user.email, name, _SUBJECTS[stage], html, text, transactional=False)
