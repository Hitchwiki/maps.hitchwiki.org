"""Where to send a request for a city page that was never generated.

Every Hitchwiki place article links "See recent hitchhiking rides in and around X" to
/city/<Country>/<Article title>.html (Template:Infobox Location). cities.py only writes a
page for places that have rides, under GeoNames spelling ("Thessaloníki", "Qazvīn"), so on
2026-11-26 114 of 250 sampled wiki links answered with a bare Werkzeug 404 -- no map, no
navigation, a dead end for a reader who just asked to see rides.

The fix lives here rather than in the wiki template because the template is shared,
outward-facing wiki infrastructure, while this side can resolve the link with data it
already has: the generated files themselves.
"""

import os
import unicodedata
from urllib.parse import quote

# Country names the wiki uses that cities.py spells differently.
COUNTRY_ALIASES = {
    "united states of america": "united states",
    "usa": "united states",
    "england": "united kingdom",
    "england, uk": "united kingdom",
    "scotland": "united kingdom",
    "wales": "united kingdom",
    "northern ireland": "united kingdom",
    "uk": "united kingdom",
}


def _strip_disambiguation(name):
    """ "Richmond (Virginia)" -> "Richmond": the wiki disambiguates titles, GeoNames doesn't.

    Plain string ops, not a regex: this runs on the request path, and CodeQL flagged the
    regex as polynomial on crafted input.
    """
    name = name.rstrip()
    if name.endswith(")") and "(" in name:
        return name[: name.rindex("(")].strip()
    return name


def fold(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.replace("-", " ").replace("_", " ").split())


def _find(directory, wanted, suffix=""):
    """The entry of `directory` whose folded name (minus suffix) equals `wanted`, or None."""
    try:
        names = os.listdir(directory)
    except OSError:
        return None
    for name in names:
        if suffix and not name.endswith(suffix):
            continue
        stem = name[: -len(suffix)] if suffix else name
        if fold(stem) == wanted:
            return stem
    return None


def resolve_missing_city_page(city_dir, path):
    """(status, location) for a missing city/<country>/<name>.html request, or None to 404.

    301 to the existing page when the name only differs by accents/case/country spelling
    (the same place, permanently); otherwise 302 to the country view, which is still a map
    with that country's rides -- 302 because the city may get its own page once a ride is
    logged there.
    """
    if not (path.startswith("city/") and path.endswith(".html")):
        return None
    parts = path[len("city/") : -len(".html")].split("/")
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        return None
    country_raw, city_raw = parts
    country_key = fold(country_raw)
    country_key = COUNTRY_ALIASES.get(country_key, country_key)
    country = _find(city_dir, country_key)
    if country is None:
        return None

    country_path = os.path.join(city_dir, country)
    for candidate in (fold(city_raw), fold(_strip_disambiguation(city_raw))):
        if not candidate:
            continue
        city = _find(country_path, candidate, ".html")
        if city is not None:
            return 301, "/city/" + quote(country) + "/" + quote(city) + ".html"
    return 302, "/country/" + quote(country)
