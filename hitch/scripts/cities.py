"""Create separate HTML pages for major cities mentioned in hitchhiking reviews. Also for SEO purposes."""

import html
import json
import logging
import os
import urllib.parse
import zipfile
from datetime import date

import numpy as np
import pandas as pd
from flask import g
from jinja2 import Environment, FileSystemLoader

from hitch.helpers import get_db, get_dirs
from hitch.translations import SUPPORTED_LANGUAGES, t

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dirs = get_dirs()
dist_dir = dirs["dist"]

# Canonical site origin + per-city URL builder. Defined here (before the render
# loop) so each city page can embed a self-referencing canonical that matches,
# byte for byte, the sitemap entry built later.
SITE_URL = "https://maps.hitchwiki.org"


# How many cities get a page in every supported language. Deliberately not "all
# of them": 14.5k cities x 31 languages is ~450k pages (~7 GB) on a host that has
# run out of disk, and — the bigger reason — translating only the page furniture
# around user reviews that stay in their original language is thin, near-duplicate
# content at that scale, which search engines penalise across the whole domain.
# The cities anyone actually searches ("Trampen in Berlin") are all in the head of
# the ride-volume distribution, so a few hundred captures essentially all the value.
TOP_N_TRANSLATED = 400


def _city_slug(city_name):
    # cities.py writes "/" as "-" on disk; URLs must match byte for byte.
    return city_name.replace("/", "-")


def _city_loc(country, city_name, lang="en"):
    """Canonical URL of a city page in one language.

    English keeps the historical /city/... path (it is the canonical version and
    is already indexed under it); other languages take the /<lang> prefix every
    other translated route on the site uses — see register_blueprints.
    """
    country_seg = urllib.parse.quote(country)
    city_seg = urllib.parse.quote(f"{_city_slug(city_name)}.html")
    prefix = "" if lang == "en" else f"/{lang}"
    return f"{SITE_URL}{prefix}/city/{country_seg}/{city_seg}"


def _city_path(country, city_name, lang="en"):
    """Where that page lands under dist/, mirroring _city_loc's URL exactly.

    catch_all serves any dist/ path, so dist/de/city/... is reachable at
    /de/city/... with no routing change.
    """
    parts = [dist_dir] + ([] if lang == "en" else [lang]) + ["city", country]
    return os.path.join(*parts), f"{_city_slug(city_name)}.html"


def _city_jsonld(city, place_label, canonical_url, city_rides):
    """Place + Review structured data for one city page.

    Built here, not in the template, same reasoning as route_pages.py's
    jsonld_steps: this is the copy a parser (or an assistant summarising the
    page) lifts directly, so it should be exact and it's awkward to assemble
    with conditionals in Jinja. Only real logged content goes in -- no rating
    field exists in ride_event, so no AggregateRating is emitted.
    """
    reviews = []
    for row in city_rides.itertuples():
        # pd.read_sql leaves a NULL comment as NaN (a float), not None -- `or ""`
        # alone doesn't catch it, since bool(nan) is True and .strip() then throws.
        comment = "" if pd.isna(row.comment) else str(row.comment).strip()
        if not comment:
            continue
        reviews.append(
            {
                "@type": "Review",
                "reviewBody": comment[:500],
                "author": {"@type": "Person", "name": row.hitchhiker_name or "Anonymous"},
                "datePublished": (row.submission_time or "")[:10],
            }
        )
    data = {
        "@context": "https://schema.org",
        "@type": "Place",
        "name": place_label,
        "url": canonical_url,
        "geo": {"@type": "GeoCoordinates", "latitude": float(city.lat), "longitude": float(city.lng)},
    }
    if reviews:
        data["review"] = reviews
    return data


# Load template environment.
#
# These pages extend the site's base.html, which is written for Flask's own Jinja
# environment and so reaches for globals a bare Environment doesn't have. `request`
# is already guarded with `is defined` in the template (it genuinely doesn't exist
# during static generation), but `{{ g.lang }}` and `t()` are not — and an
# UndefinedError there aborts the render of *every* page. That is exactly what
# happened when the i18n work landed: this script died on `'g' is undefined`, which
# stopped city pages regenerating AND stopped sitemap.xml/robots.txt being rewritten,
# since both are produced at the end of this run.
#
# Passing Flask's real `g` (rather than a stand-in) is what makes per-language
# rendering work: translations.current_lang() reads g.lang, so setting it once per
# language makes every t() in the templates resolve to that language.
env = Environment(loader=FileSystemLoader("hitch/templates"))
env.globals["t"] = t
env.globals["g"] = g
env.globals["SUPPORTED_LANGUAGES"] = SUPPORTED_LANGUAGES
city_template = env.get_template("city_template.html")
city_index = env.get_template("city_index.html")

