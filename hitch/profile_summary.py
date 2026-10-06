"""Aggregate profile-fill counts for the weekly growth read (IDEAS #632).

cities.py writes dist/profile_summary.csv from the user table. Counts only: no names,
no city names, no links. Any bucket under SUPPRESS_BELOW reads "<5" so a tiny cell
cannot single out a person. City groups are keyed on the city name alone (case-folded),
which slightly over-counts matches across countries; it is a growth signal, not a roster.
"""

import csv
import os
from collections import Counter

from hitch.profile_links import describe_link, load_links

SUPPRESS_BELOW = 5
_SOCIAL = {"Instagram", "Facebook", "X", "Bluesky", "Threads", "Mastodon", "TikTok", "Tumblr", "Pinterest"}
_SOCIAL |= {"Flickr", "VK", "Discord"}
_COMMUNITY = {"Hitchwiki", "Trustroots", "Couchsurfing", "BeWelcome", "Polarsteps", "Komoot", "Strava"}
LINK_CATEGORIES = {"social": _SOCIAL, "hitch_community": _COMMUNITY}


def _norm(text):
    return " ".join((text or "").split()).casefold()


def _category(url):
    label = describe_link(url)["label"]
    for name, labels in LINK_CATEGORIES.items():
        if label in labels:
            return name
    return "other"


def summarize(rows):
    """rows: iterable of (origin_city, current_city, profile_links_json) per active user."""
    users = origin = current = either = with_links = 0
    groups = {}
    cats = Counter()
    for origin_city, current_city, links_raw in rows:
        users += 1
        o, c = _norm(origin_city), _norm(current_city)
        origin += bool(o)
        current += bool(c)
        either += bool(o or c)
        for city in {o, c} - {""}:
            groups[city] = groups.get(city, 0) + 1
        links = load_links(links_raw)
        with_links += bool(links)
        for cat in {_category(u) for u in links}:
            cats[cat] += 1
    matchable = [n for n in groups.values() if n >= 2]
    return {
        "users": users,
        "with_origin_city": origin,
        "with_current_city": current,
        "with_any_city": either,
        "matchable_city_groups": len(matchable),
        "largest_city_group": max(matchable, default=0),
        "with_profile_link": with_links,
        "links_social": cats["social"],
        "links_hitch_community": cats["hitch_community"],
        "links_other": cats["other"],
    }


def _shown(value):
    return f"<{SUPPRESS_BELOW}" if 0 < value < SUPPRESS_BELOW else value


def write_profile_summary(path, summary):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(list(summary))
        w.writerow([_shown(v) for v in summary.values()])
    os.replace(tmp, path)
