import csv
import json

from hitch.profile_summary import summarize, write_profile_summary


def _links(*urls):
    return json.dumps(list(urls))


def test_counts_and_groups():
    rows = [
        ("Hamburg", None, _links("https://instagram.com/a", "https://hitchwiki.org/x")),
        (" hamburg ", "Berlin", None),
        (None, "Berlin", _links("https://example.com")),
        (None, None, None),
    ]
    s = summarize(rows)
    assert s["users"] == 4 and s["with_origin_city"] == 2 and s["with_current_city"] == 2 and s["with_any_city"] == 3
    assert s["matchable_city_groups"] == 2 and s["largest_city_group"] == 2
    assert s["with_profile_link"] == 2
    assert (s["links_social"], s["links_hitch_community"], s["links_other"]) == (1, 1, 1)


def test_small_buckets_suppressed_and_no_names(tmp_path):
    p = tmp_path / "profile_summary.csv"
    write_profile_summary(str(p), summarize([("Hamburg", None, None)] * 2 + [(None, None, None)] * 10))
    text = p.read_text()
    assert "hamburg" not in text.lower()
    row = next(csv.DictReader(text.splitlines()))
    assert row["users"] == "12" and row["with_origin_city"] == "<5" and row["with_profile_link"] == "0"
