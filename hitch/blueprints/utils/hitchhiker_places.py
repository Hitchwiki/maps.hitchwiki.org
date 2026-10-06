"""Where each hitchhiker is, as a point on the map — the data behind the map's
Hitchhikers mode (`dist/hitchhikers.json`, built by hitch/scripts/hitchhikers_map.py).

A user's place is the free text they typed on /edit-user, so it has to be geocoded.
Two places can be stated, and the map shows one per person:

- "Currently in" when it names a city and was updated within `CURRENT_MAX_AGE_DAYS` —
  the map answers "who is around here", and a traveller who said "Tbilisi" four months
  ago is not in Tbilisi any more. A country alone is too coarse to put a pin on.
- otherwise the hometown ("Where are you from?").

The point is the city's centre as Photon knows it, never anything finer: that is exactly
what the public profile already prints ("From Hamburg, Germany"), so the map reveals
nothing the profile doesn't. People in the same city share one point; the client's
cluster layer spiderfies them.

Geocodes are cached per (city, country) in `dist/place_geocode_cache.json` — city names
only, no user data, so it is harmless that dist/ is public. A place Photon answered with
nothing is cached as null and never retried (typos stay typos); a *failed request* caches
nothing, so an outage can't permanently drop people off the map.
"""

import json
import logging
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

CURRENT_MAX_AGE_DAYS = 90
PHOTON_URL = "https://photon.komoot.io/api/"
USER_AGENT = "hitchwiki-maps (https://maps.hitchwiki.org)"
# Photon asks for at most ~1 request/s from a client.
REQUEST_INTERVAL_S = 1.1
CACHE_FILENAME = "place_geocode_cache.json"
# Only settlements: without this a city qualified by the "wrong" country ("Copenhagen,
# France" — the dropdown is sometimes a nationality) matched a shop called "Flying Tiger
# Copenhagen", and "Moscow, Russian Federation" an intelligence agency's headquarters.
PHOTON_LAYERS = ("city", "locality", "district")
# How closely the result's name must resemble what was typed: loose enough for spelling
# and accents (Kiiv/Kyiv 0.75, Århus/Aarhus 0.91), tight enough to reject Photon's fuzzy
# fallbacks (Tbilisi/"Tifliser Platz", Haarlem/Haarberg 0.53). An exonym fails it
# (Praha/Prague 0.55), so a miss is re-checked against the place's local-language name.
MIN_NAME_SIMILARITY = 0.7


def _clean(text):
    return " ".join((text or "").split())


def cache_key(city, country):
    return f"{_clean(city).casefold()}|{_clean(country).casefold()}"


def chosen_place(user, now=None):
    """(city, country, kind, updated_at) for the place the map shows `user` at, or None.
    `user` is any object with the origin_*/current_* attributes. kind is "current" or "home"."""
    now = now or datetime.utcnow()
    current_city = _clean(getattr(user, "current_city", None))
    updated = getattr(user, "current_location_updated_at", None)
    if isinstance(updated, str):
        try:
            updated = datetime.fromisoformat(updated)
        except ValueError:
            updated = None
    if current_city and updated and now - updated <= timedelta(days=CURRENT_MAX_AGE_DAYS):
        return current_city, _clean(getattr(user, "current_country", None)), "current", updated
    home_city = _clean(getattr(user, "origin_city", None))
    if home_city:
        return home_city, _clean(getattr(user, "origin_country", None)), "home", None
    return None


def _photon(query, lang="en"):
    """Photon's best settlement for `query` as {"lat", "lon", "name"}, or None. `lang`
    picks the language of "name"; "default" is the place's own (Praha, not Prague)."""
    params = [("q", query), ("limit", "1"), ("lang", lang)] + [("layer", layer) for layer in PHOTON_LAYERS]
    req = urllib.request.Request(PHOTON_URL + "?" + urllib.parse.urlencode(params), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        features = json.load(resp).get("features") or []
    if not features:
        return None
    lon, lat = features[0]["geometry"]["coordinates"]
    return {"lat": round(lat, 4), "lon": round(lon, 4), "name": features[0]["properties"].get("name") or ""}


def _fold(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).replace("-", " ").split())


