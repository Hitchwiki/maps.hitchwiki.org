"""Validation, storage, and URLs for opt-in public profile pictures."""

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

from hitch.blueprints.utils.ride_images import RideImageError, prepare_upload
from hitch.helpers import dirs

logger = logging.getLogger(__name__)

PROFILE_IMAGES_SUBDIR = "profile-images"
PROFILE_IMAGES_URL_PREFIX = "/profile-images"
AVATAR_SOURCES = {"none", "upload", "gravatar"}


def profile_images_dir():
    return os.path.join(dirs["dist"], PROFILE_IMAGES_SUBDIR)


def uploaded_image_url(filename):
    return f"{PROFILE_IMAGES_URL_PREFIX}/{filename}" if filename else None


def gravatar_url(email, size=400):
    """Return Gravatar's HTTPS image URL using its documented canonical SHA-256 hash."""
    canonical = (email or "").strip().lower().encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    query = urlencode({"s": max(1, min(int(size), 2048)), "r": "g", "d": "404"})
    return f"https://gravatar.com/avatar/{digest}?{query}"


def avatar_view(avatar, email):
    """Return template-safe display metadata, or None when no image was selected."""
    if avatar is None:
        return None
    if avatar.source == "upload" and avatar.filename:
        return {"url": uploaded_image_url(avatar.filename), "uploaded": True}
    if avatar.source == "gravatar" and email:
        return {"url": gravatar_url(email), "uploaded": False}
    return None


def store_uploaded_image(upload):
    """Re-encode one upload, store it under a random name, and return that name."""
    prepared = prepare_upload(upload)
    now = datetime.now(timezone.utc)
    rel_dir = f"{now.year:04d}/{now.month:02d}"
    filename = f"{rel_dir}/{uuid.uuid4().hex}.jpg"
    target_dir = os.path.join(profile_images_dir(), rel_dir)
    try:
        os.makedirs(target_dir, exist_ok=True)
        with open(os.path.join(profile_images_dir(), filename), "wb") as handle:
            handle.write(prepared.data)
    except OSError as err:
        logger.exception("Could not write a profile picture")
        raise RideImageError("The profile picture could not be saved. Please try again.") from err
    return filename


def delete_uploaded_image(filename):
    """Delete one known stored upload; random relative names never come from the request."""
    if not filename:
        return
    try:
        os.unlink(os.path.join(profile_images_dir(), filename))
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Could not delete old profile picture %s", filename)
