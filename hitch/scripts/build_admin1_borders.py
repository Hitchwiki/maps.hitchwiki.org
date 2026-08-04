#!/usr/bin/env python3
"""Build `hitch/static/admin1_borders.geojson` — the internal first-level administrative
borders (US states, Russian federal subjects, Indian states, Chinese provinces, …) drawn
on top of the waiting-time heatmap so a large country can be read region by region.

Standalone one-off asset builder (plain `python3`, stdlib only, no app context). The output
is checked into git next to `countries.geojson`; re-run it only to refresh the source data.

Source: Natural Earth 1:50m admin-1 states/provinces (public domain), which only ships
first-level units for the handful of countries big enough for them to matter — exactly the
set this feature is for.

Two things the pipeline does on purpose:

* **Only edges shared by two units are kept.** A state polygon's outline is part internal
  border, part national border/coastline; the national part is already drawn from
  `countries.geojson`, and drawing it twice from a different Natural Earth scale would show
  as two lines a few pixels apart. An internal border belongs to exactly two units and so
  appears twice in the edge set, a coastline once — that count is the filter.
* **Edges are chained into long lines before simplification.** Simplifying each polygon on
  its own would move shared vertices differently for each neighbour and tear the borders
  apart; and one MultiLineString per country is far smaller than 294 closed rings.
"""

import argparse
import json
import math
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_1_states_provinces_lakes.geojson"
)

# Simplification tolerance in degrees. The heatmap image itself is 0.1°/px, so ~0.01°
# (~1 km) is already an order of magnitude finer than anything it can show.
TOLERANCE_DEG = 0.01
# Coordinate precision in the output. 4 decimals ≈ 11 m, well below the tolerance above.
PRECISION = 4
# Vertices are matched exactly, so round only far enough to absorb float noise.
KEY_PRECISION = 6


def iter_rings(geometry):
    """Every linear ring of a Polygon/MultiPolygon geometry."""
    if geometry["type"] == "Polygon":
        return list(geometry["coordinates"])
    if geometry["type"] == "MultiPolygon":
        return [ring for polygon in geometry["coordinates"] for ring in polygon]
    return []


def edge_key(a, b):
    """Undirected key for the segment a–b, so neighbours that traverse a shared border in
    opposite directions still land on the same entry."""
    ka = (round(a[0], KEY_PRECISION), round(a[1], KEY_PRECISION))
    kb = (round(b[0], KEY_PRECISION), round(b[1], KEY_PRECISION))
    return (ka, kb) if ka <= kb else (kb, ka)


def internal_edges(features):
    """The segments of `features` that two units share — i.e. the internal borders."""
    counts = Counter()
    for feature in features:
        for ring in iter_rings(feature["geometry"]):
            for a, b in zip(ring, ring[1:]):
                key = edge_key(a, b)
                if key[0] != key[1]:
                    counts[key] += 1
    return [key for key, count in counts.items() if count >= 2]


def chain_edges(edges):
    """Stitch undirected segments into the longest possible polylines.

    Walks from each unvisited endpoint, extending in both directions. Junctions (a point
    where three states meet) are broken arbitrarily — which line gets the shared vertex
    doesn't matter, every edge is drawn exactly once either way.
    """
    adjacency = defaultdict(list)
    for index, (a, b) in enumerate(edges):
        adjacency[a].append((b, index))
        adjacency[b].append((a, index))

    used = [False] * len(edges)
    lines = []

    def walk(start):
        """Follow unused edges from `start` for as long as there are any."""
        path = [start]
        node = start
        while True:
            nxt = next((n for n in adjacency[node] if not used[n[1]]), None)
            if nxt is None:
                return path
            neighbour, index = nxt
            used[index] = True
            path.append(neighbour)
            node = neighbour

    # Start at junctions/dead ends first (anything that isn't a plain 2-way vertex), so
    # closed loops don't get chopped in the middle of a run.
    starts = [node for node, links in adjacency.items() if len(links) != 2]
    starts += list(adjacency.keys())
    for start in starts:
        while any(not used[i] for _, i in adjacency[start]):
            forward = walk(start)
            backward = walk(start)
            line = list(reversed(backward[1:])) + forward
            if len(line) > 1:
                lines.append(line)
    return lines


def perpendicular_distance(point, start, end):
    (px, py), (x0, y0), (x1, y1) = point, start, end
    dx, dy = x1 - x0, y1 - y0
    if dx == 0 and dy == 0:
        return math.hypot(px - x0, py - y0)
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


def simplify(line, tolerance):
    """Ramer-Douglas-Peucker, iterative so a 10k-vertex line can't blow the stack."""
    if len(line) < 3:
        return line
    keep = [False] * len(line)
    keep[0] = keep[-1] = True
    stack = [(0, len(line) - 1)]
    while stack:
        first, last = stack.pop()
        worst, worst_index = tolerance, None
        for i in range(first + 1, last):
            d = perpendicular_distance(line[i], line[first], line[last])
            if d > worst:
                worst, worst_index = d, i
        if worst_index is not None:
            keep[worst_index] = True
            stack.append((first, worst_index))
            stack.append((worst_index, last))
    return [p for p, k in zip(line, keep) if k]


def round_line(line):
    out = []
    for x, y in line:
        point = [round(x, PRECISION), round(y, PRECISION)]
        # Rounding can collapse neighbouring vertices onto each other.
        if not out or out[-1] != point:
            out.append(point)
    return out


def build(source, tolerance):
    data = json.loads(source)
    by_country = defaultdict(list)
    for feature in data["features"]:
        cc = feature["properties"].get("iso_a2")
        if cc and cc != "-99":
            by_country[cc].append(feature)

    features = []
    for cc in sorted(by_country):
        units = by_country[cc]
        if len(units) < 2:
            continue
        lines = []
        for line in chain_edges(internal_edges(units)):
            simplified = round_line(simplify(line, tolerance))
            if len(simplified) > 1:
                lines.append(simplified)
        if not lines:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {"cc": cc, "name": units[0]["properties"].get("admin")},
                "geometry": {"type": "MultiLineString", "coordinates": lines},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def main():
    default_out = Path(__file__).resolve().parents[1] / "static" / "admin1_borders.geojson"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="local copy of the Natural Earth geojson (default: download)")
    parser.add_argument("--out", type=Path, default=default_out)
    parser.add_argument("--tolerance", type=float, default=TOLERANCE_DEG)
    args = parser.parse_args()

    if args.source:
        source = Path(args.source).read_text()
    else:
        with urllib.request.urlopen(SOURCE_URL, timeout=120) as response:
            source = response.read().decode()

    collection = build(source, args.tolerance)
    args.out.write_text(json.dumps(collection, separators=(",", ":")))
    counts = {f["properties"]["cc"]: len(f["geometry"]["coordinates"]) for f in collection["features"]}
    print(f"{args.out} — {len(collection['features'])} countries, {args.out.stat().st_size / 1024:.0f} KB")
    print("lines per country:", counts)


if __name__ == "__main__":
    main()
