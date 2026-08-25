"""One person, whatever case their name was typed in.

A Hitchwiki account arrives here spelled the way MediaWiki stores it ("Germanytoindia")
while the same person's imported hitchmap.com rides carry the spelling they used there
("GermanyToIndia"). Those used to be two identities: the rides sat on a stub page their
author could not edit and got no credit for. The rule under test (hitch/usernames.py) is
that names are compared case-insensitively over their whole length, and displayed the way
the registered account spells them.
"""

import json

import pytest

import hitch.blueprints.main as main
from hitch.blueprints.user import _get_rides_for_user, _query_rides_by_hitchhiker
from hitch.blueprints.utils.ride_facts import hitchhiker_name
from hitch.extensions import db as _db
from hitch.models import RideEvent, User
from hitch.usernames import canonical_username, find_user_ci, same_username, username_key
from tests.conftest import TEST_PUBKEY

# As the Hitchwiki account is spelled, and as the imported rides spell it.
ACCOUNT_NAME = "Germanytoindia"
RIDE_NAME = "GermanyToIndia"
UNIQUIFIER = "username-case-test-uniquifier"


def _ride(d_tag, nickname):
    content = {
        "version": "1.0.0",
        "source": "hitchmap.com",
        "comment": "picked up outside the services",
        "rating": 4,
        "submission_time": "2026-07-02T16:35:00",
        "license": "odbl",
        "hitchhikers": [{"nickname": nickname}],
        "stops": [
            {
                "location": {"latitude": 51.08170, "longitude": 13.73629, "is_exact": True},
                "departure_time": "2026-07-02T09:00:00",
                "waiting_duration": "PT12M",
            },
            {"location": {"latitude": 52.51739, "longitude": 13.39513, "is_exact": False}},
        ],
    }
    return RideEvent(
        id="e-" + d_tag,
        kind=36820,
        pubkey=TEST_PUBKEY,
        sig="s" * 128,
        created_at=1_800_000_000,
        content=content,
        source=content["source"],
        rating=4,
        comment=content["comment"],
        hitchhikers=content["hitchhikers"],
        stops=content["stops"],
        submission_time=content["submission_time"],
        d=d_tag,
        tags=[["d", d_tag], ["published_at", "1800000000"]],
    )


@pytest.fixture
def account(app):
    """The registered account, plus one ride logged under each spelling."""
    with app.app_context():
        _db.session.query(RideEvent).delete()
        _db.session.query(User).filter(User.fs_uniquifier == UNIQUIFIER).delete()
        user = User(
            username=ACCOUNT_NAME,
            email="germanytoindia@example.com",
            password="x",
            active=True,
            fs_uniquifier=UNIQUIFIER,
        )
        _db.session.add(user)
        _db.session.add_all([_ride("imported-ride", RIDE_NAME), _ride("logged-here", ACCOUNT_NAME)])
        _db.session.commit()
        yield user
        _db.session.query(RideEvent).delete()
        _db.session.query(User).filter(User.fs_uniquifier == UNIQUIFIER).delete()
        _db.session.commit()


class TestTheRule:
    def test_case_differences_anywhere_in_the_name_are_the_same_person(self):
        # Not just the first letter, which is all MediaWiki itself normalises.
        assert same_username(ACCOUNT_NAME, RIDE_NAME)
        assert username_key(RIDE_NAME) == username_key(ACCOUNT_NAME)

    def test_different_names_stay_different(self):
        assert not same_username("Germanytoindia", "Germanytoiran")

    def test_an_empty_name_matches_nobody(self):
        # Otherwise every ride with a missing nickname would belong to everyone.
        assert not same_username("", "")
        assert not same_username(None, "Germanytoindia")


class TestLookups:
    def test_a_differently_cased_name_finds_the_account(self, app, account):
        with app.app_context():
            assert find_user_ci(RIDE_NAME).username == ACCOUNT_NAME
            assert find_user_ci("GERMANYTOINDIA").username == ACCOUNT_NAME
            assert find_user_ci("someone-who-never-registered") is None

    def test_a_nickname_is_displayed_as_its_owners_account_spells_it(self, app, account):
        with app.app_context():
            assert canonical_username(RIDE_NAME) == ACCOUNT_NAME

    def test_an_unregistered_nickname_is_left_exactly_as_logged(self, app, account):
        with app.app_context():
            assert canonical_username("SomeHitchhiker") == "SomeHitchhiker"

    def test_anonymous_is_never_resolved_to_an_account(self, app, account):
        # The sentinel is a placeholder, not a person: every downstream filter tests for it.
        with app.app_context():
            assert canonical_username("Anonymous") == "Anonymous"
            assert hitchhiker_name([{"nickname": "Anonymous"}]) == "Anonymous"


class TestRideAttribution:
    def test_both_spellings_land_in_one_ride_history(self, app, account):
        with app.app_context():
            for name in (ACCOUNT_NAME, RIDE_NAME):
                found = {ride.d for ride in _query_rides_by_hitchhiker(name)}
                assert found == {"imported-ride", "logged-here"}

    def test_the_profile_lists_both_and_prints_one_name(self, app, account):
        with app.app_context():
            rides = _get_rides_for_user(account, display_only=True)
            assert {r["d_tag"] for r in rides} == {"imported-ride", "logged-here"}
            # A card showing "GermanyToIndia" next to one showing "Germanytoindia" reads
            # as two hitchhikers sharing a profile.
            assert {r["hitchhiker_name"] for r in rides} == {ACCOUNT_NAME}

    def test_the_owner_may_edit_a_ride_logged_under_the_other_spelling(self, app, account):
        with app.app_context():
            ride = _db.session.query(RideEvent).filter_by(d="imported-ride").first()
            assert main._user_is_hitchhiker(ride, account)
            assert account in main._ride_owner_users(ride)


class TestProfileUrl:
    def test_the_other_spelling_redirects_to_the_accounts_own_url(self, client, account):
        resp = client.get(f"/account/{RIDE_NAME}")
        assert resp.status_code == 301
        assert resp.headers["Location"].endswith(f"/account/{ACCOUNT_NAME}")

    def test_the_redirect_keeps_the_language_mirror(self, client, account):
        # Every route is mirrored under /<lang>; a redirect that drops the prefix would
        # throw a German reader back into English (see the language-mirror invariants).
        resp = client.get(f"/de/account/{RIDE_NAME}")
        assert resp.status_code == 301
        assert resp.headers["Location"].endswith(f"/de/account/{ACCOUNT_NAME}")

    def test_the_accounts_own_url_still_renders(self, client, account):
        assert client.get(f"/account/{ACCOUNT_NAME}").status_code == 200

    def test_is_username_used_is_case_insensitive(self, client, account):
        # The signup/co-hitchhiker check must not report a name free that would resolve
        # to an existing account.
        assert json.loads(client.get(f"/is_username_used/{RIDE_NAME.lower()}").data)["used"] is True
