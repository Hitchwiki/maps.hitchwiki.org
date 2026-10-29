"""Self-serve account deletion (maps#484): erase the person, keep the published rides.

Rides are published to Nostr and mirrored to relays we do not control, so they stay (the
privacy policy and /delete-account say so). Everything that only exists on this server and
identifies or belongs to the account is removed; the `user` row itself is scrubbed and
deactivated rather than deleted, because public ride content still names the username as a
free-text nickname and other tables hold foreign keys to it. After the scrub nobody can log
in, the e-mail address and every profile field are gone, and the username is freed.
"""

import secrets

from hitch.blueprints.utils.profile_images import delete_uploaded_image
from hitch.extensions import db
from hitch.models import (
    Follow,
    Message,
    Notification,
    ProposedSpot,
    PushSubscription,
    RideComment,
    RideImage,
    RideLike,
    RideReport,
    Trip,
    TripRide,
    User,
    UserAvatar,
)

# Profile columns reset to their empty value. Counters go back to zero because they are
# derived from rides the account no longer owns.
_CLEARED_TO_NONE = (
    "gender",
    "year_of_birth",
    "hitchhiking_since",
    "origin_country",
    "origin_city",
    "current_country",
    "current_city",
    "current_location_updated_at",
    "hitchwiki_username",
    "trustroots_username",
    "profile_links",
    "last_ride_at",
    "lapsed_reminder_sent_for",
    "nearby_hitchhikers_email_last_sent",
    "recent_seen_at",
    "location_share_secret",
    "us_phone_number",
    "us_totp_secrets",
    "tf_phone_number",
    "tf_totp_secret",
    "tf_primary_method",
    "mf_recovery_codes",
    "fs_webauthn_user_handle",
    "confirmed_at",
    "last_login_ip",
    "current_login_ip",
)


def erase_account(user):
    """Delete `user`'s personal data in the current session (the caller commits)."""
    uid = user.id

    avatar = db.session.get(UserAvatar, uid)
    if avatar is not None:
        delete_uploaded_image(avatar.filename)
        db.session.delete(avatar)

    for model, column in (
        (Notification, Notification.user_id),
        (PushSubscription, PushSubscription.user_id),
        (RideLike, RideLike.user_id),
        (RideComment, RideComment.user_id),
        (RideReport, RideReport.user_id),
    ):
        db.session.query(model).filter(column == uid).delete(synchronize_session=False)
    db.session.query(Follow).filter((Follow.follower_id == uid) | (Follow.followed_id == uid)).delete(
        synchronize_session=False
    )
    db.session.query(Message).filter((Message.sender_id == uid) | (Message.recipient_id == uid)).delete(
        synchronize_session=False
    )

    trip_ids = [row[0] for row in db.session.query(Trip.id).filter(Trip.user_id == uid).all()]
    if trip_ids:
        db.session.query(TripRide).filter(TripRide.trip_id.in_(trip_ids)).delete(synchronize_session=False)
        db.session.query(Trip).filter(Trip.id.in_(trip_ids)).delete(synchronize_session=False)

    # Spots and photos belong to the map, not the person: keep them, drop the link.
    db.session.query(ProposedSpot).filter(ProposedSpot.user_id == uid).update(
        {"user_id": None, "username": None, "ip": None}, synchronize_session=False
    )
    db.session.query(RideImage).filter(RideImage.user_id == uid).update({"user_id": None}, synchronize_session=False)

    for column in _CLEARED_TO_NONE:
        setattr(user, column, None)
    user.username = None
    user.email = f"deleted-{uid}@deleted.invalid"
    user.password = secrets.token_urlsafe(48)  # unusable: nobody is told it
    user.fs_uniquifier = secrets.token_hex(16)  # invalidates every session and remember-me cookie
    user.active = False
    user.email_notifications = False
    user.message_email_notifications = False
    user.nearby_hitchhikers_email = False
    user.allow_messages = False
    user.total_rides = 0
    user.total_distance_km = 0
    user.total_waiting_time_min = 0
    return user
