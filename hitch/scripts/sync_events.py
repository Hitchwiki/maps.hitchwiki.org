"""Sync hitchhiking-related events from Hitchwiki into dist/events.json.

Every page in Hitchwiki's `Category:Event` may embed one or more event markers of
the form:

    {{Event|<name>|<start-date>|<end-date>|<latitude>|<longitude>}}

e.g. {{Event|Autostop House open to all in Albania|2026-07-01|2026-08-30|42.0681371|19.5121437}}

We pull every page in that category, extract each {{Event|...}} template, keep only
the events whose end date is still in the future (today included), and write them to
`dist/events.json`. The map frontend loads that file and draws a special event marker
at each location; clicking it opens a bottom sheet with the event name, dates, a short
description pulled from the wiki page, and a link back to Hitchwiki.

This writes the served JSON directly (like country_ratings) rather than going through
the database, because events are self-contained — they don't need to be joined with
rides / OSM / spots the way HitchwikiArticleLocation does.
"""

import datetime
import json
import logging
import os
import re
import time

import requests

from hitch.helpers import get_dirs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

API_URL = "https://hitchwiki.org/en/api.php"
BASE_URL = "https://hitchwiki.org/en/"
CATEGORY = "Category:Events"

# Hitchwiki sits behind Cloudflare, which serves a 403 "Just a moment..." bot
# challenge to requests without a browser-like User-Agent. Send one so the API
# calls get through (a descriptive contact is also MediaWiki API etiquette).
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36 maps.hitchwiki.org-events-sync"
    )
}

# {{Event|name|start|end|lat|lon}} — five pipe-separated fields. Fields are captured
# non-greedily up to the next pipe / closing braces so a name can contain spaces and
# punctuation (but not a literal pipe, which is the field separator in wikitext).
EVENT_PATTERN = re.compile(
    r"\{\{\s*Event\s*\|"
    r"\s*([^|]+?)\s*\|"  # name
    r"\s*([^|]+?)\s*\|"  # start date
    r"\s*([^|]+?)\s*\|"  # end date
    r"\s*([^|]+?)\s*\|"  # latitude
    r"\s*([^|}]+?)\s*"  # longitude (no trailing pipe)
    r"\}\}",
    re.IGNORECASE,
)


def api_get(params: dict) -> dict | None:
    """GET the MediaWiki API with basic 429 backoff, returning parsed JSON or None."""
    params = {**params, "format": "json"}
    for attempt in range(5):
        try:
            resp = requests.get(API_URL, params=params, timeout=30, headers=HEADERS)
        except Exception as e:
            logger.warning(f"API request failed: {e}")
            return None
        if resp.status_code == 429:
            wait = 2**attempt
            logger.warning(f"Rate limited (429), waiting {wait}s...")
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            logger.warning(f"API returned HTTP {resp.status_code}: {resp.text[:300]}")
            return None
        return resp.json()
    return None


def get_category_members() -> list[str]:
    """Return the titles of every page in Category:Event."""
    titles: list[str] = []
    cm_continue = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": CATEGORY,
            "cmlimit": "500",
            "cmtype": "page",
        }
        if cm_continue:
            params["cmcontinue"] = cm_continue
        data = api_get(params)
        if not data:
            break
        members = data.get("query", {}).get("categorymembers", [])
        titles.extend(m["title"] for m in members)
        cont = data.get("continue")
        if cont and "cmcontinue" in cont:
            cm_continue = cont["cmcontinue"]
        else:
            break
    return titles


def get_pages_wikitext(titles: list[str]) -> dict[str, str]:
    """Fetch the raw wikitext of each title. Requests are batched (50 titles/call)."""
    result: dict[str, str] = {}
    for i in range(0, len(titles), 50):
        batch = titles[i : i + 50]
        data = api_get(
            {
                "action": "query",
                "titles": "|".join(batch),
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
            }
        )
        if not data:
            continue
        for page in data.get("query", {}).get("pages", {}).values():
            revisions = page.get("revisions")
            if not revisions:
                continue
            text = revisions[0].get("slots", {}).get("main", {}).get("*", "")
            result[page.get("title", "")] = text
    return result


