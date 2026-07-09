"""On Hitchwiki the {{Coords|...}} template is used to reference coordinates of hitchhiking spots."""

import json
import logging
import os
import re
import urllib.parse

import pandas as pd
from tqdm import tqdm

from hitch.extensions import db
from hitch.helpers import get_dirs
from hitch.models import HitchwikiArticleLocation, HitchwikiArticleMap

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)


def heading_to_fragment(heading, num_same_heading_above: int):
    # 1. Trim whitespace
    heading = heading.strip()
    # 2. Remove wiki markup (e.g., '', ''', etc.)
    heading = re.sub(r"''+", "", heading)
    # 3. Normalize spaces to single underscores
    heading = re.sub(r"\s+", "_", heading)
    # Remove [ and ] characters
    heading = heading.replace("[", "").replace("]", "")
    # 4. Capitalize the first character
    if heading:
        heading = heading[0].upper() + heading[1:]
    # 5. Percent-encode non-ASCII or special characters
    # fragment = urllib.parse.quote(heading, safe='_')
    if num_same_heading_above > 0:
        heading += f"_{num_same_heading_above + 1}"
    return heading


def extract_coords_and_headings(text):
    # Find all headings with their positions
    heading_pattern = re.compile(r"^(=+)\s*(.*?)\s*\1$", re.MULTILINE)
    headings = [(m.start(), m.group(2)) for m in heading_pattern.finditer(text)]

    # Find all {{Coords|...}} tags with their positions
    coords_pattern = re.compile(r"{{Coords\|[^}]+}}")
    coords = [(m.start(), m.group(0)) for m in coords_pattern.finditer(text)]

    results = []
    for coord_pos, coord_tag in coords:
        # Find the closest preceding heading
        heading = None
        same_heading_count = 0
        for h_pos, h_text in reversed(headings):
            if heading and h_text == heading:
                same_heading_count += 1

            if h_pos < coord_pos and heading is None:
                heading = h_text

        results.append(
            {
                "heading": heading,
                "coords": coord_tag,
                "same_heading_count": same_heading_count,
            }
        )
    return results


def extract_maps(text):
    """Extract map patterns from wiki text.
    
    Looks for patterns like: |map = <map lat='51.049' lng='13.74' zoom='11'.../>
    """
    map_pattern = re.compile(r"\|map\s*=\s*<map\s+lat='([^']+)'\s+lng='([^']+)'\s+zoom='([^']+)'")
    maps = [(m.start(), m.group(0), m.group(1), m.group(2), m.group(3)) for m in map_pattern.finditer(text)]
    
    return maps


def find_maps(raw_wiki_page: str, title: str, base_url: str = "https://hitchwiki.org/en/") -> list[dict]:
    """Extracts map coordinates and zoom levels from a raw wiki page text.

    Args:
        raw_wiki_page (str): The raw text of the wiki page.
        title (str): The title of the wiki page.
        base_url (str, optional): The base URL for constructing links. Defaults to "https://hitchwiki.org/en/".

    Returns:
        list[dict]: A list of dictionaries containing map data with lat, lng, zoom, and URL.
    """
    results = []
    maps = extract_maps(raw_wiki_page)
    
    for _, map_tag, lat, lng, zoom in maps:
        link = base_url + title
        
        results.append({
            "title": title,
            "lat": lat,
            "lng": lng, 
            "zoom": zoom,
            "link": link,
            "map_tag": map_tag
        })
    
    return results


def find_coords_and_headings(raw_wiki_page: str, title: str, base_url: str = "https://hitchwiki.org/en/") -> list[dict]:
    """Extracts coordinates and their associated headings from a raw wiki page text.

    Args:
        raw_wiki_page (str): The raw text of the wiki page.
        title (str): The title of the wiki page.
        base_url (str, optional): The base URL for constructing links. Defaults to "https://hitchwiki.org/en/".

    Returns:
        list[dict]: A list of dictionaries containing article paragraph headings and their associated coordinates.
    """
    results = []
    for item in extract_coords_and_headings(raw_wiki_page):
        if item["heading"]:
            fragment = heading_to_fragment(item["heading"], item["same_heading_count"])
            link = base_url + title + "#" + urllib.parse.quote(fragment)
        else:
            link = base_url + title

        item["link"] = link
        item["title"] = title
        results.append(item)

    return results


### MAIN SCRIPT ###

logger.info("Starting Hitchwiki synchronization script...")

# TODO: get articles with |map = <map lat='51.049' lng='13.74' zoom='11'/> in Infobox as well
articles_file = os.path.join(get_dirs()["dist"], "hitchwiki_articles.json")
logger.info(f"Articles file path: {articles_file}")
if os.path.exists(articles_file):
    logger.info(f"Loading existing articles from {articles_file}...")
    with open(articles_file, encoding="utf-8") as f:
        articles = json.load(f)
