"""Photos attached to a ride: validation, the draft upload flow, and where they show up.

Two things drive the design and so drive most of these tests:
  * nothing a visitor uploads is ever served back verbatim (the Pillow re-encode), and
  * a photo is uploaded when it is picked, not when the form is submitted, because the
    form navigates away to the map and a file input cannot survive that.
"""

import io
import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

import hitch.blueprints.main as main
from hitch.blueprints.utils import ride_images
from hitch.blueprints.utils.ride_images import (
    MAX_IMAGES_PER_RIDE,
    RideImageError,
    claim_draft_images,
    images_for_draft,
    images_for_ride,
    prepare_upload,
    store_draft_image,
    sweep_stale_drafts,
    valid_draft_token,
)
from hitch.extensions import db as _db
from hitch.models import RideEvent, RideImage, User

PUBKEY = "b" * 64
D_TAG = "maps.hitchwiki.org-photo"
OWNER_USERNAME = "photohitcher"
TOKEN = "d3b07384-d113-4ec3-9e33-000000000001"


class _FakeUpload:
    """Stands in for a werkzeug FileStorage: only .filename and .read() are used."""

    def __init__(self, filename, data):
        self.filename = filename
        self._stream = io.BytesIO(data)

    def read(self, size=-1):
        return self._stream.read(size)