def parse_date(value: str) -> datetime.date | None:
    """Parse a YYYY-MM-DD (or YYYY/MM/DD) date string, tolerating extra whitespace."""
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def substitute_page_name(text: str, title: str) -> str:
    """Resolve the page-name magic words MediaWiki expands server-side.

    {{FULLPAGENAME}} / {{PAGENAME}} / {{BASEPAGENAME}} / {{SUBPAGENAME}} stay literal in
    raw wikitext and would otherwise be dropped by the template stripper below, so
    replace them with the actual page title (the "E" suffixes are URL-encoded variants).
    """
    base = title.rsplit("/", 1)[0] if "/" in title else title
    sub = title.rsplit("/", 1)[1] if "/" in title else title
    text = re.sub(r"\{\{\s*(?:FULLPAGENAME|PAGENAME)E?\s*\}\}", title, text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{\s*BASEPAGENAMEE?\s*\}\}", base, text, flags=re.IGNORECASE)
    text = re.sub(r"\{\{\s*SUBPAGENAMEE?\s*\}\}", sub, text, flags=re.IGNORECASE)
    return text


def wikitext_to_description(text: str, title: str, max_len: int = 600) -> str:
    """Turn a page's wikitext into a short plain-text blurb for the event sheet.

    This is deliberately light-touch — strip the templates and the noisiest markup so
    the sheet shows readable prose, and let the "read on Hitchwiki" link cover the rest.
    """
    text = substitute_page_name(text, title)
    # Drop all templates (including the {{Event|...}} markers and infoboxes).
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    # Category / file / image links.
    text = re.sub(r"\[\[(?:Category|File|Image):[^\]]*\]\]", "", text, flags=re.IGNORECASE)
    # [[target|label]] -> label ; [[target]] -> target
    text = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
    # [http://url label] -> label ; bare [http://url] -> url
    text = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", text)
    text = re.sub(r"\[(https?://\S+)\]", r"\1", text)
    # Headings, bold/italic, and HTML comments.
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"^=+\s*(.*?)\s*=+$", r"\1", text, flags=re.MULTILINE)
    text = re.sub(r"'''?", "", text)
    text = re.sub(r"<[^>]+>", "", text)  # stray HTML tags
    # Collapse whitespace and blank lines.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*", "\n\n", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0].rstrip() + "…"
    return text


def main():
    logger.info("Starting Hitchwiki events synchronization...")
    today = datetime.date.today()

    titles = get_category_members()
    logger.info(f"Found {len(titles)} page(s) in {CATEGORY}")

    pages = get_pages_wikitext(titles)
    logger.info(f"Fetched wikitext for {len(pages)} page(s)")

    events = []
    skipped_past = 0
    for title, text in pages.items():
        # Resolve page-name magic words up front so both the {{Event|...}} name field and
        # the description show the page title instead of a literal {{FULLPAGENAME}}.
        text = substitute_page_name(text, title)
        description = wikitext_to_description(text, title)
        url = BASE_URL + title.replace(" ", "_")
        for match in EVENT_PATTERN.finditer(text):
            name, start_raw, end_raw, lat_raw, lon_raw = (g.strip() for g in match.groups())

            end_date = parse_date(end_raw)
            if end_date is None:
                logger.warning(f"Skipping event '{name}' on '{title}': unparseable end date '{end_raw}'")
                continue
            # Requirement: only surface events that haven't finished yet (today counts as ongoing).
            if end_date < today:
                skipped_past += 1
                continue

            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
            except ValueError:
                logger.warning(f"Skipping event '{name}' on '{title}': bad coordinates '{lat_raw}, {lon_raw}'")
                continue

            start_date = parse_date(start_raw)
            events.append(
                {
                    "name": name,
                    "start": start_date.isoformat() if start_date else start_raw,
                    "end": end_date.isoformat(),
                    "lat": lat,
                    "lon": lon,
                    "title": title,
                    "url": url,
                    "description": description,
                }
            )

    # Show soonest-ending events first.
    events.sort(key=lambda ev: ev["end"])

    dist_dir = get_dirs()["dist"]
    os.makedirs(dist_dir, exist_ok=True)
    out_path = os.path.join(dist_dir, "events.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

    logger.info(f"Wrote {len(events)} upcoming/ongoing event(s) to {out_path} (skipped {skipped_past} past event(s))")
    logger.info("SYNC EVENTS SCRIPT FINISHED")


main()
