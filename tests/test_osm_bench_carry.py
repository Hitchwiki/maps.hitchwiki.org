from types import SimpleNamespace as S

from hitch.osm_bench_carry import carry_forward


def spot(i, **tags):
    return S(id=i, tags=tags)


def test_keeps_named_bench_missing_tonight():
    prior = [
        spot(1, amenity="bench", name="Mitfahrbank Sielenbach"),
        spot(2, highway="hitchhiking"),
        spot(3, amenity="bench", name="Park bench"),
    ]
    assert [s.id for s in carry_forward(prior, seen_ids=set())] == [1]


def test_does_not_duplicate_or_resurrect_retagged_spot():
    prior = [spot(1, amenity="bench", name="Mitfahrbank X"), spot(2, highway="hitchhiking", name="Mitfahrbank Y")]
    assert carry_forward(prior, seen_ids={1}) == []


def test_tags_none_is_safe():
    assert carry_forward([S(id=9, tags=None)], set()) == []
