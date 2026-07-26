"""Photo attachments for a ride: validation, storage on disk, and lookup.

Where the bytes live: `dist/ride-images/<yyyy>/<mm>/<uuid>.jpg`. `dist/` is the right
home for three independent reasons — it is bind-mounted into the container (so uploads
survive an image rebuild, and a deploy's `git reset --hard` cannot touch them), the whole
directory is gitignored (so nothing a visitor uploads can reach the repository), and the
catch-all route already serves it, so no extra endpoint is needed.

Every upload is decoded and re-encoded through Pillow rather than stored as received.
That is the entire security model here: the bytes we serve back are ones Pillow wrote, so
a file that is simultaneously a valid image and a valid HTML/script payload cannot
survive the round trip. Re-encoding also drops EXIF, which matters for consent as much as
for size — a phone photo carries GPS coordinates and a device serial, and someone
attaching a picture of a slip road is not choosing to publish where they live.

Validation happens *before* the ride is published to Nostr (`prepare_uploads`) and
storage only afterwards (`store_ride_images`), because the d tag a photo hangs off does
not exist until the relay publish returns. Splitting it this way means a broken or
oversized file is a plain form error, not a failure discovered after the ride is already
live and unrecallable.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from hitch.extensions import db
from hitch.helpers import dirs
from hitch.models import RideImage

logger = logging.getLogger(__name__)

# Requirement: at most three photos per ride. Enforced here rather than only in the
# browser, and counted against photos that already exist, so an edit cannot walk the
# total up three at a time.
MAX_IMAGES_PER_RIDE = 3

# Per-file cap on the *uploaded* bytes. A modern phone photo is 3-8 MB; 12 MB leaves room
# for that without letting one request buffer an arbitrary amount of memory. The
# app-wide MAX_CONTENT_LENGTH (settings.py) is the outer guard for the whole request.
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

# Longest side of the stored image. A ride photo is looked at on a phone or inline on the
# ride page; anything beyond this is bandwidth nobody sees. ~1600px keeps a stored JPEG
# in the low hundreds of KB.
MAX_DIMENSION = 1600
JPEG_QUALITY = 82

# Decompression-bomb guard: a 5 KB PNG can declare a 100k x 100k canvas, which Pillow
# would happily try to allocate. Pillow's own default only *warns* at ~89 Mpx; be
# explicit and refuse well below anything a real camera produces (50 Mpx ≈ 8600x5800).
Image.MAX_IMAGE_PIXELS = 50_000_000

# Formats we are willing to decode. Everything is re-encoded to JPEG regardless, so this
# list is about what a browser's file picker realistically hands us, not about output.
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF"}

RIDE_IMAGES_SUBDIR = "ride-images"

# The public URL prefix. dist/ride-images/<rel> is served by the catch-all route at
# /ride-images/<rel> — the two must stay in step.
RIDE_IMAGES_URL_PREFIX = "/" + RIDE_IMAGES_SUBDIR


class RideImageError(ValueError):
    """A rejected upload.

    Subclasses ValueError on purpose: the /ride POST handler already turns ValueError
    into "bad input, do not retry" (400 for the in-ride JSON client), which is exactly
    the right classification for a file the user must replace.
    """


class PreparedImage:
    """A validated, re-encoded image held in memory until the ride has a d tag."""

    __slots__ = ("data", "width", "height")

    def __init__(self, data, width, height):
        self.data = data
        self.width = width
        self.height = height


def ride_images_dir():
    return os.path.join(dirs["dist"], RIDE_IMAGES_SUBDIR)


def image_url(filename):
    """Public URL for a stored photo, e.g. "/ride-images/2026/07/<uuid>.jpg"."""
    return f"{RIDE_IMAGES_URL_PREFIX}/{filename}"


def images_for_ride(d_tag):
    """This ride's photos, oldest first (upload order is the display order)."""
    if not d_tag:
        return []
    return db.session.query(RideImage).filter_by(ride_d_tag=d_tag).order_by(RideImage.id.asc()).all()


