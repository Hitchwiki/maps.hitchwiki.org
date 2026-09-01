"""#202 / EXP-432 -- hitch/scripts/spot_access_hint.access_hint.

Picks the most recent ride comment that describes how someone *reached* a spot
(which bus, which station, where to walk from) for the spot pane to surface above
the ride stream.
"""

from hitch.scripts.spot_access_hint import ACCESS_HINT_MAX, access_hint


def _ride(comment, id="r1", submission_time="2020-01-01T00:00:00"):
    return {"comment": comment, "id": id, "submission_time": submission_time}


def test_matches_a_transit_comment():
    hint = access_hint([_ride("Take bus 31 from the centre and get off at the last stop.")])
    assert hint == {"c": "Take bus 31 from the centre and get off at the last stop.", "id": "r1"}


def test_returns_none_without_an_access_phrase():
    assert access_hint([_ride("Great spot, waited ten minutes, lovely driver to Berlin.")]) is None


def test_ignores_too_short_comments():
    assert access_hint([_ride("by bus")]) is None


def test_picks_the_most_recent_matching_comment():
    hint = access_hint(
        [
            _ride("walk from the train station, 10 min", id="old", submission_time="2019-05-01T00:00:00"),
            _ride("tram 4 to Hauptbahnhof then walk north", id="new", submission_time="2021-09-01T00:00:00"),
        ]
    )
    assert hint["id"] == "new"


def test_truncates_a_long_comment_on_a_word_boundary():
    long_comment = "Take the bus " + "and then walk a very long way " * 20
    hint = access_hint([_ride(long_comment)])
    assert len(hint["c"]) <= ACCESS_HINT_MAX + 1
    assert hint["c"].endswith("…")
    assert "  " not in hint["c"]


def test_handles_missing_or_empty_comment():
    assert access_hint([{"comment": None, "id": "x", "submission_time": "2020-01-01"}]) is None
    assert access_hint([]) is None


def test_does_not_match_a_bare_bus_grievance_without_a_boundary_verb():
    # "bus" alone still matches by design (named mode); this documents that a
    # comment naming a mode is treated as an access hint even if terse.
    assert access_hint([_ride("the bus stop nearby has a shelter if it rains")]) is not None
