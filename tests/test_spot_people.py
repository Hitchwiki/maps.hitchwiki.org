"""#458 -- hitch/scripts/spot_people.spot_people."""

from hitch.scripts.spot_people import MIN_PEOPLE_SHOWN, spot_people


def _r(name):
    return {"hitchhiker_name": name}


def test_counts_distinct_names_case_insensitively():
    assert spot_people([_r("Ann"), _r("ann "), _r("Bo"), _r("Cy"), _r("Di")]) == 4


def test_anonymous_and_missing_names_are_ignored():
    rides = [_r("Anonymous"), _r(None), _r(""), _r("A"), _r("B"), _r("C")]
    assert spot_people(rides) == 3


def test_below_the_floor_returns_none():
    assert MIN_PEOPLE_SHOWN == 3
    assert spot_people([_r("A"), _r("B"), _r("Anonymous")]) is None
    assert spot_people([]) is None
