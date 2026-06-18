"""First-login welcome email, sent via SparkPost.

We reuse the Hitchwiki SparkPost account/credentials shared with the
hitchhiking-newsletter project (SPARKPOST_API_KEY / SPARKPOST_BASE_URL in the env)
and post directly to the transmissions API — the same mechanism as the newsletter
send script — rather than the SMTP2GO/Flask-Mailman path the rest of the app uses.

`maybe_send_welcome_email` is the gated entry point called from the OAuth login flow:
it sends at most once per user, ever, honours the user's email_notifications
preference, and never raises (a mail failure must not break login).
"""

import requests
from flask import current_app, render_template

from hitch.extensions import db

# OAuth users whose Hitchwiki profile carried no email get a synthetic, undeliverable
# address; never try to mail those.
_SYNTHETIC_EMAIL_SUFFIX = "@hitchwiki.oauth"

WELCOME_SUBJECT = "Welcome to the Hitchwiki Map"


def _send_via_sparkpost(to_email, to_name, subject, html, text):
    """POST a single transactional transmission to SparkPost. Raises on HTTP error."""
    base_url = current_app.config["SPARKPOST_BASE_URL"].rstrip("/")
    api_key = current_app.config["SPARKPOST_API_KEY"]
    payload = {
        # Transactional: this is a one-time account email, not marketing — so it is not
        # subject to list-unsubscribe suppression on SparkPost's side.
        "options": {"open_tracking": False, "click_tracking": False, "transactional": True},
        "content": {
            "from": {
                "email": current_app.config["WELCOME_FROM_EMAIL"],
                "name": current_app.config["WELCOME_FROM_NAME"],
            },
            "subject": subject,
            "html": html,
            "text": text,
        },
        "recipients": [{"address": {"email": to_email, "name": to_name or ""}}],
    }
    response = requests.post(
        f"{base_url}/transmissions",
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def send_welcome_email(user):
    """Render and send the welcome email to `user`. Raises on failure (no gating)."""
    name = user.username or "there"
    html = render_template("email/welcome.html", name=name)
    text = render_template("email/welcome.txt", name=name)
    return _send_via_sparkpost(user.email, name, WELCOME_SUBJECT, html, text)


def maybe_send_welcome_email(user):
    """Send the first-login welcome email once per user, if eligible. Never raises.

    Eligibility: not already sent, the user opted into email notifications, a real
    (deliverable) email address is on file, and SparkPost is configured. On a
    successful send we flip `welcome_email_sent` so it is never sent twice; on any
    failure we leave the flag unset so a later login retries.
    """
    if user.welcome_email_sent:
        return
    if not user.email_notifications:
        return
    if not user.email or user.email.endswith(_SYNTHETIC_EMAIL_SUFFIX):
        return
    if not current_app.config.get("SPARKPOST_API_KEY"):
        current_app.logger.warning("SPARKPOST_API_KEY not set — skipping welcome email")
        return

    try:
        send_welcome_email(user)
        user.welcome_email_sent = True
        db.session.commit()
        current_app.logger.info(f"Sent welcome email to {user.username} <{user.email}>")
    except Exception:
        # Roll back the (uncommitted) flag change and swallow — login must succeed
        # regardless. The unset flag means we retry on the user's next login.
        db.session.rollback()
        current_app.logger.exception(f"Failed to send welcome email to {user.username}")
