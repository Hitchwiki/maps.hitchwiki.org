#!/usr/bin/env python3
"""Render a high-resolution world map with country borders and a 1 km circle
around every hitchhiking spot whose popup was opened (clicked) on the map.

Click data is extracted directly from the production Docker container's logs:
every spot popup click triggers a `GET /rides/by-spot/<lat>_<lon>.json`
request, and the filename encodes the spot's coordinates (see show.py:
generate_spot_id -> f"{lat:.4f}_{lon:.4f}"). The log line's timestamp is also
parsed so the image can be stamped with the period the stats cover.

Country borders are drawn from the Natural Earth 50m admin-0 dataset, which is
downloaded once and cached next to this script (gitignored).

Usage:
    ../.venv/bin/python generate_clicked_spots_map.py

Docker logs are ephemeral and rotate, so the time range reflects only the logs
currently retained by the container, not all-time history.
"""

import csv
import os
import re
import subprocess
import urllib.request
from collections import Counter
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # headless: write a file, no display needed
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CONTAINER = "hitchhiking-map"
CLICKS_CSV = os.path.join(HERE, "clicked_spots.csv")
GEOJSON_PATH = os.path.join(HERE, "ne_50m_admin_0_countries.geojson")
GEOJSON_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_50m_admin_0_countries.geojson"
)
OUTPUT_PNG = os.path.join(HERE, "clicked_spots_map.png")

# Matches the access-log timestamp and the clicked spot's coordinates in one go,
# e.g. ... [29/May/2026 22:44:12] "GET /rides/by-spot/30.8705_57.8576.json ...
CLICK_RE = re.compile(
    r"\[(\d{2}/[A-Za-z]{3}/\d{4} \d{2}:\d{2}:\d{2})\]"
    r'.*?GET /rides/by-spot/(-?[\d.]+)_(-?[\d.]+)\.json'
)
LOG_TIME_FMT = "%d/%b/%Y %H:%M:%S"

# 1 km expressed in degrees of latitude (constant); longitude is scaled by the
# cosine of the latitude further down because meridians converge at the poles.
KM_PER_DEG_LAT = 111.32
CIRCLE_RADIUS_KM = 1.0


