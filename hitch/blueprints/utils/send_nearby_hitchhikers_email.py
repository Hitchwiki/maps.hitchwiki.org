"""Daily "hitchhikers near you" digest email, sent via SparkPost.

Reuses the same SparkPost transport as the welcome email
(`send_welcome_email._send_via_sparkpost`). The gating / who-to-send-to logic
lives in the `notify_nearby_hitchhikers` script; this module only renders and
sends a single digest to one recipient.
"""

from flask import render_template

# Reuse the shared SparkPost transmission helper rather than duplicating it.
from hitch.blueprints.utils.send_welcome_email import _send_via_sparkpost

NEARBY_SUBJECT = "Hitchhikers who were close to you"


def send_nearby_hitchhikers_email(user, profiles):
    """Render and send the nearby-hitchhikers digest to `user`.

    `profiles` is a list of dicts describing the other users who were near `user`:
    {username, profile_url, location, hitchhiking_since}. Raises on send failure.
    """
    name = user.username or "there"
    html = render_template("email/nearby_hitchhikers.html", name=name, profiles=profiles)
    text = render_template("email/nearby_hitchhikers.txt", name=name, profiles=profiles)
    # Non-transactional: this is a recurring digest, not a one-time account email, so it
    # must honour list-unsubscribe suppression on SparkPost's side.
    return _send_via_sparkpost(
        user.email, name, NEARBY_SUBJECT, html, text, transactional=False, campaign="nearby-hitchhikers"
    )
