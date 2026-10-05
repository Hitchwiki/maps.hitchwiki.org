"""Links to profiles elsewhere on the public profile (hitch/profile_links.py)."""

import json

import pytest

from hitch.extensions import db as _db
from hitch.models import User
from hitch.profile_links import describe_link, load_links, normalize_link

UQ = "profile-links-test-uniquifier"


@pytest.mark.parametrize(
    "url, label, icon",
    [
        ("https://www.instagram.com/hitcher", "Instagram", "fa-brands fa-instagram"),
        ("https://m.facebook.com/hitcher", "Facebook", "fa-brands fa-facebook"),
        ("https://twitter.com/hitcher", "X", "fa-brands fa-x-twitter"),
        ("https://bsky.app/profile/hitcher.bsky.social", "Bluesky", "fa-brands fa-bluesky"),
        ("https://www.youtube.com/@hitcher", "YouTube", "fa-brands fa-youtube"),  # /@ but not Mastodon
        ("https://mastodon.social/@hitcher", "Mastodon", "fa-brands fa-mastodon"),
        ("https://chaos.social/@hitcher", "Mastodon", "fa-brands fa-mastodon"),
        ("https://www.polarsteps.com/hitcher", "Polarsteps", "fa-solid fa-shoe-prints"),
        ("https://www.trustroots.org/profile/hitcher", "Trustroots", "fa-solid fa-tree"),
        ("https://www.my-travel-blog.net/about", "my-travel-blog.net", "fa-solid fa-globe"),
        ("https://notinstagram.com/x", "notinstagram.com", "fa-solid fa-globe"),  # suffix, not substring
    ],
)
def test_platform_detection(url, label, icon):
    assert describe_link(url) == {"url": url, "label": label, "icon": icon}


def test_normalize_adds_scheme_and_rejects_non_web_links():
    assert normalize_link("  instagram.com/hitcher ") == "https://instagram.com/hitcher"
    assert normalize_link("http://example.org") == "http://example.org"
    for bad in [
        "javascript:alert(1)",
        "javascript://example.com/%0aalert(1)",
        "data:text/html,x",
        "hello",
        "a b.com",
        "ftp://x.org",
    ]:
        with pytest.raises(ValueError):
            normalize_link(bad)


def test_load_links_tolerates_garbage():
    assert load_links(None) == [] and load_links("not json") == [] and load_links('{"a": 1}') == []
    assert load_links(json.dumps([f"https://e{i}.org" for i in range(9)])) == [f"https://e{i}.org" for i in range(5)]


@pytest.fixture
def me(app, client):
    with app.app_context():
        user = User(username="linkhitcher", email="l@example.com", password="x", active=True, fs_uniquifier=UQ)
        _db.session.add(user)
        _db.session.commit()
        uid = user.id
    with client.session_transaction() as s:
        s["_user_id"], s["_fresh"] = UQ, True
    yield uid
    with client.session_transaction() as s:
        s.clear()
    with app.app_context():
        _db.session.delete(_db.session.get(User, uid))
        _db.session.commit()


def _form(*links):
    data = {"gender": "", "origin_country": "", "distance_unit": "metric"}
    data.update({f"profile_links-{i}": link for i, link in enumerate(links)})
    return data


def test_links_are_saved_and_shown_with_icons(app, client, me):
    resp = client.post(
        "/edit-user", data=_form("instagram.com/linkhitcher", "", "https://mastodon.social/@lh", "instagram.com/linkhitcher")
    )
    assert resp.status_code == 302
    with app.app_context():
        assert load_links(_db.session.get(User, me).profile_links) == [
            "https://instagram.com/linkhitcher",
            "https://mastodon.social/@lh",
        ]

    page = client.get("/account/linkhitcher").data.decode()
    assert 'href="https://instagram.com/linkhitcher"' in page and "fa-brands fa-instagram" in page
    assert "fa-brands fa-mastodon" in page and 'rel="me nofollow ugc noopener"' in page
    assert "fontawesome-free@6.7.2" in page

    # The edit form shows what is stored; clearing every field removes them.
    assert 'value="https://mastodon.social/@lh"' in client.get("/edit-user").data.decode()
    assert client.post("/edit-user", data=_form()).status_code == 302
    with app.app_context():
        assert _db.session.get(User, me).profile_links is None


def test_invalid_link_rerenders_form_and_saves_nothing(app, client, me):
    resp = client.post("/edit-user", data=_form("https://ok.org", "javascript:alert(1)"))
    assert resp.status_code == 200
    assert "look like a web address" in resp.data.decode()
    with app.app_context():
        assert _db.session.get(User, me).profile_links is None