# Load rides directly from the ride_event table (rides.json may not exist yet on a
# fresh install; the DB is the canonical source — see CLAUDE.md "Database Storage").
logger.info("Loading rides from ride_event table")
rides = pd.read_sql("select stops, comment, hitchhikers, submission_time from ride_event", get_db())
rides["stops"] = rides["stops"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
rides["hitchhikers"] = rides["hitchhikers"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)


def _hitchhiker_name(hitchhikers):
    if isinstance(hitchhikers, list) and hitchhikers:
        first = hitchhikers[0]
        if isinstance(first, dict) and isinstance(first.get("nickname"), str) and first["nickname"].strip() != "":
            return first["nickname"]
    return "Anonymous"


rides["hitchhiker_name"] = rides["hitchhikers"].apply(_hitchhiker_name)


def _coords(row):
    stops = row["stops"] or []
    if not stops:
        return pd.Series({"lat": None, "lon": None, "dest_lat": None, "dest_lon": None})
    start = stops[0]["location"]
    if len(stops) > 1:
        end = stops[-1]["location"]
        return pd.Series(
            {"lat": start["latitude"], "lon": start["longitude"], "dest_lat": end["latitude"], "dest_lon": end["longitude"]}
        )
    return pd.Series({"lat": start["latitude"], "lon": start["longitude"], "dest_lat": None, "dest_lon": None})


rides[["lat", "lon", "dest_lat", "dest_lon"]] = rides.apply(_coords, axis=1)


def _ride_datetime(stops):
    if isinstance(stops, list) and stops:
        first = stops[0]
        if isinstance(first, dict):
            return first.get("departure_time")
    return None


rides["ride_datetime"] = pd.to_datetime(rides["stops"].apply(_ride_datetime), errors="coerce", utc=True)

# Build the HTML "text" the city template renders for each review.
rides["hitchhiker_name"] = rides["hitchhiker_name"].fillna("Anonymous")
rides["text"] = (
    rides["comment"].fillna("").map(html.escape).str.replace("\n", "<br>") + "<br>―" + rides["hitchhiker_name"].map(html.escape)
)
rides = rides.dropna(subset=["lat", "lon"])
logger.info(f"Loaded {len(rides)} rides")

cities_csv_path = os.path.join(dist_dir, "worldcities.csv")
if not os.path.exists(cities_csv_path):
    zip_path = os.path.join(dist_dir, "worldcities.zip")

    logger.info("Extracting worldcities.csv...")
    # Unzip and extract worldcities.csv
    with zipfile.ZipFile(zip_path) as z, z.open("worldcities.csv") as f:
        cities_df = pd.read_csv(f)

    # Filter for major cities (population > 50000)
    major_cities = cities_df[cities_df["population"] > 50000]
    logger.info(f"Found {len(major_cities)} major cities with population > 50,000")

    # Save to dist/worldcities.csv
    major_cities.to_csv(cities_csv_path, index=False)
    logger.info(f"Saved cities data to {cities_csv_path}")

# Sort rides by datetime (most recent first)
rides.sort_values("ride_datetime", inplace=True, ascending=False)

# Load cities data
cities = pd.read_csv(cities_csv_path).drop_duplicates().sort_values("city")
rendered_cities = []

logger.info(f"Processing {len(cities)} cities")

# Radius in km: rides within this distance of a city center are associated with that city.
# Scaled by population so larger cities cast a wider net (up to 50km for megacities).
CITY_RADIUS_BASE_KM = 20
CITY_RADIUS_MAX_KM = 50

# Precompute ride coordinates in radians for vectorized haversine
ride_lats = np.radians(rides["lat"].values.astype(float))
ride_lons = np.radians(rides["lon"].values.astype(float))
has_dest = rides["dest_lat"].notna() & rides["dest_lon"].notna()
dest_lats = np.where(has_dest, np.radians(rides["dest_lat"].fillna(0).values.astype(float)), np.nan)
dest_lons = np.where(has_dest, np.radians(rides["dest_lon"].fillna(0).values.astype(float)), np.nan)


def haversine_km(lat1, lon1, lat2, lon2):
    """Vectorized haversine distance in km between a single point and arrays of points."""
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


total_cities = len(cities)
# Log progress every ~10% so cron logs show forward motion without spamming a line per city
log_every = max(1, total_cities // 10)

# Pass 1: match rides to cities. Nothing is written yet, because which languages a
# city gets depends on how it ranks against every other city — unknowable mid-loop.
# Only the matched ride *indices* are kept (<=20 ints each); holding 14.5k
# DataFrames instead would cost hundreds of MB for data we can re-slice for free.
matched = []  # (city namedtuple, ride index array, total matching rides)
for i, city in enumerate(cities.itertuples(), start=1):
    if i % log_every == 0 or i == total_cities:
        logger.info(f"Matching rides to cities: {i}/{total_cities} ({i * 100 // total_cities}%)")

    # Scale radius by population: log10(50k)≈4.7, log10(10M)≈7 → range ~4.7-7
    pop = city.population if pd.notna(city.population) and city.population > 0 else 50000
    radius_km = min(CITY_RADIUS_BASE_KM * (np.log10(pop) / np.log10(50000)), CITY_RADIUS_MAX_KM)

    city_lat = np.radians(city.lat)
    city_lon = np.radians(city.lng)

    # Check pickup location proximity
    pickup_dist = haversine_km(city_lat, city_lon, ride_lats, ride_lons)
    near_pickup = pickup_dist <= radius_km

    # Check destination proximity (only for rides that have a destination)
    near_dest = np.zeros(len(rides), dtype=bool)
    if has_dest.any():
        dest_dist = haversine_km(city_lat, city_lon, dest_lats, dest_lons)
        near_dest = has_dest.values & (dest_dist <= radius_km)

    hits = near_pickup | near_dest
    # Rank on the UNCAPPED count: the page shows at most 20 reviews, so capping
    # first would tie thousands of cities at 20 and make the ranking meaningless.
    matched.append((city, rides.index[hits][:20], int(hits.sum())))

rendered_cities = [total >= 3 for _, _, total in matched]
# The cities that earn every language: best-evidenced first. Keyed by position in
# `matched` rather than by the row object, since pandas hands out a fresh namedtuple
# per iteration and identity comparisons on those are a trap.
renderable = [pos for pos, keep in enumerate(rendered_cities) if keep]
translated_positions = set(sorted(renderable, key=lambda pos: -matched[pos][2])[:TOP_N_TRANSLATED])
logger.info(
    f"{len(renderable)} cities have enough rides to render; "
    f"top {len(translated_positions)} also get all {len(SUPPORTED_LANGUAGES)} languages"
)

# Hand the ranking to route_pages.py. Matching rides to 48k cities is the slow part
# of this script (~25 min); the route generator needs exactly the same ranking to
# choose which city pairs deserve a page, so it reads this instead of recomputing it.
top_cities = [
    {
        "city": matched[pos][0].city,
        "country": matched[pos][0].country,
        "lat": float(matched[pos][0].lat),
        "lon": float(matched[pos][0].lng),
        "rides": matched[pos][2],
        # Population stands in for search demand: route_pages.py uses it to pick
        # which city represents a metro area, so "Paris" wins over "Meudon".
        "population": int(matched[pos][0].population) if pd.notna(matched[pos][0].population) else 0,
        "url": _city_loc(matched[pos][0].country, matched[pos][0].city),
    }
    for pos in sorted(renderable, key=lambda pos: -matched[pos][2])[:TOP_N_TRANSLATED]
]
os.makedirs(os.path.join(dist_dir, "city"), exist_ok=True)
with open(os.path.join(dist_dir, "city", "top_cities.json"), "w", encoding="utf-8") as f:
    json.dump(top_cities, f)
logger.info(f"Wrote top_cities.json ({len(top_cities)} cities) for route page generation")

translated_locs = []  # sitemap entries for the non-English versions
for pos in renderable:
    city, ride_idx, _total = matched[pos]
    city_rides = rides.loc[ride_idx]
    langs = SUPPORTED_LANGUAGES if pos in translated_positions else ("en",)
    # Every version points at every other (and at the English x-default) so the
    # set reads as one page in 31 languages rather than 31 competing pages.
    alternates = [(code, _city_loc(city.country, city.city, code)) for code in langs] if len(langs) > 1 else []

    for lang in langs:
        g.lang = lang  # translations.current_lang() reads this; drives every t()
        folder, filename = _city_path(city.country, city.city, lang)
        os.makedirs(folder, exist_ok=True)
        canonical = _city_loc(city.country, city.city, lang)
        place_label = f"{city.city}, {city.country}" if city.country else city.city
        with open(os.path.join(folder, filename), "w") as f:
            f.write(
                city_template.render(
                    city=city,
                    title=city.city,
                    reviews=city_rides,
                    canonical_url=canonical,
                    alternate_urls=alternates,
                    city_jsonld=_city_jsonld(city, place_label, canonical, city_rides),
                )
            )
        if lang != "en":
            translated_locs.append(canonical)
    g.lang = "en"  # leave the index/sitemap rendering below in English

logger.info(
    f"Rendered {sum(rendered_cities)} English city pages out of {len(cities)} cities, "
    f"plus {len(translated_locs)} translated versions"
)

# Create the city index, once per language. A translated city page's nav links to
# /<lang>/city/index.html, so without this every one of them would 404.
#
# The English index lists every rendered city; a translated index lists only the
# cities that actually have a page in that language (TOP_N_TRANSLATED), because
# linking /de/city/<Country>/<SmallTown>.html when only the English version exists
# would point a whole index full of links at 404s.
translated_mask = [pos in translated_positions for pos in range(len(matched))]
index_locs = []
for lang in SUPPORTED_LANGUAGES:
    g.lang = lang
    listed = cities[rendered_cities if lang == "en" else translated_mask]
    folder = os.path.join(*([dist_dir] + ([] if lang == "en" else [lang]) + ["city"]))
    os.makedirs(folder, exist_ok=True)
    prefix = "" if lang == "en" else f"/{lang}"
    canonical = f"{SITE_URL}{prefix}/city/index.html"
    with open(os.path.join(folder, "index.html"), "w") as f:
        f.write(
            city_index.render(
                grouped_cities=listed.groupby("country"),
                canonical_url=canonical,
                alternate_urls=[
                    (code, f"{SITE_URL}{'' if code == 'en' else '/' + code}/city/index.html") for code in SUPPORTED_LANGUAGES
                ],
            )
        )
    if lang != "en":
        index_locs.append(canonical)
g.lang = "en"
logger.info(f"Wrote {len(SUPPORTED_LANGUAGES)} city index pages ({len(index_locs)} translated)")

# Generate sitemap.xml + robots.txt so search engines can discover the per-city
# SEO pages (the rest of the site is the SPA map / JSON data, not worth indexing).
# Built here because this is the only place that knows which cities actually got a
# page (the rendered_cities mask) — pointing the sitemap at unrendered cities 404s.
lastmod = date.today().isoformat()


def _sitemap_url(loc, priority):
    # loc is already absolute; XML-escape it (& -> &amp; etc.) for valid XML.
    return (
        f"  <url>\n"
        f"    <loc>{html.escape(loc)}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <priority>{priority}</priority>\n"
        f"  </url>\n"
    )


# Static, server-rendered pages reachable from the map's menu / action buttons.
# These are real distinct URLs (own HTML), so listing them helps crawlers find
# pages the JS-driven UI would otherwise hide behind buttons.
# NOTE on what is deliberately NOT here:
#   - Route planning is "/#routing" — a hash fragment. Crawlers strip everything
#     after "#", so it is the same URL as "/" and cannot be a separate entry.
#   - "?heatmap=true" is a query-param view of "/" whose server HTML is identical
#     to "/" (the heatmap is drawn client-side). We still list it so the heatmap
#     view is explicitly advertised, but it intentionally shares "/"'s content.
def _country_locs():
    """Sitemap URLs for /country/<name>, one per country we can actually describe.

    Only countries with waiting-time stats are listed: main.render_country emits
    a description (and therefore stays indexable) exactly when country_insights
    has them, so listing the rest would point the sitemap at noindex pages — the
    same mistake as pointing it at cities that never got rendered.

    The country view used to be reachable only as "#country/<name>". Crawlers drop
    everything after "#", so all ~90 countries were the single URL "/" and none of
    them could be listed here at all.
    """
    geo_path = os.path.join(dirs["base"], "static", "countries.geojson")
    insights_path = os.path.join(dist_dir, "country_insights.json")
    try:
        with open(geo_path) as f:
            features = json.load(f).get("features", [])
        with open(insights_path) as f:
            insights = json.load(f)
    except (OSError, ValueError):
        logger.warning("No country insights/geojson — skipping country URLs in sitemap")
        return []

    locs = []
    for feature in features:
        props = feature.get("properties") or {}
        stats = ((insights.get(props.get("cc")) or {}).get("wait") or {}).get("stats") or {}
        if stats.get("n"):
            locs.append(f"{SITE_URL}/country/{urllib.parse.quote(props['name'])}")
    return sorted(locs)


STATIC_PAGES = [
    (f"{SITE_URL}/", "1.0"),
    (f"{SITE_URL}/?heatmap=true", "0.6"),
    (f"{SITE_URL}/help", "0.7"),
    (f"{SITE_URL}/recent", "0.6"),
    (f"{SITE_URL}/leaderboard", "0.6"),
    (f"{SITE_URL}/races", "0.6"),
    (f"{SITE_URL}/statistics", "0.5"),
    (f"{SITE_URL}/statistics/waiting-times", "0.5"),
    (f"{SITE_URL}/statistics/ride-collection", "0.5"),
    (f"{SITE_URL}/city/index.html", "0.5"),
]

sitemap_parts = [
    '<?xml version="1.0" encoding="UTF-8"?>\n',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n',
]
for loc, priority in STATIC_PAGES:
    sitemap_parts.append(_sitemap_url(loc, priority))
country_locs = _country_locs()
# Above the per-city priority: a country page aggregates every city in it, and
# "hitchhiking in <country>" is the broader query we can realistically rank for.
for loc in country_locs:
    sitemap_parts.append(_sitemap_url(loc, "0.8"))
for city in cities[rendered_cities].itertuples():
    sitemap_parts.append(_sitemap_url(_city_loc(city.country, city.city), "0.7"))
# Translated versions sit just below their English original: same content, but the
# English page is the one we nominate as x-default in the hreflang set above.
for loc in translated_locs:
    sitemap_parts.append(_sitemap_url(loc, "0.6"))
for loc in index_locs:
    sitemap_parts.append(_sitemap_url(loc, "0.5"))
# Route pages (route_pages.py, which runs just before this job). Read from its
# manifest rather than globbed off disk, so a half-finished run can't put URLs in
# the sitemap. Absent on a fresh install or if that job failed — skipped quietly,
# exactly like the country URLs above.
route_locs = []
try:
    with open(os.path.join(dist_dir, "route", "index.json"), encoding="utf-8") as f:
        route_locs = json.load(f)
except (OSError, ValueError):
    logger.warning("No dist/route/index.json — skipping route URLs in sitemap")
# Highest per-page priority we assign: a "hitchhiking from X to Y" page answers a
# more specific question than a city page and is the harder query to rank for.
for loc in route_locs:
    sitemap_parts.append(_sitemap_url(loc, "0.8"))
sitemap_parts.append("</urlset>\n")

with open(os.path.join(dist_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
    f.write("".join(sitemap_parts))
_sitemap_total = (
    sum(rendered_cities) + len(STATIC_PAGES) + len(country_locs) + len(translated_locs) + len(index_locs) + len(route_locs)
)
logger.info(
    f"Wrote sitemap.xml with {_sitemap_total} URLs "
    f"({len(country_locs)} countries, {len(translated_locs)} translated city pages, "
    f"{len(index_locs)} translated indexes, {len(route_locs)} route pages)"
)

# Open access so search engines and AI crawlers can discover the city pages.
# Discovery is opt-in by NOT disallowing, so AI training/search bots (GPTBot,
# ClaudeBot, Google-Extended, Applebot-Extended, CCBot, PerplexityBot, …) are
# all permitted. Crawl-delay gentles polite crawlers (Bing/Yandex/some AI bots;
# Googlebot ignores it) — it is NOT overload protection, which belongs in Caddy.
robots_txt = (
    "# We welcome search engines and AI crawlers — access is open so our city\n"
    "# pages can be discovered and indexed.\n"
    "User-agent: *\n"
    "Allow: /\n"
    "Crawl-delay: 5\n"
    "\n"
    f"Sitemap: {SITE_URL}/sitemap.xml\n"
)
with open(os.path.join(dist_dir, "robots.txt"), "w", encoding="utf-8") as f:
    f.write(robots_txt)

logger.info("CITIES SCRIPT FINISHED")
