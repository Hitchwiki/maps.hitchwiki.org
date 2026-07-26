"""Photos attached to a ride: validation, storage, and where they show up.

The feature's security rests on one thing — nothing a visitor uploads is ever served
back verbatim — so most of these tests are about the re-encode, not about the happy path.
"""

import io
import json
import os

import pytest
from PIL import Image

import hitch.blueprints.main as main
from hitch.blueprints.utils import ride_images
from hitch.blueprints.utils.ride_images import (
    MAX_IMAGES_PER_RIDE,
    RideImageError,
    delete_ride_images,
    images_for_ride,
    prepare_uploads,
    store_ride_images,
)
from hitch.extensions import db as _db
from hitch.models import RideEvent, RideImage, User

PUBKEY = "b" * 64
D_TAG = "maps.hitchwiki.org-photo"
OWNER_USERNAME = "photohitcher"


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


class TestPrepareUploads:
    """Pure validation — no app context, since nothing here touches the database."""

    def test_a_png_is_re_encoded_to_jpeg(self):
        prepared = prepare_uploads([_FakeUpload("spot.png", _png_bytes())])
        assert len(prepared) == 1
        # The stored bytes are Pillow's, not the uploader's — the format changed.
        assert Image.open(io.BytesIO(prepared[0].data)).format == "JPEG"
        assert (prepared[0].width, prepared[0].height) == (40, 30)

    def test_exif_including_gps_is_stripped(self):
        # A photo of a road should not publish where the phone was standing, nor which
        # phone it was. This is the reason we re-encode rather than store as received.
        source = _jpeg_with_exif_gps()
        assert Image.open(io.BytesIO(source)).getexif().get(0x8825) is not None

        prepared = prepare_uploads([_FakeUpload("phone.jpg", source)])

        stored_exif = Image.open(io.BytesIO(prepared[0].data)).getexif()
        assert stored_exif.get(0x8825) is None
        assert stored_exif.get(0x010F) is None

    def test_an_oversized_image_is_downscaled(self):
        prepared = prepare_uploads([_FakeUpload("big.png", _png_bytes(size=(4000, 2000)))])
        assert max(prepared[0].width, prepared[0].height) == ride_images.MAX_DIMENSION

    def test_a_transparent_png_survives_the_flatten_to_jpeg(self):
        # RGBA saved straight to JPEG raises; the alpha has to be composited first.
        buf = io.BytesIO()
        Image.new("RGBA", (20, 20), (255, 0, 0, 0)).save(buf, format="PNG")
        prepared = prepare_uploads([_FakeUpload("logo.png", buf.getvalue())])
        assert Image.open(io.BytesIO(prepared[0].data)).mode == "RGB"

    def test_a_file_that_is_not_an_image_is_rejected(self):
        # The payload here is a valid HTML document with an image-ish name — the exact
        # thing that must never reach dist/ and be served back.
        with pytest.raises(RideImageError):
            prepare_uploads([_FakeUpload("evil.jpg", b"<html><script>alert(1)</script></html>")])

    def test_an_empty_file_is_rejected(self):
        with pytest.raises(RideImageError):
            prepare_uploads([_FakeUpload("nothing.jpg", b"")])

    def test_a_file_over_the_byte_cap_is_rejected(self, monkeypatch):
        monkeypatch.setattr(ride_images, "MAX_UPLOAD_BYTES", 100)
        with pytest.raises(RideImageError):
            prepare_uploads([_FakeUpload("big.png", _png_bytes(size=(200, 200)))])

    def test_more_files_than_the_allowance_are_rejected(self):
        uploads = [_FakeUpload(f"{i}.png", _png_bytes()) for i in range(MAX_IMAGES_PER_RIDE + 1)]
        with pytest.raises(RideImageError):
            prepare_uploads(uploads)

    def test_uploading_when_the_ride_is_already_full_is_rejected(self):
        with pytest.raises(RideImageError):
            prepare_uploads([_FakeUpload("one.png", _png_bytes())], allowance=0)

    def test_empty_file_inputs_are_ignored(self):
        # A browser posts a FileStorage with an empty filename for an untouched file
        # input; that is not an error, it means "no photo".
        assert prepare_uploads([_FakeUpload("", b"")]) == []
        assert prepare_uploads([]) == []
        assert prepare_uploads(None) == []


