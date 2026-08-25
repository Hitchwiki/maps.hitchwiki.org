"""Anonymous co-hitchhikers may carry a gender, encoded in the co_hitchhiker form field.

The form posts a comma-separated list where a co-hitchhiker without an account is
"Anonymous", optionally suffixed ":male" / ":female". These tests pin that encoding and
the resulting Nostr hitchhikers, since the form (ride_form.html), the in-ride sheet
(inride.js) and the backend all have to agree on it.
"""

import pytest

from hitch.blueprints import publish_ride
from hitch.blueprints.publish_ride import (
    anonymous_co_hitchhiker_gender,
    anonymous_co_hitchhiker_token,
    create_record_from_custom_object,
    is_anonymous_co_hitchhiker,
)


@pytest.mark.parametrize(
    "token,expected",
    [
        ("Anonymous", True),
        ("Anonymous:male", True),
        (" Anonymous:female ", True),
        ("alice", False),
        # A real username can only be [a-zA-Z0-9]+, so nothing that merely starts with
        # the word may be mistaken for an anonymous entry.
        ("Anonymouse", False),
        ("", False),
    ],
)
def test_is_anonymous_co_hitchhiker(token, expected):
    assert is_anonymous_co_hitchhiker(token) is expected


@pytest.mark.parametrize(
    "token,expected",
    [
        ("Anonymous", None),
        ("Anonymous:male", "male"),
        ("Anonymous:female", "female"),
        # Anything we don't accept degrades to "unstated" rather than reaching Nostr.
        ("Anonymous:bogus", None),
        ("Anonymous:", None),
    ],
)
def test_anonymous_co_hitchhiker_gender(token, expected):
    assert anonymous_co_hitchhiker_gender(token) == expected


def test_anonymous_co_hitchhiker_token_round_trips():
    for gender in (None, "male", "female"):
        assert anonymous_co_hitchhiker_gender(anonymous_co_hitchhiker_token(gender)) == gender
    # Genders we don't offer collapse to a plain anonymous entry.
    assert anonymous_co_hitchhiker_token("non_binary") == "Anonymous"


def test_record_publishes_one_hitchhiker_per_anonymous_token(monkeypatch):
    """Named co-hitchhikers stay out of the event (they join on accepting the invite)."""
    monkeypatch.setattr(publish_ride, "current_user", type("Anon", (), {"is_anonymous": True})())

    record = create_record_from_custom_object(
        custom_object={
            "pickup_lat": 51.0,
            "pickup_lon": 13.0,
            "destination_lat": None,
            "destination_lon": None,
            "datetime_ride": "",
            "wait": None,
            "rate": 4,
            "comment": "",
            "signal": ["thumb"],
            "co_hitchhiker": "alice,Anonymous,Anonymous:male,Anonymous:female",
        },
        source="test",
        license="test",
    )

    assert [(h.nickname, h.gender) for h in record.hitchhikers] == [
        ("Anonymous", None),  # the (anonymous) submitter
        ("Anonymous", None),
        ("Anonymous", "male"),
        ("Anonymous", "female"),
    ]
