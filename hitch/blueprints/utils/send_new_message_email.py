"""New-chat-message email, sent via SparkPost.

Reuses the same SparkPost transport as the welcome email
(`send_welcome_email._send_via_sparkpost`). Gating (recipient opted in, throttled to
once per unread burst) lives in the messages blueprint; this module only renders and
sends a single notification to one recipient.
"""

from flask import current_app, render_template

# Reuse the shared SparkPost transmission helper and the synthetic-address guard rather
# than duplicating them.
from hitch.blueprints.utils.send_welcome_email import _SYNTHETIC_EMAIL_SUFFIX, _send_via_sparkpost

MESSAGE_SUBJECT = "You have a new message on Hitchwiki Maps"


def send_new_message_email(recipient, sender_username, preview):
    """Email `recipient` that `sender_username` messaged them. Never raises.

    `preview` is a short excerpt of the message body for the email. A mail failure must not
    break sending the message itself, so all errors are swallowed and logged.
    """
    email = recipient.email or ""
    # OAuth users with no real address get a synthetic, undeliverable one — skip those.
    if not email or email.endswith(_SYNTHETIC_EMAIL_SUFFIX):
        return
    name = recipient.username or "there"
    try:
        html = render_template(
            "email/new_message.html", name=name, sender=sender_username, preview=preview
        )
        text = render_template(
            "email/new_message.txt", name=name, sender=sender_username, preview=preview
        )
        _send_via_sparkpost(email, name, MESSAGE_SUBJECT, html, text, transactional=False)
    except Exception:
        current_app.logger.exception("Failed to send new-message email to %s", email)