def resembles(typed, found):
    """Does Photon's place name `found` plausibly name the place the user `typed`?"""
    found = _fold(found)
    candidates = [typed] + re.split(r"[/,]|\s", typed)
    return any(SequenceMatcher(None, _fold(c), found).ratio() >= MIN_NAME_SIMILARITY for c in candidates if c.strip())


def _queries(city, country):
    # The country first, because a bare "Madison" or "Crest" is ambiguous; then the city
    # alone, because the country dropdown is sometimes the person's nationality rather
    # than the city's ("Copenhagen, France"); then the first word/segment, for people who
    # typed two places ("Häädemeeste/Tartu", "Paris Marseille").
    first = re.split(r"[/,]|\s", city)[0]
    tries = [f"{city}, {country}" if country else city, city, first]
    return [q for q in dict.fromkeys(tries) if q]


def geocode(city, country, cache, fetch=_photon, sleep=time.sleep):
    """{"lat", "lon"} for a typed place, or None. Fills `cache` in place."""
    key = cache_key(city, country)
    if key in cache:
        return cache[key]
    hit = None
    for query in _queries(_clean(city), _clean(country)):
        sleep(REQUEST_INTERVAL_S)
        found = fetch(query)  # raises on a failed request: nothing is cached then
        if found and not resembles(city, found.get("name", "")):
            sleep(REQUEST_INTERVAL_S)
            local = fetch(query, lang="default")
            found = local if local and resembles(city, local.get("name", "")) else None
        if found:
            hit = {"lat": found["lat"], "lon": found["lon"]}
            break
    cache[key] = hit
    return hit


def load_cache(dist_dir):
    try:
        with open(os.path.join(dist_dir, CACHE_FILENAME)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_cache(dist_dir, cache):
    path = os.path.join(dist_dir, CACHE_FILENAME)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cache, fh, ensure_ascii=False, sort_keys=True)
    os.replace(tmp, path)


def geocode_all(places, cache, limit=None, fetch=_photon, sleep=time.sleep):
    """Geocode every (city, country) not cached yet, at most `limit` new ones.
    Returns how many were looked up; request failures are logged and skipped."""
    looked_up = 0
    for city, country in places:
        if cache_key(city, country) in cache:
            continue
        if limit is not None and looked_up >= limit:
            break
        try:
            geocode(city, country, cache, fetch=fetch, sleep=sleep)
        except Exception as err:  # noqa: BLE001 — an outage must not abort the run
            logger.warning("geocoding %r, %r failed: %s", city, country, err)
        looked_up += 1
    return looked_up


def hitchhiker_entries(users, cache, avatars=None, now=None):
    """One map entry per user whose chosen place is geocoded, oldest account first.
    `avatars` maps user id -> image URL."""
    avatars = avatars or {}
    entries = []
    for user in users:
        place = chosen_place(user, now)
        if place is None:
            continue
        city, country, kind, updated = place
        point = cache.get(cache_key(city, country))
        if not point:
            continue
        entry = {
            "u": user.username,
            "lat": point["lat"],
            "lon": point["lon"],
            "place": ", ".join(x for x in (city, country) if x),
            "k": kind,
        }
        if updated is not None:
            entry["since"] = updated.strftime("%Y-%m-%d")
        if kind == "current" and _clean(getattr(user, "origin_city", None)):
            entry["from"] = ", ".join(x for x in (_clean(user.origin_city), _clean(user.origin_country)) if x)
        if getattr(user, "allow_messages", True):
            entry["msg"] = True
        if avatars.get(user.id):
            entry["img"] = avatars[user.id]
        entries.append(entry)
    return entries
