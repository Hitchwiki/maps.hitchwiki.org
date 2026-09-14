"""Self-service reports using the map's existing OSM-to-ride associations."""

import csv
import io
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from statistics import median
from urllib.parse import urlencode

from flask import Blueprint, Response, abort, g, render_template, request

from hitch.helpers import get_dirs
from hitch.models import OsmHitchhikingSpot

organizers_bp = Blueprint("organizers", __name__)


@organizers_bp.before_request
def german_page():
    g.lang = "de"


def parse_bounds(raw):
    try:
        west, south, east, north = map(float, raw.split(","))
        if not all(math.isfinite(v) for v in (west, south, east, north)):
            raise ValueError
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError
        if east - west > 5 or north - south > 5:
            raise ValueError
        return west, south, east, north
    except (ValueError, AttributeError):
        abort(400, "Bitte einen Kartenausschnitt von höchstens 5° Breite und Höhe auswählen.")


def ride_date(ride):
    # Submission dates cannot measure change after a municipal intervention.
    stamp = ride.get("rd")
    if not isinstance(stamp, (float, int)) or not math.isfinite(stamp):
        return None
    try:
        return datetime.fromtimestamp(stamp / 1000, timezone.utc).date()
    except (ValueError, OverflowError, OSError):
        return None


@lru_cache(maxsize=1)
def load_evidence(dist, index_stamp, spots_stamp):
    """Refresh on generated-file changes; never spatially reassign a ride."""
    root = Path(dist)
    spots = json.loads((root / "spots.json").read_text())
    associations = {}
    unsuccessful = set()
    for spot in spots:
        if not spot.get("osm"):
            continue
        sid = f"{spot['lat']:.5f}_{spot['lon']:.5f}"
        detail = json.loads((root / "rides" / "by-spot" / f"{sid}.json").read_text())
        associations[sid] = detail["spot"]["osm_id"]
        unsuccessful.update(r["id"] for r in detail.get("rides", []) if r.get("no_ride"))
    grouped = defaultdict(list)
    seen = set()
    for ride in json.loads((root / "rides_index.json").read_text()):
        osm_id = associations.get(ride["sid"])
        if osm_id is not None and ride["id"] not in seen:
            grouped[osm_id].append({**ride, "no_ride": ride["id"] in unsuccessful})
            seen.add(ride["id"])
    return grouped


def summarize(rides):
    successful = [r for r in rides if not r.get("no_ride")]
    waits = [r["w"] for r in successful if isinstance(r.get("w"), (int, float)) and math.isfinite(r["w"]) and r["w"] >= 0]
    dates = [d for r in successful if (d := ride_date(r)) is not None]
    bins = [
        (0, 5, "unter 5"),
        (5, 15, "5 bis unter 15"),
        (15, 30, "15 bis unter 30"),
        (30, 60, "30 bis unter 60"),
        (60, 120, "60 bis unter 120"),
        (120, math.inf, "ab 120"),
    ]
    return {
        "count": len(successful),
        "records": len(rides),
        "unsuccessful": len(rides) - len(successful),
        "wait_n": len(waits),
        "median": round(median(waits), 1) if waits else None,
        "latest": max(dates).isoformat() if dates else None,
        "histogram": [{"label": label, "count": sum(low <= w < high for w in waits)} for low, high, label in bins],
    }


@organizers_bp.route("/mitfahrbaenke")
def landing():
    return render_template(
        "organizers.html", report=None, title="Mitfahrbänke auswerten – Erfahrungen und Wartezeiten", emit_hreflang=False
    )