def _png_bytes(size=(40, 30), color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_with_exif_gps():
    """A JPEG carrying an EXIF GPS tag, i.e. exactly what a phone hands us."""
    buf = io.BytesIO()
    img = Image.new("RGB", (60, 40), (10, 120, 200))
    exif = img.getexif()
    exif[0x8825] = {1: "N", 2: (52.0, 31.0, 0.0)}  # GPSInfo
    exif[0x010F] = "TestPhoneCorp"  # Make
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


@pytest.fixture
def image_dir(app, tmp_path, monkeypatch):
    """Redirect stored photos into a tmp dir so tests never write into dist/."""
    monkeypatch.setattr(ride_images, "ride_images_dir", lambda: str(tmp_path))
    with app.app_context():
        _db.session.query(RideImage).delete()
        _db.session.commit()
        yield tmp_path
        _db.session.query(RideImage).delete()
        _db.session.commit()


class TestPrepareUpload:
    """Pure validation — no app context, since nothing here touches the database."""

    def test_a_png_is_re_encoded_to_jpeg(self):
        prepared = prepare_upload(_FakeUpload("spot.png", _png_bytes()))
        # The stored bytes are Pillow's, not the uploader's — the format changed.
        assert Image.open(io.BytesIO(prepared.data)).format == "JPEG"
        assert (prepared.width, prepared.height) == (40, 30)

    def test_exif_including_gps_is_stripped(self):
        # A photo of a road should not publish where the phone was standing, nor which
        # phone it was. This is the reason we re-encode rather than store as received.
        source = _jpeg_with_exif_gps()
        assert Image.open(io.BytesIO(source)).getexif().get(0x8825) is not None

        prepared = prepare_upload(_FakeUpload("phone.jpg", source))

        stored_exif = Image.open(io.BytesIO(prepared.data)).getexif()
        assert stored_exif.get(0x8825) is None
        assert stored_exif.get(0x010F) is None

    def test_an_oversized_image_is_downscaled(self):
        prepared = prepare_upload(_FakeUpload("big.png", _png_bytes(size=(4000, 2000))))
        assert max(prepared.width, prepared.height) == ride_images.MAX_DIMENSION

    def test_a_transparent_png_survives_the_flatten_to_jpeg(self):
        # RGBA saved straight to JPEG raises; the alpha has to be composited first.
        buf = io.BytesIO()
        Image.new("RGBA", (20, 20), (255, 0, 0, 0)).save(buf, format="PNG")
        prepared = prepare_upload(_FakeUpload("logo.png", buf.getvalue()))
        assert Image.open(io.BytesIO(prepared.data)).mode == "RGB"

    def test_a_file_that_is_not_an_image_is_rejected(self):
        # The payload here is a valid HTML document with an image-ish name — the exact
        # thing that must never reach dist/ and be served back.
        with pytest.raises(RideImageError):
            prepare_upload(_FakeUpload("evil.jpg", b"<html><script>alert(1)</script></html>"))

    def test_an_empty_file_is_rejected(self):
        with pytest.raises(RideImageError):
            prepare_upload(_FakeUpload("nothing.jpg", b""))

    def test_a_file_over_the_byte_cap_is_rejected(self, monkeypatch):
        monkeypatch.setattr(ride_images, "MAX_UPLOAD_BYTES", 100)
        with pytest.raises(RideImageError):
            prepare_upload(_FakeUpload("big.png", _png_bytes(size=(200, 200))))

    def test_a_missing_file_is_rejected(self):
        # A browser posts a FileStorage with an empty filename for an untouched input.
        with pytest.raises(RideImageError):
            prepare_upload(_FakeUpload("", b""))
        with pytest.raises(RideImageError):
            prepare_upload(None)


class TestDraftTokens:
    def test_only_token_shaped_strings_are_accepted(self):
        # The token is the key that grants access to a draft's photos, so it is validated
        # before it ever reaches a query.
        assert valid_draft_token(TOKEN) == TOKEN
        assert valid_draft_token("  " + TOKEN + " ") == TOKEN
        assert valid_draft_token("short") is None
        assert valid_draft_token("' OR 1=1 --") is None
        assert valid_draft_token("x" * 65) is None
        assert valid_draft_token(None) is None


class TestDraftStorage:
    def test_storing_writes_a_file_and_an_unclaimed_row(self, app, image_dir):
        with app.app_context():
            row = store_draft_image(TOKEN, prepare_upload(_FakeUpload("spot.png", _png_bytes())))

            assert os.path.isfile(os.path.join(image_dir, row.filename))
            # The uploaded name is never reused: it is attacker-controlled and can carry
            # personal information of its own.
            assert "spot" not in row.filename
            assert row.filename.endswith(".jpg")
            # Unclaimed until a ride exists to claim it.
            assert row.ride_d_tag is None
            assert row.draft_token == TOKEN
            assert [r.id for r in images_for_draft(TOKEN)] == [row.id]

    def test_a_write_failure_is_reported_rather_than_silently_swallowed(self, app, image_dir, monkeypatch):
        # Nothing has been published at draft time, so the honest answer to the browser
        # is "that didn't work" — unlike the post-publish path, where the ride must win.
        def _boom(*args, **kwargs):
            raise OSError("disk full")

        with app.app_context():
            prepared = prepare_upload(_FakeUpload("spot.png", _png_bytes()))
            monkeypatch.setattr("builtins.open", _boom)
            with pytest.raises(RideImageError):
                store_draft_image(TOKEN, prepared)
            monkeypatch.undo()
            assert images_for_draft(TOKEN) == []

    def test_claiming_moves_photos_onto_the_ride(self, app, image_dir):
        with app.app_context():
            store_draft_image(TOKEN, prepare_upload(_FakeUpload("a.png", _png_bytes())))
            store_draft_image(TOKEN, prepare_upload(_FakeUpload("b.png", _png_bytes())))

            claimed = claim_draft_images(TOKEN, D_TAG)

            assert len(claimed) == 2
            assert len(images_for_ride(D_TAG)) == 2
            # No longer a draft, so the sweeper can never take them.
            assert images_for_draft(TOKEN) == []

    def test_claiming_never_pushes_a_ride_over_the_cap(self, app, image_dir):
        # The token travels through the browser, so the count that matters is the one at
        # claim time — not the one checked when each photo was uploaded.
        with app.app_context():
            for i in range(MAX_IMAGES_PER_RIDE + 2):
                store_draft_image(TOKEN, prepare_upload(_FakeUpload(f"{i}.png", _png_bytes())))

            claim_draft_images(TOKEN, D_TAG)

            assert len(images_for_ride(D_TAG)) == MAX_IMAGES_PER_RIDE

    def test_stale_drafts_are_swept_but_claimed_photos_are_untouched(self, app, image_dir):
        with app.app_context():
            old = store_draft_image(TOKEN, prepare_upload(_FakeUpload("old.png", _png_bytes())))
            fresh = store_draft_image(TOKEN, prepare_upload(_FakeUpload("fresh.png", _png_bytes())))
            claimed = store_draft_image(TOKEN + "x", prepare_upload(_FakeUpload("kept.png", _png_bytes())))
            claim_draft_images(TOKEN + "x", D_TAG)

            stale = datetime.now(timezone.utc).replace(tzinfo=None) - ride_images.DRAFT_TTL - timedelta(minutes=1)
            old_path = os.path.join(image_dir, old.filename)
            old.created_at = stale
            # A claimed photo is old too — it must survive on the draft_token IS NOT NULL
            # condition alone, not on its age.
            claimed.created_at = stale
            _db.session.commit()

            assert sweep_stale_drafts() == 1

            assert not os.path.exists(old_path)
            assert [r.id for r in images_for_draft(TOKEN)] == [fresh.id]
            assert len(images_for_ride(D_TAG)) == 1


class _StubEvent:
    def __init__(self, raw):
        self._raw = raw

    def to_dict(self):
        return self._raw


class _RecordingPoster:
    """Publishes nothing, but hands back a signed-looking event with a fixed d tag."""

    def __init__(self):
        self.last_event = None

    def post(self, ride_record, tags=None, d_tag=None):
        tag = D_TAG
        if tags is not None:
            tag = next(t[1] for t in tags if t[0] == "d")
        content = {
            "version": "1.0.0",
            "source": "maps.hitchwiki.org",
            "comment": "photo ride",
            "rating": 4,
            "submission_time": "2026-07-26T10:00:00",
            # Named rather than Anonymous so the edit tests below can own this ride
            # (_user_owns_ride matches the logged-in username against this list).
            "hitchhikers": [{"nickname": OWNER_USERNAME}],
            "stops": [{"location": {"latitude": 51.0817, "longitude": 13.73629}}],
        }
        self.last_event = _StubEvent(
            {
                "id": "img-event",
                "kind": 36820,
                "pubkey": PUBKEY,
                "sig": "s" * 128,
                "created_at": 1_800_000_000,
                "content": json.dumps(content),
                "tags": [["d", tag]],
            }
        )
        return tag

    def close(self):
        pass


@pytest.fixture
def clean_rides(app):
    with app.app_context():
        _db.session.query(RideEvent).delete()
        _db.session.commit()
        yield
        _db.session.query(RideEvent).delete()
        _db.session.commit()


@pytest.fixture
def owner(app, client):
    """Log in the user listed as the ride's hitchhiker, so the edit path is authorised.

    Login is Hitchwiki OAuth (no local password form to POST), so seed Flask-Login's
    session key directly — the same thing login_user() ultimately does.
    """
    with app.app_context():
        user = User(
            username=OWNER_USERNAME,
            email="photohitcher@example.com",
            password="x",
            active=True,
            fs_uniquifier="ride-images-test-uniquifier",
        )
        _db.session.add(user)
        _db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess["_user_id"] = "ride-images-test-uniquifier"
        sess["_fresh"] = True

    yield user_id

    with client.session_transaction() as sess:
        sess.clear()
    with app.app_context():
        user = _db.session.get(User, user_id)
        if user:
            _db.session.delete(user)
            _db.session.commit()


def _upload(client, name="spot.png", token=TOKEN, data=None):
    return client.post(
        "/ride-image",
        data={"image": (io.BytesIO(data or _png_bytes()), name), "draft_token": token},
        content_type="multipart/form-data",
    )


class TestUploadEndpoint:
    def test_a_photo_uploads_immediately_under_the_draft_token(self, app, client, image_dir):
        resp = _upload(client)

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["url"].startswith("/ride-images/")
        with app.app_context():
            assert len(images_for_draft(TOKEN)) == 1

    def test_several_photos_accumulate_instead_of_replacing_each_other(self, app, client, image_dir):
        # The bug this whole flow exists to fix: picking photos one at a time used to
        # keep only the last, because re-opening the file picker replaces the FileList.
        _upload(client, "one.png")
        _upload(client, "two.png")

        with app.app_context():
            assert len(images_for_draft(TOKEN)) == 2

    def test_the_cap_is_enforced_per_draft(self, app, client, image_dir):
        for i in range(MAX_IMAGES_PER_RIDE):
            assert _upload(client, f"{i}.png").status_code == 200

        resp = _upload(client, "one-too-many.png")

        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False
        with app.app_context():
            assert len(images_for_draft(TOKEN)) == MAX_IMAGES_PER_RIDE

    def test_a_bad_file_is_a_400_not_a_500(self, app, client, image_dir):
        resp = _upload(client, "evil.jpg", data=b"<html><script>alert(1)</script></html>")

        assert resp.status_code == 400
        assert "error" in resp.get_json()
        with app.app_context():
            assert images_for_draft(TOKEN) == []

    def test_a_missing_or_malformed_token_is_refused(self, app, client, image_dir):
        assert _upload(client, token="").status_code == 400
        assert _upload(client, token="../../etc").status_code == 400

    def test_the_draft_listing_lets_the_form_redraw_its_tiles(self, app, client, image_dir):
        # Picking a pickup location navigates the page away; the token survives in
        # sessionStorage and this endpoint rebuilds the strip on return.
        _upload(client, "one.png")

        body = client.get(f"/ride-image/draft/{TOKEN}").get_json()

        assert len(body["images"]) == 1
        assert body["images"][0]["url"].startswith("/ride-images/")


class TestDeleteEndpoint:
    def test_the_x_removes_a_draft_photo_for_whoever_holds_the_token(self, app, client, image_dir):
        image_id = _upload(client).get_json()["id"]

        resp = client.post(f"/ride-image/{image_id}/delete", data={"draft_token": TOKEN})

        assert resp.status_code == 200
        with app.app_context():
            assert images_for_draft(TOKEN) == []

    def test_a_draft_photo_cannot_be_deleted_without_its_token(self, app, client, image_dir):
        image_id = _upload(client).get_json()["id"]

        assert client.post(f"/ride-image/{image_id}/delete", data={"draft_token": "nope-nope-nope"}).status_code == 403
        with app.app_context():
            assert len(images_for_draft(TOKEN)) == 1

    def test_deleting_an_already_deleted_photo_is_not_an_error(self, app, client, image_dir):
        # A double-click must not surface an error: the tile is already gone.
        assert client.post("/ride-image/999999/delete", data={"draft_token": TOKEN}).status_code == 200

    def test_a_rides_photo_cannot_be_deleted_by_a_stranger(self, app, client, image_dir, clean_rides, monkeypatch):
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        _upload(client)
        _submit(client)
        with app.app_context():
            image_id = images_for_ride(D_TAG)[0].id

        # Not logged in, and the photo is no longer a draft, so the token means nothing.
        resp = client.post(f"/ride-image/{image_id}/delete", data={"draft_token": TOKEN})

        assert resp.status_code == 403
        with app.app_context():
            assert len(images_for_ride(D_TAG)) == 1

    def test_the_rides_owner_can_delete_its_photo(self, app, client, image_dir, clean_rides, monkeypatch, owner):
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        _upload(client)
        _submit(client)
        with app.app_context():
            row = images_for_ride(D_TAG)[0]
            image_id, path = row.id, os.path.join(image_dir, row.filename)

        assert client.post(f"/ride-image/{image_id}/delete", data={}).status_code == 200

        with app.app_context():
            assert images_for_ride(D_TAG) == []
        assert not os.path.exists(path)


def _submit(client, edit_d_tag="", token=TOKEN):
    return client.post(
        "/ride",
        data={
            "rate": "4",
            "wait": "12",
            "signal": "thumb",
            "comment": "photo ride",
            "pickup_lat": "51.08170",
            "pickup_lon": "13.73629",
            "destination_lat": "",
            "destination_lon": "",
            "edit_d_tag": edit_d_tag,
            "draft_token": token,
        },
    )


class TestRideSubmit:
    def test_submitting_claims_the_draft_and_the_photos_show_on_the_ride_page(
        self, app, client, monkeypatch, image_dir, clean_rides
    ):
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        _upload(client, "one.png")
        _upload(client, "two.png")

        assert _submit(client).status_code == 302

        with app.app_context():
            stored = images_for_ride(D_TAG)
            assert len(stored) == 2
            urls = [f"/ride-images/{img.filename}" for img in stored]

        page = client.get(f"/ride/{D_TAG}").get_data(as_text=True)
        for url in urls:
            assert url in page

    def test_a_ride_without_photos_still_submits(self, app, client, monkeypatch, image_dir, clean_rides):
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)

        assert _submit(client, token="").status_code == 302
        with app.app_context():
            assert _db.session.query(RideEvent).filter_by(d=D_TAG).count() == 1
            assert images_for_ride(D_TAG) == []

    def test_editing_a_ride_adds_to_its_photos(self, app, client, monkeypatch, image_dir, clean_rides, owner):
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        _upload(client, "one.png")
        _submit(client)

        second = "d3b07384-d113-4ec3-9e33-000000000002"
        _upload(client, "two.png", token=second)
        assert _submit(client, edit_d_tag=D_TAG, token=second).status_code == 302

        with app.app_context():
            assert len(images_for_ride(D_TAG)) == 2

    def test_a_stranger_editing_a_ride_cannot_attach_photos_to_it(self, app, client, monkeypatch, image_dir, clean_rides):
        # Not logged in, so the edit is refused before the claim is ever reached.
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        _submit(client, token="")

        second = "d3b07384-d113-4ec3-9e33-000000000003"
        _upload(client, "sneaky.png", token=second)
        resp = _submit(client, edit_d_tag=D_TAG, token=second)

        assert resp.headers["Location"] == "/#error"
        with app.app_context():
            assert images_for_ride(D_TAG) == []

    def test_the_edit_form_shows_the_owners_photos_as_tiles(self, app, client, monkeypatch, image_dir, clean_rides, owner):
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        _upload(client)
        _submit(client)
        with app.app_context():
            filename = images_for_ride(D_TAG)[0].filename

        page = client.get(f"/ride?edit={D_TAG}").get_data(as_text=True)

        assert f"/ride-images/{filename}" in page
        assert "ride-photo-tiles" in page

    def test_a_fresh_rides_photos_reach_the_spot_pane_before_show_py_runs(
        self, app, client, monkeypatch, image_dir, clean_rides, tmp_path
    ):
        # The spot pane's image strip is fed by the per-spot files, which regenerate
        # every ~10 min; /pending_rides.json is what closes that gap for the ride card,
        # so it has to carry the photos too or the strip trails the card.
        monkeypatch.setattr(main, "_last_generation_ts", lambda: 0)
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        _upload(client)
        _submit(client)

        entries = client.get("/pending_rides.json").get_json()

        entry = next(e for e in entries if e["id"] == D_TAG)
        assert len(entry["images"]) == 1
        assert entry["images"][0].startswith("/ride-images/")

    def test_photos_are_not_published_to_nostr(self, app, client, monkeypatch, image_dir, clean_rides):
        # The whole point of storing them locally: the ride event must be byte-identical
        # to one submitted without photos.
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        _upload(client)
        _submit(client)

        with app.app_context():
            ride = _db.session.query(RideEvent).filter_by(d=D_TAG).one()
            assert not ride.images
            assert "ride-images" not in json.dumps(ride.content)
