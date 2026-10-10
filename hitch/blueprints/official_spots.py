"""All known official stops, including places with no ride contributions yet."""

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

from flask import Blueprint, abort, jsonify, redirect, render_template, request

from hitch.helpers import get_dirs
from hitch.models import OsmHitchhikingSpot

official_spots_bp = Blueprint("official_spots", __name__)


@lru_cache(maxsize=1)
def _reviewed_links(dist, stamp, generation_stamp):
    root = Path(dist)
    links = {}
    for spot in json.loads((root / "spots.json").read_text()):
        if not spot.get("osm"):
            continue
        sid = f"{spot['lat']:.5f}_{spot['lon']:.5f}"
        detail = json.loads((root / "rides" / "by-spot" / f"{sid}.json").read_text())
        osm_id = detail["spot"].get("osm_id")
        if osm_id is not None:
            links.setdefault(osm_id, []).append((sid, spot["lat"], spot["lon"]))
    return links


def reviewed_links():
    root = Path(get_dirs()["dist"])
    try:
        generated = root / "generated_at.json"
        return _reviewed_links(
            str(root), (root / "spots.json").stat().st_mtime_ns, generated.stat().st_mtime_ns if generated.exists() else 0
        )
    except (OSError, ValueError, KeyError, TypeError):
        # The registry must remain visible on a fresh install or during regeneration.
        # Exceptions are not cached, so the next request can use completed detail files.
        return {}


def map_spot_id(stop, links):
    candidates = links.get(stop.id, [])
    if candidates:
        # Preserve the map's existing association; never invent reviews for a bench.
        return min(candidates, key=lambda s: ((s[1] - stop.latitude) ** 2 + (s[2] - stop.longitude) ** 2, s[0]))[0]
    return f"{stop.latitude:.5f}_{stop.longitude:.5f}"


@official_spots_bp.route("/official-stops.json")
def official_stops():
    links = reviewed_links()
    markers = []
    for stop in OsmHitchhikingSpot.query.order_by(OsmHitchhikingSpot.id):
        tags = stop.tags or {}
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except ValueError:
                tags = {}
        markers.append(
            {
                "lat": round(stop.latitude, 5),
                "lon": round(stop.longitude, 5),
                "osm": True,
                "osm_id": stop.id,
                "name": tags.get("name") or "",
                "rating": None,
                "review_count": 0,
                "official_unreviewed": True,
                "map_spot_id": map_spot_id(stop, links),
            }
        )
    response = jsonify(markers)
    response.headers["Cache-Control"] = "public, max-age=60"
    return response


@official_spots_bp.route("/official-stop/<int:osm_id>")
def official_stop(osm_id):
    stop = OsmHitchhikingSpot.query.filter_by(id=osm_id).first()
    if stop is None:
        abort(404)
    # Temporary: when a first ride is logged nearby, the representative spot can move.
    target = "/spot/" + map_spot_id(stop, reviewed_links())
    # Keep a ?ref= tag (printed bench QR codes, municipality links) so base.html's
    # referred_via capture can attribute the visit; nothing else is forwarded.
    ref = request.args.get("ref", "")[:40]
    if ref:
        target += "?" + urlencode({"ref": ref})
    return redirect(target, code=302)


TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "translations"
BENCH_TOWNS_PATH = Path(__file__).resolve().parent.parent / "data" / "bench_towns.json"


BENCH_STREETS_PATH = Path(__file__).resolve().parent.parent / "data" / "bench_streets.json"