@organizers_bp.route("/mitfahrbaenke/bericht")
def report():
    bounds = parse_bounds(request.args.get("bbox"))
    west, south, east, north = bounds
    start = end = None
    try:
        if request.args.get("von") or request.args.get("bis"):
            start = date.fromisoformat(request.args.get("von", ""))
            end = date.fromisoformat(request.args.get("bis", ""))
            if end < start or (end - start).days > 3650:
                raise ValueError
            previous_start = start - timedelta(days=(end - start).days + 1)
            previous_end = start - timedelta(days=1)
    except (ValueError, OverflowError):
        abort(400, "Bitte Anfang und Ende eines Zeitraums von höchstens zehn Jahren angeben.")

    dist = Path(get_dirs()["dist"])
    try:
        evidence = load_evidence(
            str(dist), (dist / "rides_index.json").stat().st_mtime_ns, (dist / "spots.json").stat().st_mtime_ns
        )
    except (OSError, ValueError, KeyError, TypeError):
        # Missing or mid-regeneration files are not evidence of zero use.
        abort(503, "Die Fahrtdaten werden gerade aktualisiert. Bitte später erneut versuchen.")

    stops = (
        OsmHitchhikingSpot.query.filter(
            OsmHitchhikingSpot.longitude.between(west, east), OsmHitchhikingSpot.latitude.between(south, north)
        )
        .order_by(OsmHitchhikingSpot.id)
        .all()
    )
    rows, selected, previous = [], [], []
    unknown = 0
    for stop in stops:
        rides = evidence.get(stop.id, [])
        unknown += sum(ride_date(r) is None for r in rides)
        current = [r for r in rides if not start or ((d := ride_date(r)) is not None and start <= d <= end)]
        before = [r for r in rides if start and (d := ride_date(r)) is not None and previous_start <= d <= previous_end]
        selected.extend(current)
        previous.extend(before)
        tags = stop.tags or {}
        if isinstance(tags, str):
            tags = json.loads(tags)
        rows.append(
            {
                "id": stop.id,
                "name": tags.get("name") or f"Mitfahrhalt {stop.id}",
                "lat": stop.latitude,
                "lon": stop.longitude,
                "map_url": f"/official-stop/{stop.id}",
                "stats": summarize(current),
                "previous": summarize(before),
                "spot_ids": sorted({r["sid"] for r in current}),
            }
        )
    params = {"bbox": ",".join(str(v) for v in bounds)}
    if start:
        params.update(von=start.isoformat(), bis=end.isoformat())
    report_path = "/mitfahrbaenke/bericht?" + urlencode(params)
    report_url = "https://maps.hitchwiki.org" + report_path
    data = {
        "rows": rows,
        "stats": summarize(selected),
        "previous": summarize(previous),
        "unknown": unknown,
        "bounds": bounds,
        "bbox": params["bbox"],
        "start": start,
        "end": end,
        "previous_start": previous_start if start else None,
        "previous_end": previous_end if start else None,
        "with_reports": sum(row["stats"]["records"] > 0 for row in rows),
        "updated": datetime.fromtimestamp((dist / "rides_index.json").stat().st_mtime, timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        ),
        "url": report_url,
        "path": report_path,
    }
    if request.args.get("format") == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "osm_node",
                "latitude",
                "longitude",
                "documented_rides",
                "documented_unsuccessful_attempts",
                "wait_sample_n",
                "median_wait_minutes",
                "latest_ride_date",
                "previous_period_rides",
                "from",
                "to",
                "report_url",
            ]
        )
        for row in rows:
            s = row["stats"]
            writer.writerow(
                [
                    row["id"],
                    row["lat"],
                    row["lon"],
                    s["count"],
                    s["unsuccessful"],
                    s["wait_n"],
                    s["median"],
                    s["latest"],
                    row["previous"]["count"] if start else "",
                    start or "",
                    end or "",
                    report_url,
                ]
            )
        return Response(
            "\ufeff" + output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": 'attachment; filename="mitfahrbaenke-bericht.csv"'},
        )
    return render_template(
        "organizers.html",
        report=data,
        title="Mitfahrbänke: lokaler Nutzungsbericht",
        noindex=True,
        canonical_url=report_url,
        emit_hreflang=False,
    )