class TestStoreAndDelete:
    def test_storing_writes_a_file_and_a_row(self, app, image_dir):
        with app.app_context():
            prepared = prepare_uploads([_FakeUpload("spot.png", _png_bytes())])
            rows = store_ride_images(D_TAG, prepared, user_id=None)

            assert len(rows) == 1
            assert os.path.isfile(os.path.join(image_dir, rows[0].filename))
            # The uploaded name is never reused: it is attacker-controlled and can carry
            # personal information of its own.
            assert "spot" not in rows[0].filename
            assert rows[0].filename.endswith(".jpg")
            assert [r.id for r in images_for_ride(D_TAG)] == [rows[0].id]

    def test_a_write_failure_costs_the_photo_but_never_raises(self, app, image_dir, monkeypatch):
        # By the time photos are stored the ride is already on the relays, so a disk
        # problem must not turn a successful publish into a 500.
        def _boom(*args, **kwargs):
            raise OSError("disk full")

        with app.app_context():
            prepared = prepare_uploads([_FakeUpload("spot.png", _png_bytes())])
            monkeypatch.setattr("builtins.open", _boom)
            assert store_ride_images(D_TAG, prepared) == []
            monkeypatch.undo()
            assert images_for_ride(D_TAG) == []

    def test_deleting_removes_the_row_and_the_file(self, app, image_dir):
        with app.app_context():
            rows = store_ride_images(D_TAG, prepare_uploads([_FakeUpload("a.png", _png_bytes())]))
            path = os.path.join(image_dir, rows[0].filename)

            assert delete_ride_images([rows[0].id], D_TAG) == 1
            assert not os.path.exists(path)
            assert images_for_ride(D_TAG) == []

    def test_a_photo_of_another_ride_cannot_be_deleted(self, app, image_dir):
        # The ids come from checkbox values on a page, so the delete has to be scoped to
        # the ride the user was authorised to edit.
        with app.app_context():
            mine = store_ride_images("someone-elses-ride", prepare_uploads([_FakeUpload("a.png", _png_bytes())]))
            assert delete_ride_images([mine[0].id], D_TAG) == 0
            assert len(images_for_ride("someone-elses-ride")) == 1


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


class TestRideFormUpload:
    def _post(self, client, files, edit_d_tag="", extra=None):
        data = {
            "rate": "4",
            "wait": "12",
            "signal": "thumb",
            "comment": "photo ride",
            "pickup_lat": "51.08170",
            "pickup_lon": "13.73629",
            "destination_lat": "",
            "destination_lon": "",
            "edit_d_tag": edit_d_tag,
            "ride_images": files,
        }
        data.update(extra or {})
        return client.post("/ride", data=data, content_type="multipart/form-data")

    def test_a_photo_posted_with_the_ride_is_stored_and_shown_on_the_ride_page(
        self, app, client, monkeypatch, image_dir, clean_rides
    ):
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)

        resp = self._post(client, [(io.BytesIO(_png_bytes()), "spot.png")])
        assert resp.status_code == 302

        with app.app_context():
            stored = images_for_ride(D_TAG)
            assert len(stored) == 1
            url = f"/ride-images/{stored[0].filename}"

        page = client.get(f"/ride/{D_TAG}")
        assert page.status_code == 200
        assert url in page.get_data(as_text=True)

    def test_the_ride_is_still_published_when_no_photo_is_attached(self, app, client, monkeypatch, image_dir, clean_rides):
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)

        assert self._post(client, []).status_code == 302
        with app.app_context():
            assert _db.session.query(RideEvent).filter_by(d=D_TAG).count() == 1
            assert images_for_ride(D_TAG) == []

    def test_too_many_photos_are_refused_before_the_ride_is_published(self, app, client, monkeypatch, image_dir, clean_rides):
        # Validation runs before the Nostr publish on purpose: a rejected file must not
        # leave a ride on the relays that the user thinks failed.
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)

        files = [(io.BytesIO(_png_bytes()), f"{i}.png") for i in range(MAX_IMAGES_PER_RIDE + 1)]
        with pytest.raises(RideImageError):
            self._post(client, files)

        with app.app_context():
            assert _db.session.query(RideEvent).filter_by(d=D_TAG).count() == 0
            assert images_for_ride(D_TAG) == []

    def test_a_second_photo_can_be_added_by_editing_the_ride(self, app, client, monkeypatch, image_dir, clean_rides, owner):
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        self._post(client, [(io.BytesIO(_png_bytes()), "first.png")])

        resp = self._post(client, [(io.BytesIO(_png_bytes()), "second.png")], edit_d_tag=D_TAG)
        assert resp.status_code == 302

        with app.app_context():
            assert len(images_for_ride(D_TAG)) == 2

    def test_the_edit_form_lists_the_owners_photos_with_a_remove_box(
        self, app, client, monkeypatch, image_dir, clean_rides, owner
    ):
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        self._post(client, [(io.BytesIO(_png_bytes()), "first.png")])
        with app.app_context():
            filename = images_for_ride(D_TAG)[0].filename
            image_id = images_for_ride(D_TAG)[0].id

        page = client.get(f"/ride?edit={D_TAG}").get_data(as_text=True)
        assert f"/ride-images/{filename}" in page
        assert f'name="remove_image" value="{image_id}"' in page

    def test_ticking_remove_on_the_edit_form_deletes_the_photo(self, app, client, monkeypatch, image_dir, clean_rides, owner):
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)
        self._post(client, [(io.BytesIO(_png_bytes()), "first.png")])
        with app.app_context():
            image_id = images_for_ride(D_TAG)[0].id
            path = os.path.join(image_dir, images_for_ride(D_TAG)[0].filename)

        self._post(client, [], edit_d_tag=D_TAG, extra={"remove_image": str(image_id)})

        with app.app_context():
            assert images_for_ride(D_TAG) == []
        assert not os.path.exists(path)

    def test_photos_are_not_published_to_nostr(self, app, client, monkeypatch, image_dir, clean_rides):
        # The whole point of storing them locally: the ride event must be byte-identical
        # to one submitted without photos.
        monkeypatch.setattr(main, "HitchhikingDataStandardToNostrPoster", _RecordingPoster)

        self._post(client, [(io.BytesIO(_png_bytes()), "spot.png")])

        with app.app_context():
            ride = _db.session.query(RideEvent).filter_by(d=D_TAG).one()
            assert not ride.images
            assert "ride-images" not in json.dumps(ride.content)