@lru_cache(maxsize=1)
def bench_streets():
    """Street per official stop (Nominatim reverse, (c) OpenStreetMap contributors, ODbL)."""
    try:
        return json.loads(BENCH_STREETS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


BENCH_RIDES_PATH = Path(__file__).resolve().parent.parent / "data" / "bench_rides.json"


@lru_cache(maxsize=1)
def bench_rides():
    """Logged rides within 100 m of a town's stops: {slug: {"rides": n, "stops": k}} (n >= 1 only)."""
    try:
        return json.loads(BENCH_RIDES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


@lru_cache(maxsize=1)
def bench_towns():
    """Snapshot of official stops grouped by town (research/bench-towns-2026-10.md)."""
    return json.loads(BENCH_TOWNS_PATH.read_text(encoding="utf-8"))


_BENCH_LANG = {"fr": "fr", "nl": "nl", "dk": "da", "us": "en"}

# Page chrome per language. Keys with a trailing _1 / _n are singular / plural.
_BENCH_STRINGS = {
    "de": {
        "title": "Mitfahrbänke in {name}",
        "all": "Alle Orte",
        "intro_1": (
            "{n} offizieller Mitfahrhalt in {name}{state}. "
            "Öffne einen Halt, um Erfahrungen anderer zu lesen und deine eigene Fahrt einzutragen."
        ),
        "intro_n": (
            "{n} offizielle Mitfahrhalte in {name}{state}. "
            "Öffne einen Halt, um Erfahrungen anderer zu lesen und deine eigene Fahrt einzutragen."
        ),
        "rides_1": "{r} Fahrt im Umkreis von 100 m dieser Halte eingetragen.",
        "rides_n": "{r} Fahrten im Umkreis von 100 m dieser Halte eingetragen.",
        "map": "Auf der Karte ansehen",
        "add": "Eine Bank fehlt? Auf der Karte ergänzen",
        "stop": "Mitfahrhalt",
    },
    "fr": {
        "title": "Arrêts de covoiturage Rezo Pouce à {name}",
        "all": "Tous les lieux",
        "intro_1": (
            "{n} arrêt officiel dans cette commune{state}. "
            "Ouvrez un arrêt pour voir les expériences d'autres personnes et ajouter la vôtre."
        ),
        "intro_n": (
            "{n} arrêts officiels dans cette commune{state}. "
            "Ouvrez un arrêt pour voir les expériences d'autres personnes et ajouter la vôtre."
        ),
        "rides_1": "{r} trajet enregistré à moins de 100 m de ces arrêts.",
        "rides_n": "{r} trajets enregistrés à moins de 100 m de ces arrêts.",
        "map": "Voir sur la carte",
        "add": "Un banc manque ? Ajoutez-le sur la carte",
        "stop": "Arrêt",
    },
    "nl": {
        "title": "Liftplekken in {name}",
        "all": "Alle plaatsen",
        "intro_1": (
            "{n} officiële liftplek in {name}{state}. "
            "Open een plek om ervaringen van anderen te lezen en je eigen rit toe te voegen."
        ),
        "intro_n": (
            "{n} officiële liftplekken in {name}{state}. "
            "Open een plek om ervaringen van anderen te lezen en je eigen rit toe te voegen."
        ),
        "rides_1": "{r} rit geregistreerd binnen 100 m van deze plekken.",
        "rides_n": "{r} ritten geregistreerd binnen 100 m van deze plekken.",
        "map": "Bekijk op de kaart",
        "add": "Ontbreekt er een bank? Voeg hem toe op de kaart",
        "stop": "Liftplek",
    },
    "da": {
        "title": "Blafferpladser i {name}",
        "all": "Alle steder",
        "intro_1": (
            "{n} officiel blafferplads i {name}{state}. "
            "Åbn en plads for at læse andres erfaringer og tilføje din egen tur."
        ),
        "intro_n": (
            "{n} officielle blafferpladser i {name}{state}. "
            "Åbn en plads for at læse andres erfaringer og tilføje din egen tur."
        ),
        "rides_1": "{r} tur registreret inden for 100 m af disse pladser.",
        "rides_n": "{r} ture registreret inden for 100 m af disse pladser.",
        "map": "Se på kortet",
        "add": "Mangler der en bænk? Tilføj den på kortet",
        "stop": "Plads",
    },
    "en": {
        "title": "Hitchhiking spots in {name}",
        "all": "All places",
        "intro_1": (
            "{n} official hitchhiking spot in {name}{state}. "
            "Open a spot to read others' experiences and add your own ride."
        ),
        "intro_n": (
            "{n} official hitchhiking spots in {name}{state}. "
            "Open a spot to read others' experiences and add your own ride."
        ),
        "rides_1": "{r} ride logged within 100 m of these spots.",
        "rides_n": "{r} rides logged within 100 m of these spots.",
        "map": "View on the map",
        "add": "A bench is missing? Add it on the map",
        "stop": "Spot",
    },
}


@official_spots_bp.route("/mitfahrbank/<slug>")
def bench_town(slug):
    town = bench_towns().get(slug)
    if town is None:
        abort(404)
    # All six Belgian towns are Ostbelgien (German-speaking); the French
    # "Rezo Pouce" wording is for France only. NL/DK/US get their own language
    # rather than German (the pledge strings already exist in nl/da/en).
    lang = _BENCH_LANG.get(town["cc"], "de")
    fr = lang == "fr"
    n = len(town["stops"])
    L = _BENCH_STRINGS[lang]
    title = L["title"].format(name=town["name"])
    lat = sum(s[1] for s in town["stops"]) / n
    lon = sum(s[2] for s in town["stops"]) / n
    tr_file = {"de": "de.json", "fr": "fr.json", "nl": "nl.json", "da": "da.json"}.get(lang)
    tr = json.loads((TRANSLATIONS_DIR / tr_file).read_text(encoding="utf-8")) if tr_file else {}
    pledge_btn = tr.get("I'll stop for a hitchhiker when I'm driving", "I'll stop for a hitchhiker when I'm driving")
    pledge_note = tr.get("Pledge made — thank you.", "Pledge made — thank you.")
    return render_template(
        "bench_town.html",
        title=title,
        town=town,
        n=n,
        fr=fr,
        L=L,
        plural=n > 1,
        page_lang=lang,
        streets=bench_streets(),
        ride_count=bench_rides().get(slug),
        lat=round(lat, 5),
        lon=round(lon, 5),
        pledge_btn=pledge_btn,
        pledge_note=pledge_note,
        emit_hreflang=False,
    )


@official_spots_bp.route("/mitfahrbank/")
@official_spots_bp.route("/mitfahrbank")
def bench_town_index():
    groups = {}
    for slug, t in bench_towns().items():
        groups.setdefault((t["cc"], t["state"]), []).append((t["name"], slug, len(t["stops"])))
    ordered = [(cc, st, sorted(items)) for (cc, st), items in sorted(groups.items())]
    return render_template(
        "bench_town_index.html", groups=ordered, total=len(bench_towns()), title="Mitfahrbänke nach Ort", emit_hreflang=False
    )
