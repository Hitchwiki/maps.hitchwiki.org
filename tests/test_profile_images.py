"""Profile-picture upload, licensing display, and opt-in Gravatar tests."""

import hashlib
import io

import pytest
from PIL import Image

from hitch.blueprints.utils import profile_images
from hitch.extensions import db as _db
from hitch.models import User, UserAvatar


def _png_bytes():
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (20, 90, 160)).save(out, format="PNG")
    return out.getvalue()


def _form_data(**extra):
    # SelectField validates submitted values against its choices; send the form's explicit
    # empty choices rather than omitting them (which represents malformed browser input).
    return {"gender": "", "origin_country": "", "distance_unit": "metric", **extra}


@pytest.fixture
def profile_user(app, client):
    with app.app_context():
        user = User(
            username="avatarhitcher",
            email=" AvatarHitcher@Example.COM ",
            password="x",
            active=True,
            fs_uniquifier="profile-images-test-uniquifier",
        )
        _db.session.add(user)
        _db.session.commit()
        user_id = user.id

    with client.session_transaction() as session:
        session["_user_id"] = "profile-images-test-uniquifier"
        session["_fresh"] = True

    yield user_id

    with client.session_transaction() as session:
        session.clear()
    with app.app_context():
        UserAvatar.query.filter_by(user_id=user_id).delete()
        user = _db.session.get(User, user_id)
        if user:
            _db.session.delete(user)
        _db.session.commit()


@pytest.fixture
def profile_image_dir(tmp_path, monkeypatch):
    monkeypatch.setitem(profile_images.dirs, "dist", str(tmp_path))
    return tmp_path / "profile-images"


def test_gravatar_uses_documented_canonical_sha256_hash():
    expected = hashlib.sha256(b"avatarhitcher@example.com").hexdigest()
    url = profile_images.gravatar_url(" AvatarHitcher@Example.COM ")
    assert url == f"https://gravatar.com/avatar/{expected}?s=400&r=g&d=404"


def test_upload_is_reencoded_and_publicly_credited(app, client, profile_user, profile_image_dir):
    response = client.post(
        "/edit-user",
        data=_form_data(**{
            "avatar_source": "upload",
            "avatar_image": (io.BytesIO(_png_bytes()), "where-i-live.png"),
        }),
        content_type="multipart/form-data",
    )
    assert response.status_code == 302

    redirected = client.get("/me")
    assert b'profile_picture_saved' in redirected.data
    # The session marker is consumed: reloading the profile cannot double-count a save.
    assert b'profile_picture_saved' not in client.get("/me").data

    with app.app_context():
        avatar = UserAvatar.query.filter_by(user_id=profile_user).one()
        assert avatar.source == "upload"
        assert "where-i-live" not in avatar.filename
        stored = profile_image_dir / avatar.filename
        assert stored.exists()
        with Image.open(stored) as image:
            assert image.format == "JPEG"

    page = client.get("/account/avatarhitcher")
    assert page.status_code == 200
    assert b"Photo by avatarhitcher, CC BY-SA 4.0" in page.data
    assert b"/profile-images/" in page.data


def test_upload_source_requires_a_file(client, profile_user, profile_image_dir):
    response = client.post("/edit-user", data=_form_data(avatar_source="upload"))
    assert response.status_code == 200
    assert b"Choose a picture to upload." in response.data


def test_gravatar_is_opt_in_and_not_claimed_as_cc(app, client, profile_user):
    response = client.post("/edit-user", data=_form_data(avatar_source="gravatar"))
    assert response.status_code == 302

    page = client.get("/account/avatarhitcher")
    digest = hashlib.sha256(b"avatarhitcher@example.com").hexdigest().encode()
    assert digest in page.data
    assert b"Photo from Gravatar" in page.data
    assert b"CC BY-SA" not in page.data


def test_uploaded_profile_picture_has_long_immutable_cache(client):
    response = client.get("/profile-images/not-present.jpg")
    assert response.status_code == 404
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
