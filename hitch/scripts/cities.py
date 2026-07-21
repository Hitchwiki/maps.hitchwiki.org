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
from jinja2 import Environment, FileSystemLoader

from hitch.helpers import get_db, get_dirs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dirs = get_dirs()
dist_dir = dirs["dist"]

# Canonical site origin + per-city URL builder. Defined here (before the render
# loop) so each city page can embed a self-referencing canonical that matches,
# byte for byte, the sitemap entry built later.
SITE_URL = "https://maps.hitchwiki.org"


def _city_loc(country, city_name):
    # Match the on-disk filename (cities.py replaces "/" with "-"), then
    # percent-encode each path segment so spaces/diacritics produce valid URLs.
    safe_filename = city_name.replace("/", "-")
    country_seg = urllib.parse.quote(country)
    city_seg = urllib.parse.quote(f"{safe_filename}.html")
    return f"{SITE_URL}/city/{country_seg}/{city_seg}"


# Load template environment
env = Environment(loader=FileSystemLoader("hitch/templates"))
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
for i, city in enumerate(cities.itertuples(), start=1):
    if i % log_every == 0 or i == total_cities:
        logger.info(f"Rendering city pages: {i}/{total_cities} ({i * 100 // total_cities}%)")
    country_folder = os.path.join(dist_dir, "city", city.country)
    os.makedirs(country_folder, exist_ok=True)

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

    city_rides = rides[near_pickup | near_dest].iloc[:20]

    rendered_cities.append(len(city_rides) >= 3)
    if rendered_cities[-1]:
        # logger.info(f"Rendering city page for {city.city}, {city.country} ({len(city_rides)} rides)")
        rendered = city_template.render(
            city=city,
            title=city.city,
            reviews=city_rides,
            canonical_url=_city_loc(city.country, city.city),
        )
        # Replace "/" with "-" to avoid filesystem issues
        safe_filename = city.city.replace("/", "-")
        with open(os.path.join(country_folder, f"{safe_filename}.html"), "w") as f:
            f.write(rendered)

logger.info(f"Rendered {sum(rendered_cities)} city pages out of {len(cities)} cities")

# Create city index page
os.makedirs(os.path.join(dist_dir, "city"), exist_ok=True)
index_rendered = city_index.render(grouped_cities=cities[rendered_cities].groupby("country"))
with open(os.path.join(dist_dir, "city", "index.html"), "w") as f:
    f.write(index_rendered)

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
    (f"{SITE_URL}/recent", "0.6"),
    (f"{SITE_URL}/leaderboard", "0.6"),
    (f"{SITE_URL}/dashboard.html", "0.5"),
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
sitemap_parts.append("</urlset>\n")

with open(os.path.join(dist_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
    f.write("".join(sitemap_parts))
logger.info(
    f"Wrote sitemap.xml with {sum(rendered_cities) + len(STATIC_PAGES) + len(country_locs)} URLs ({len(country_locs)} countries)"
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
