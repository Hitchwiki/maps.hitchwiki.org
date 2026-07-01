"""Obtain hitchwiki.org country ratings.

Computes the average hitchhiking-ride rating per country and writes it to a CSV.

This is a standalone, manually-triggered script (NOT wired into cron or
`flask generate`). Run it by hand whenever fresh country ratings are needed:

    python hitch/scripts/country_ratings.py

Each ride's country is derived from its start coordinate (stops[0].location)
via offline reverse geocoding (the `reverse_geocoder` package — no API calls,
no network). Output is written to dist/country_ratings.csv, sorted by average
rating (descending).
"""

import csv
import json
import os
import sqlite3
from collections import defaultdict

import reverse_geocoder as rg

# Resolve the DB path the same way hitch/settings.py does: db/{DATABASE_NAME}.
# Defaults to the production DB name so a manual run on the server just works.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATABASE_NAME = os.getenv("DATABASE_NAME", "prod-points.sqlite")
DATABASE_URI = os.getenv("DATABASE_URI", os.path.join(BASE_DIR, "db", DATABASE_NAME))

DIST_DIR = os.path.join(BASE_DIR, "dist")
OUTPUT_CSV = os.path.join(DIST_DIR, "country_ratings.csv")


def main():
    conn = sqlite3.connect(DATABASE_URI)
    rows = conn.execute("SELECT stops, rating FROM ride_event WHERE rating IS NOT NULL").fetchall()
    conn.close()

    coords = []
    ratings = []
    for stops, rating in rows:
        stops = json.loads(stops) if isinstance(stops, str) else stops
        # Skip rides we can't place (missing/malformed start location).
        try:
            loc = stops[0]["location"]
            coords.append((loc["latitude"], loc["longitude"]))
        except (TypeError, KeyError, IndexError):
            continue
        ratings.append(rating)

    # Single batched, offline reverse-geocode of every start coordinate.
    results = rg.search(coords)

    sums = defaultdict(float)
    counts = defaultdict(int)
    for res, rating in zip(results, ratings):
        cc = res["cc"]
        sums[cc] += rating
        counts[cc] += 1

    country_rows = [
        (cc, round(sums[cc] / counts[cc]), counts[cc]) for cc in sums
    ]
    # Sort by average rating (desc), then by number of rides (desc) as tiebreak.
    country_rows.sort(key=lambda r: (r[1], r[2]), reverse=True)

    os.makedirs(DIST_DIR, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["country_code", "average_rating", "ride_count"])
        writer.writerows(country_rows)

    print(f"Wrote {len(country_rows)} countries ({sum(counts.values())} rides) to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