def extract_clicks_from_docker_logs():
    """Read the container logs, returning (spots, time_min, time_max) where
    spots is a list of (lat, lon, click_count) and the times are datetimes of
    the first/last click seen (None if no clicks)."""
    try:
        logs = subprocess.run(
            ["docker", "logs", CONTAINER],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        # Fall back to whatever was cached on a previous run rather than crash.
        print(f"Could not read docker logs ({exc}); falling back to {CLICKS_CSV}")
        return _load_cached_clicks()

    output = (logs.stdout or "") + (logs.stderr or "")  # werkzeug logs to stderr
    counts = Counter()
    times = []
    for match in CLICK_RE.finditer(output):
        ts, lat, lon = match.groups()
        counts[(float(lat), float(lon))] += 1
        times.append(datetime.strptime(ts, LOG_TIME_FMT))

    spots = [(lat, lon, n) for (lat, lon), n in counts.most_common()]
    _write_cache(spots)
    time_min = min(times) if times else None
    time_max = max(times) if times else None
    return spots, time_min, time_max


def _write_cache(spots):
    with open(CLICKS_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["count", "lat", "lon"])
        for lat, lon, n in spots:
            writer.writerow([n, f"{lat:.4f}", f"{lon:.4f}"])


def _load_cached_clicks():
    spots = []
    with open(CLICKS_CSV, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            spots.append((float(row["lat"]), float(row["lon"]), int(row["count"])))
    return spots, None, None


def load_country_borders():
    """Download (once) and parse Natural Earth admin-0 country polygons."""
    if not os.path.exists(GEOJSON_PATH):
        print("Downloading Natural Earth country borders...")
        urllib.request.urlretrieve(GEOJSON_URL, GEOJSON_PATH)

    import json

    with open(GEOJSON_PATH, encoding="utf-8") as fh:
        data = json.load(fh)

    # Collect every exterior/interior ring as a sequence of (lon, lat) points so
    # they can be drawn as thin border lines without filling the land.
    rings = []
    for feature in data["features"]:
        geom = feature["geometry"]
        if geom is None:
            continue
        if geom["type"] == "Polygon":
            polygons = [geom["coordinates"]]
        elif geom["type"] == "MultiPolygon":
            polygons = geom["coordinates"]
        else:
            continue
        for polygon in polygons:
            for ring in polygon:
                rings.append(np.asarray(ring))
    return rings


def circle_polygon(lat, lon, radius_km, n=24):
    """Approximate a geodesic circle of `radius_km` around (lat, lon) as a
    small polygon in lon/lat space, correcting longitude for latitude."""
    dlat = radius_km / KM_PER_DEG_LAT
    # Guard against division blow-up very close to the poles.
    dlon = radius_km / (KM_PER_DEG_LAT * max(np.cos(np.radians(lat)), 1e-6))
    theta = np.linspace(0, 2 * np.pi, n)
    xs = lon + dlon * np.cos(theta)
    ys = lat + dlat * np.sin(theta)
    return np.column_stack([xs, ys])


def format_period(time_min, time_max):
    """Human-readable description of the time span the stats cover."""
    if time_min is None or time_max is None:
        return "time range unknown (loaded from cache)"
    fmt = "%d %b %Y %H:%M"
    return f"{time_min.strftime(fmt)} – {time_max.strftime(fmt)} (container log time)"


def main():
    rings = load_country_borders()
    spots, time_min, time_max = extract_clicks_from_docker_logs()
    print(f"Loaded {len(spots)} unique clicked spots, {len(rings)} border rings.")
    print(f"Period: {format_period(time_min, time_max)}")

    # High-resolution figure: 32x16 inches at 200 dpi -> 6400x3200 px.
    fig, ax = plt.subplots(figsize=(32, 16), dpi=200)
    ax.set_facecolor("#0b1d2a")
    fig.patch.set_facecolor("#0b1d2a")

    # Country borders as thin grey lines (drawn as a single collection for speed).
    ax.add_collection(LineCollection(rings, colors="#5a7184", linewidths=0.4, zorder=1))

    # A true 1 km circle is sub-pixel at world scale, so also drop a small marker
    # per spot for visibility; the circle patch is the literal requested geometry.
    lats = np.array([s[0] for s in spots])
    lons = np.array([s[1] for s in spots])
    counts = np.array([s[2] for s in spots])

    for lat, lon in zip(lats, lons):
        ax.add_patch(
            Polygon(
                circle_polygon(lat, lon, CIRCLE_RADIUS_KM),
                closed=True,
                facecolor="#ff5252",
                edgecolor="#ff5252",
                linewidth=0.3,
                alpha=0.9,
                zorder=3,
            )
        )

    # Marker size scales (sub-linearly) with how often the spot was clicked.
    ax.scatter(
        lons,
        lats,
        s=8 + 12 * np.sqrt(counts),
        facecolors="none",
        edgecolors="#ffd54f",
        linewidths=0.6,
        alpha=0.7,
        zorder=2,
    )

    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 84)  # crop Antarctica / keep populated latitudes
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    total_clicks = int(counts.sum())
    ax.set_title(
        f"Clicked hitchhiking spots — {len(spots)} unique spots, "
        f"{total_clicks} clicks (1 km circles)",
        color="#e0e0e0",
        fontsize=22,
        pad=20,
    )
    # Subtitle: which period these stats cover + when the image was rendered.
    generated = datetime.now().strftime("%d %b %Y %H:%M")
    ax.text(
        0.5,
        1.012,
        f"Stats from {format_period(time_min, time_max)}  ·  generated {generated}",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        color="#9fb3c2",
        fontsize=13,
    )

    fig.savefig(OUTPUT_PNG, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Wrote {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
