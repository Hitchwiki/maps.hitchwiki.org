"""1:1 chat between registered users.

A conversation is just the set of Message rows between an unordered pair of users; there
is no conversation table. Opt-in gates who may write: to send a message to X, X must have
`allow_messages` enabled (this applies to replies too — a reply is still "writing to" the
other person). The Chat button on a profile only appears when the target opted in.
"""

from flask import Blueprint, jsonify, redirect, render_template, request
from flask_security import current_user
from sqlalchemy import and_, or_

from hitch.blueprints.utils.notifications import notify_new_message
from hitch.blueprints.utils.send_new_message_email import send_new_message_email
from hitch.extensions import db
from hitch.models import Message, Notification, User
from hitch.usernames import find_user_ci

messages_bp = Blueprint("messages", __name__)

# Hard cap on a single message so one POST can't store an unbounded blob.
MAX_MESSAGE_LEN = 4000
# How much of the body to put in the notification email preview.
EMAIL_PREVIEW_LEN = 140


def _pair_filter(a_id, b_id):
    """SQLAlchemy filter matching every message exchanged between users a and b (either
    direction). Used for both loading a thread and marking it read."""
    return or_(
        and_(Message.sender_id == a_id, Message.recipient_id == b_id),
        and_(Message.sender_id == b_id, Message.recipient_id == a_id),
    )


def _serialize(msg, me_id):
    """Message as the JSON the thread page renders. `mine` lets the UI right-align it."""
    return {
        "id": msg.id,
        "body": msg.body,
        "mine": msg.sender_id == me_id,
        "created_at": msg.created_at.strftime("%Y-%m-%d %H:%M") if msg.created_at else "",
    }


@messages_bp.route("/messages", methods=["GET"])
def inbox():
    """List the current user's conversations, most-recent message first."""
    if current_user.is_anonymous:
        return redirect("/login")

    # Every message the user is part of, newest first; collapse to one row per other user.
    rows = (
        Message.query.filter(or_(Message.sender_id == current_user.id, Message.recipient_id == current_user.id))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .all()
    )
    conversations = []
    seen = set()
    for msg in rows:
        other_id = msg.recipient_id if msg.sender_id == current_user.id else msg.sender_id
        if other_id in seen:
            continue
        seen.add(other_id)
        other = db.session.get(User, other_id)
        if other is None:
            continue
        # Unread = messages the other person sent me that I haven't opened.
        unread = Message.query.filter_by(sender_id=other_id, recipient_id=current_user.id, is_read=False).count()
        conversations.append(
            {
                "username": other.username,
                "preview": msg.body,
                "created_at": msg.created_at.strftime("%Y-%m-%d %H:%M") if msg.created_at else "",
                "unread": unread,
                "mine": msg.sender_id == current_user.id,
            }
        )

    return render_template("messages/inbox.html", conversations=conversations)


@messages_bp.route("/messages/<username>", methods=["GET"])
def thread(username):
    """Render the chat thread with `username` and mark their messages to me as read."""
    if current_user.is_anonymous:
        return redirect("/login")

    other = find_user_ci(username)
    if other is None:
        return redirect("/messages")
    # A conversation with yourself is meaningless.
    if other.id == current_user.id:
        return redirect("/messages")

    msgs = (
        db.session.query(Message).filter(_pair_filter(current_user.id, other.id)).order_by(Message.created_at, Message.id).all()
    )

    # Opening the thread clears the unread state for messages the other person sent me,
    # and marks the matching bell notification read so it doesn't linger after I've read
    # the actual messages (it otherwise only clears on a /me visit).
    unread = [m for m in msgs if m.recipient_id == current_user.id and not m.is_read]
    if unread:
        for m in unread:
            m.is_read = True
        Notification.query.filter_by(
            user_id=current_user.id, kind="message", link=f"/messages/{other.username}", is_read=False
        ).update({"is_read": True})
        db.session.commit()

    return render_template(
        "messages/thread.html",
        other=other,
        # Only the recipient's opt-in matters for whether *I* can send to *them*.
        can_send=bool(other.allow_messages),
        messages=[_serialize(m, current_user.id) for m in msgs],
        last_id=msgs[-1].id if msgs else 0,
    )


@messages_bp.route("/messages/<username>", methods=["POST"])
def send(username):
    """Send a message to `username`. Returns the stored message as JSON."""
    if current_user.is_anonymous:
        return jsonify({"error": "login_required"}), 401

    other = find_user_ci(username)
    if other is None:
        return jsonify({"error": "user_not_found"}), 404
    if other.id == current_user.id:
        return jsonify({"error": "cannot_message_self"}), 400
    # Enforce the recipient's opt-in on the server, not just by hiding the button: without
    # allow_messages, nobody (not even a reply in an existing thread) may write to them.
    if not other.allow_messages:
        return jsonify({"error": "messaging_disabled"}), 403

    body = (request.form.get("body") or "").strip()
    if not body:
        return jsonify({"error": "empty"}), 400
    body = body[:MAX_MESSAGE_LEN]

    msg = Message(sender_id=current_user.id, recipient_id=other.id, body=body)
    db.session.add(msg)
    db.session.commit()

    # In-app notification (drives the bell) is deduped-per-burst inside the helper.
    notify_new_message(other.id, current_user.username)

    # Email only on the *first* unread message of a burst: if the recipient already has an
    # unread message from me that predates this one, they've been notified and haven't
    # looked yet, so a live back-and-forth doesn't generate an email per line. Respects
    # their message_email_notifications opt-out.
    prior_unread = (
        Message.query.filter_by(sender_id=current_user.id, recipient_id=other.id, is_read=False)
        .filter(Message.id != msg.id)
        .count()
    )
    if other.message_email_notifications and prior_unread == 0:
        preview = body[:EMAIL_PREVIEW_LEN] + ("…" if len(body) > EMAIL_PREVIEW_LEN else "")
        send_new_message_email(other, current_user.username, preview)

    return jsonify(_serialize(msg, current_user.id))


@messages_bp.route("/messages/<username>/poll.json", methods=["GET"])
def poll(username):
    """New messages in the thread after `after` (message id). Powers live-ish updates.

    Also marks any of the other user's messages read, since the thread is open in front of
    the user when this fires.
    """
    if current_user.is_anonymous:
        return jsonify({"error": "login_required"}), 401
    other = find_user_ci(username)
    if other is None:
        return jsonify({"error": "user_not_found"}), 404

    after = request.args.get("after", type=int) or 0
    new_msgs = (
        db.session.query(Message).filter(_pair_filter(current_user.id, other.id), Message.id > after).order_by(Message.id).all()
    )

    unread = [m for m in new_msgs if m.recipient_id == current_user.id and not m.is_read]
    if unread:
        for m in unread:
            m.is_read = True
        db.session.commit()

    resp = jsonify({"messages": [_serialize(m, current_user.id) for m in new_msgs]})
    # Per-user private data — never let a shared cache serve one thread to another user.
    resp.headers["Cache-Control"] = "private, no-store"
    return resp