def _reencode(raw):
    """Decode `raw`, downscale it, and return (jpeg_bytes, width, height).

    Raises RideImageError for anything Pillow can't read or that isn't a format we accept.
    """
    try:
        with Image.open(BytesIO(raw)) as img:
            image_format = img.format
            if image_format not in ALLOWED_FORMATS:
                raise RideImageError(f"Unsupported image format: {image_format or 'unknown'}.")
            # Honour the EXIF orientation flag *before* stripping EXIF, otherwise a photo
            # taken in portrait would be served on its side.
            img = ImageOps.exif_transpose(img)
            # Flatten to RGB: JPEG has no alpha channel, and a transparent PNG saved
            # straight to JPEG raises rather than compositing. White matches the page.
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                converted = img.convert("RGBA")
                background.paste(converted, mask=converted.split()[-1])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
            out = BytesIO()
            # No exif= argument, so the metadata of the source (GPS, serial, timestamps)
            # is simply not carried over.
            img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
            return out.getvalue(), img.width, img.height
    except RideImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as err:
        # Image.MAX_IMAGE_PIXELS trips as a plain ValueError ("exceeds limit"), a
        # truncated upload as OSError. Neither is worth distinguishing to the user.
        raise RideImageError("That file could not be read as an image.") from err


def prepare_uploads(files, allowance=MAX_IMAGES_PER_RIDE):
    """Validate and re-encode uploaded files, returning a list of PreparedImage.

    `files` is what request.files.getlist() gives: browsers submit an empty FileStorage
    for a file input the user left alone, so those are filtered out here rather than at
    every call site. `allowance` is how many more photos this ride may have.
    """
    candidates = [f for f in (files or []) if f and f.filename]
    if not candidates:
        return []
    if allowance <= 0:
        raise RideImageError(f"This ride already has {MAX_IMAGES_PER_RIDE} photos. Remove one before adding another.")
    if len(candidates) > allowance:
        raise RideImageError(f"You can add {allowance} more photo(s) to this ride — {len(candidates)} were selected.")

    prepared = []
    for upload in candidates:
        # Read one byte past the cap: a stream that still has data at that point is too
        # big, and we learn it without holding the whole thing.
        raw = upload.read(MAX_UPLOAD_BYTES + 1)
        if len(raw) > MAX_UPLOAD_BYTES:
            raise RideImageError(f"'{upload.filename}' is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
        if not raw:
            raise RideImageError(f"'{upload.filename}' is empty.")
        data, width, height = _reencode(raw)
        prepared.append(PreparedImage(data, width, height))
    return prepared


def store_ride_images(d_tag, prepared, user_id=None):
    """Write prepared photos to disk and link them to `d_tag`. Returns the saved rows.

    Never raises. By the time this runs the ride is already published to Nostr and stored
    locally, so a full disk or a failed write must cost the photo, not the ride.
    """
    if not d_tag or not prepared:
        return []
    saved = []
    try:
        # Month folders keep any single directory to a manageable number of entries, and
        # make "delete everything older than X" a directory operation if it's ever needed.
        now = datetime.now(timezone.utc)
        rel_dir = f"{now.year:04d}/{now.month:02d}"
        abs_dir = os.path.join(ride_images_dir(), rel_dir)
        os.makedirs(abs_dir, exist_ok=True)
        for item in prepared:
            # A uuid rather than the uploaded name: the original filename is attacker
            # controlled, may collide, and can itself carry personal information.
            filename = f"{rel_dir}/{uuid.uuid4().hex}.jpg"
            path = os.path.join(ride_images_dir(), filename)
            with open(path, "wb") as handle:
                handle.write(item.data)
            row = RideImage(
                ride_d_tag=d_tag,
                filename=filename,
                user_id=user_id,
                width=item.width,
                height=item.height,
            )
            db.session.add(row)
            saved.append(row)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Could not store ride photos for d_tag=%s", d_tag)
        # Leave no orphan file behind for a row that was rolled back.
        for row in saved:
            _unlink(row.filename)
        return []
    return saved


def delete_ride_images(image_ids, d_tag):
    """Remove the given photos, but only those belonging to `d_tag`.

    Scoping the delete by d tag is what stops a crafted form from removing photos off
    someone else's ride: the caller has already checked that this user may edit `d_tag`,
    and the ids are just checkbox values from the page.
    """
    ids = [i for i in (image_ids or []) if isinstance(i, int)]
    if not ids or not d_tag:
        return 0
    rows = db.session.query(RideImage).filter(RideImage.id.in_(ids), RideImage.ride_d_tag == d_tag).all()
    if not rows:
        return 0
    filenames = [row.filename for row in rows]
    for row in rows:
        db.session.delete(row)
    db.session.commit()
    # Files last: an orphaned file wastes disk, an orphaned row shows a broken image.
    for filename in filenames:
        _unlink(filename)
    return len(rows)


def _unlink(filename):
    try:
        os.remove(os.path.join(ride_images_dir(), filename))
    except OSError:
        logger.warning("Could not remove ride image file %s", filename)