else:
    logger.info("Fetching articles from Hitchwiki via API...")
    articles = {}
    # Use MediaWiki API directly to avoid pywikibot's interwiki parsing
    # which throws SiteDefinitionError on pages with hitchwiki.org interwiki links
    import requests as http_requests

    api_url = "https://hitchwiki.org/en/api.php"
    # Hitchwiki sits behind Cloudflare, which serves a 403 "Just a moment..." bot
    # challenge to requests without a browser-like User-Agent. Send one so the API
    # calls get through (a descriptive contact is also MediaWiki API etiquette).
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36 maps.hitchwiki.org-articles-sync"
        )
    }
    # Step 1: List all pages via allpages generator + get their content in one go
    ap_continue = None
    total_pages = 0
    while True:
        params = {
            "action": "query",
            "generator": "allpages",
            "gaplimit": "50",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "format": "json",
        }
        if ap_continue:
            params["gapcontinue"] = ap_continue
        try:
            for attempt in range(5):
                resp = http_requests.get(api_url, params=params, headers=headers, timeout=30)
                if resp.status_code == 429:
                    import time
                    wait = 2 ** attempt
                    logger.warning(f"Rate limited (429), waiting {wait}s...")
                    time.sleep(wait)
                    continue
                break
            if resp.status_code != 200:
                logger.warning(f"API returned HTTP {resp.status_code}: {resp.text[:500]}")
                break
            data = resp.json()
        except Exception as e:
            logger.warning(f"API request failed: {e}")
            break

        pages_data = data.get("query", {}).get("pages", {})
        for page_data in pages_data.values():
            total_pages += 1
            title = page_data.get("title", "")
            revisions = page_data.get("revisions")
            if not revisions:
                continue
            text = revisions[0].get("slots", {}).get("main", {}).get("*", "")
            if "{{Coords" in text:
                articles[title] = {"text": text}

        if total_pages % 500 == 0:
            logger.info(f"Scanned {total_pages} pages, found {len(articles)} with coords so far...")
            with open(articles_file, "w", encoding="utf-8") as f:
                json.dump(articles, f, ensure_ascii=False, indent=4)

        cont = data.get("continue")
        if cont and "gapcontinue" in cont:
            ap_continue = cont["gapcontinue"]
        else:
            break

    logger.info(f"Scanned {total_pages} pages total, found {len(articles)} with {{{{Coords}}}}")

    # Only save if we actually found articles (don't overwrite good cache with empty results)
    if articles:
        logger.info(f"Saving final results to {articles_file}...")
        with open(articles_file, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=4)
    else:
        logger.warning("No articles fetched — skipping save to preserve any existing cache")

logger.info(f"Processing {len(articles)} articles to extract coordinates and headings...")
coords = []
maps = []
for title, meta in tqdm(articles.items()):
    coords_results = find_coords_and_headings(raw_wiki_page=meta["text"], title=title)
    maps_results = find_maps(raw_wiki_page=meta["text"], title=title)

    coords.extend(coords_results)
    maps.extend(maps_results)


coords_df = pd.DataFrame(coords)

coords_df["lat"] = coords_df["coords"].apply(lambda x: x.split("|")[1].strip())
coords_df["lon"] = coords_df["coords"].apply(lambda x: x.split("|")[2].strip().rstrip("}"))

# TODO: get real spot aggregated from RideEvents
# spots = db.session.query(RideEvent).all()
# tree = cKDTree(spots[["lat", "lon"]].values)

# distances, indices = tree.query(coords_df[["lat", "lon"]].values)

# # Add nearest node info to spots DataFrame
# coords_df["nearest_node_id"] = spots.iloc[indices]["id"].values
# coords_df["nearest_node_lat"] = spots.iloc[indices]["lat"].values
# coords_df["nearest_node_lon"] = spots.iloc[indices]["lon"].values
# coords_df["distance"] = distances

# coords_df["haversine_distance_in_m"] = coords_df.apply(
#     lambda row: haversine_np(row["lat"], row["lon"], row["nearest_node_lat"], row["nearest_node_lon"]) * 1000, axis=1
# )

# coords_df = coords_df.sort_values(by="haversine_distance_in_m")

logger.info("Saving extracted coordinates and headings into the database...")
# Remove all existing HitchwikiArticleLocation entries for a fresh start
db.session.query(HitchwikiArticleLocation).delete()
db.session.commit()

# Filter out rows with non-numeric latitude or longitude
valid_coords_df = coords_df[
    pd.to_numeric(coords_df["lat"], errors="coerce").notnull() & pd.to_numeric(coords_df["lon"], errors="coerce").notnull()
]

for _, row in valid_coords_df.iterrows():
    location = HitchwikiArticleLocation(
        title=row["title"],
        heading=row["heading"],
        latitude=float(row["lat"]),
        longitude=float(row["lon"]),
        hitchwiki_url=row["link"],
    )
    db.session.add(location)
db.session.commit()

logger.info(f"Saved {len(coords_df)} Hitchwiki article locations into the database.")

# Process and save maps
logger.info("Saving extracted map data into the database...")
# Remove all existing HitchwikiArticleMap entries for a fresh start
db.session.query(HitchwikiArticleMap).delete()
db.session.commit()

maps_df = pd.DataFrame(maps)

# Filter out rows with non-numeric latitude or longitude
valid_maps_df = maps_df[
    pd.to_numeric(maps_df["lat"], errors="coerce").notnull() & 
    pd.to_numeric(maps_df["lng"], errors="coerce").notnull() &
    pd.to_numeric(maps_df["zoom"], errors="coerce").notnull()
]

for _, row in valid_maps_df.iterrows():
    map_entry = HitchwikiArticleMap(
        title=row["title"],
        latitude=float(row["lat"]),
        longitude=float(row["lng"]),
        zoom=int(row["zoom"]),
        hitchwiki_url=row["link"],
    )
    db.session.add(map_entry)
db.session.commit()

logger.info(f"Saved {len(valid_maps_df)} Hitchwiki article maps into the database.")
logger.info("SYNC HITCHWIKI SCRIPT FINISHED")
