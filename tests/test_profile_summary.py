import csv
import json
from datetime import datetime, timedelta

from hitch.profile_summary import conversation_stats, summarize, write_profile_summary


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


def test_conversation_stats():
    now = datetime(2026, 10, 6, 12)
    h = timedelta(hours=1)
    msgs = [(1, 2, now - 2 * h), (3, 4, now - 10 * 24 * h), (4, 3, now - 10 * 24 * h + 5 * h), (5, 6, now - 10 * 24 * h)]
    s = conversation_stats(msgs, now)
    assert s["messages_7d"] == 1 and s["new_conversations_7d"] == 1
    assert s["first_messages_judged_28d"] == 2 and s["first_messages_answered_pct"] == ""


def test_reply_rate_shown_with_enough_pairs():
    now = datetime(2026, 10, 6, 12)
    day = timedelta(days=1)
    msgs = []
    for i in range(6):
        msgs.append((i * 2, i * 2 + 1, now - 10 * day))
        if i < 3:
            msgs.append((i * 2 + 1, i * 2, now - 10 * day + timedelta(hours=1)))
    assert conversation_stats(msgs, now)["first_messages_answered_pct"] == 50
