"""Mine ride destinations from free-text comments and store them keyed by Nostr `d` tag.

Some hitchmap.com / hitchwiki.org rides arrive on Nostr with no destination in their
`stops`, yet the comment names the city the ride actually reached ("got a lift to
Kayseri"). This is data only we hold; we store the inferred destination in
`derived_ride_location` (is_exact=0) so it can later be merged onto the ride as an extra
stop (DerivedRideLocation.to_stop()).

Standalone script (plain `python3`, not `flask generate`) — this is an occasional batch
job, not a cron task. Three stages, run in order:

    python3 hitch/scripts/extract_destinations.py prefilter                      # 1. candidates
    OPENAI_API_KEY=... python3 hitch/scripts/extract_destinations.py extract     # 2. LLM
    python3 hitch/scripts/extract_destinations.py geocode-store --db db/...       # 3. store

Stage 1 (`prefilter`) builds its own Flask app context (needs the RideEvent table) and
finds no-destination rides whose comment says the ride *arrived* somewhere ("<transport
cue> ... to <Place>"), not merely headed there, and writes candidates.jsonl.

Stage 2 (`extract`) asks an LLM which city each comment's ride actually reached, applying
the arrival-only rules the gate can only approximate. OpenAI key comes from the
environment and is never written to disk.

Stage 3 (`geocode-store`) resolves each city against dist/worldcities.csv (diacritic /
Turkish / endonym folded, nearest-to-start disambiguation) and upserts into the DB.

Stages 2 and 3 are plain stdlib (+requests) so they can run outside the app context and,
for stage 3, against the root-owned prod DB via sudo.
"""

import argparse
import csv
import json
import math
import os
import re
import sqlite3
import sys
import time
import unicodedata

# ---------------------------------------------------------------------------
# Shared name normalisation + gazetteer
# ---------------------------------------------------------------------------

# Local spellings an LLM tends to emit that the pop>50k gazetteer only lists under its
# English exonym. Compared post-fold, so the accents here are cosmetic.
_ALIASES = {
    "koln": "cologne",
    "munchen": "munich",
    "wien": "vienna",
    "milano": "milan",
    "torino": "turin",
    "roma": "rome",
    "napoli": "naples",
    "firenze": "florence",
    "venezia": "venice",
    "genova": "genoa",
    "praha": "prague",
    "pilsen": "plzen",
    "lisboa": "lisbon",
    "sevilla": "seville",
    "moskva": "moscow",
    "warszawa": "warsaw",
    "bruxelles": "brussels",
    "goteborg": "gothenburg",
    "kobenhavn": "copenhagen",
    "beograd": "belgrade",
    "bucuresti": "bucharest",
    "antwerpen": "antwerp",
    "den haag": "the hague",
    "nurnberg": "nuremberg",
}


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def normalize_name(s):
    if not s:
        return ""
    # Turkish dotted/dotless i (İstanbul.lower() keeps a combining dot) then strip accents.
    s = s.replace("İ", "I").replace("ı", "i")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.strip().lower()
    return _ALIASES.get(s, s)


def load_gazetteer(path):
    idx = {}  # normalized name -> [(lat, lon, population, canonical_name), ...]
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                lat, lon = float(row["lat"]), float(row["lng"])
            except (ValueError, KeyError):
                continue
            try:
                pop = float(row.get("population") or 0)
            except ValueError:
                pop = 0.0
            canon = row.get("city") or row.get("city_ascii") or ""
            for key in {normalize_name(row.get("city")), normalize_name(row.get("city_ascii"))}:
                if key:
                    idx.setdefault(key, []).append((lat, lon, pop, canon))
    return idx


def _haversine(a_lat, a_lon, b_lat, b_lon):
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def geocode(name, start_lat, start_lon, gaz):
    matches = gaz.get(normalize_name(name))
    if not matches:
        return None
    # Same-named cities: take the one nearest the ride start; among those within 25 km of
    # the nearest, prefer the most populous so a hamlet never shadows the real city.
    scored = sorted(matches, key=lambda m: _haversine(start_lat, start_lon, m[0], m[1]))
    nearest = _haversine(start_lat, start_lon, scored[0][0], scored[0][1])
    close = [m for m in scored if _haversine(start_lat, start_lon, m[0], m[1]) <= nearest + 25]
    best = max(close, key=lambda m: m[2])
    return best[0], best[1], best[3]


# ---------------------------------------------------------------------------
# Stage 1: prefilter
# ---------------------------------------------------------------------------

# A "to <Place>" mention that we only keep when preceded (within ~40 chars) by a cue that
# the writer was actually moving/carried — an arrival, not advice or a direction. Tuned
# for ~95% recall on a hand-labelled sample; the LLM stage removes the false positives.
_ARRIVAL_RE = re.compile(
    r"\b(?:ride|rides|lift|hike[ds]?|hitch\w*|truck|car|drive|drove|driven|dropped|drop|taken|took|"
    r"brought|bring|made\s+it|got|get|getting|gave|caught|catch|picked\s+up|rode|"
    r"bus|taxi|dolmu\w*|marshrutka|marshutka|ferry|train|van|minibus|autobus|autostop|"
    r"paid|free|went)\b[^.!?]{0,40}\bto\s+([\wÀ-ÿ][\wÀ-ÿ' .-]*)",
    re.I,
)


def explicit_to_city(comment, gaz):
    """If the comment says the ride went "to <Place>" and <Place> starts with the name of
    a known city, return that city; else None. This is the cheap gate that keeps prefilter
    output to real destinations (a bare "to the coast" or "to my friend's" is dropped
    before it ever costs an LLM call). Tries 3→1 word windows so multi-word names win."""
    m = _ARRIVAL_RE.search(comment)
    if not m:
        return None
    words = re.findall(r"[\wÀ-ÿ]+", m.group(1))[:3]
    for n in range(len(words), 0, -1):
        cand = " ".join(words[:n])
        if normalize_name(cand) in gaz:
            return cand
    return None


def _first_coord(stop):
    loc = (stop or {}).get("location") or {}
    lat, lon = loc.get("latitude"), loc.get("longitude")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def start_and_has_dest(stops):
    """Return (start_lat, start_lon) if the ride has a usable start but no distinct
    destination, else None. Destination = a later stop with coordinates different from the
    start; those rides already know where they went and need no enrichment."""
    if not isinstance(stops, list) or not stops:
        return None
    start = _first_coord(stops[0])
    if not start:
        return None
    for s in stops[1:]:
        c = _first_coord(s)
        if c and (abs(c[0] - start[0]) > 1e-6 or abs(c[1] - start[1]) > 1e-6):
            return None  # already has a destination
    return start


def cmd_prefilter(args):
    # Imported here so stages 2/3 stay free of the Flask/app dependency.
    from hitch import create_app
    from hitch.models import RideEvent

    gaz = load_gazetteer(args.gazetteer)
    app = create_app()
    written = 0
    with app.app_context(), open(args.out, "w", encoding="utf-8") as out:
        q = RideEvent.query.filter(RideEvent.comment.isnot(None))
        for r in q:
            if not r.d or not r.comment:
                continue
            src = (r.source or "").lower()
            if "hitchmap" not in src and "hitchwiki" not in src:
                continue
            start = start_and_has_dest(r.stops)
            if not start:
                continue
            hint = explicit_to_city(r.comment, gaz) if args.require_arrival else None
            if args.require_arrival and not hint:
                continue
            out.write(
                json.dumps(
                    {
                        "d": r.d,
                        "id": r.id,
                        "source": r.source,
                        "start_lat": start[0],
                        "start_lon": start[1],
                        "comment": r.comment,
                        "hint": hint,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            written += 1
    print(f"wrote {written} candidates -> {args.out}")


# ---------------------------------------------------------------------------
# Stage 2: LLM extraction
# ---------------------------------------------------------------------------

_SYSTEM = """You read short hitchhiking spot-review comments and extract the destination \
city that the writer's ride ACTUALLY reached, if any. Any transport mode counts (car, \
truck, lift, hitch, bus, train, taxi, ferry).

Return the city ONLY when the comment says the traveler was actually taken to / got a ride \
to / reached a specific named city. Return null when the comment only: gives advice or \
reachability ("good spot to X", "easy to get to X"); states a direction ("towards X", \
"heading to X" with no arrival); states intent without arrival ("wanted to go to X"); \
describes an offer not clearly taken; describes a failure; is habitual ("I always get a \
ride to X"); or names something that is not a city (a country, region, "the border", \
"the airport", "city center").

If the ride was cut short, return the city ACTUALLY reached, not the intended one. If \
several cities appear, return the one the writer's own ride reached from THIS spot. Output \
the bare city name, no country, common local spelling.

Reply ONLY with JSON: {"results":[{"i":<index>,"city":<name or null>}, ...]} for every index."""

_FEWSHOT_USER = """0. got a lift to Kayseri
1. no problems to catch a ride to Batman from here. Good spot.
2. Good spot for hitchhiking towards Erzurum
3. I was going to Poti but the first driver took me only to Kobuleti
4. I always got a ride from here to Helsinki in 10 minutes
5. wanted to go to munich, ended up on a car to regensburg
6. Got offered a ride to Basel within 30 mins"""

_FEWSHOT_ASSISTANT = (
    '{"results":[{"i":0,"city":"Kayseri"},{"i":1,"city":null},{"i":2,"city":null},'
    '{"i":3,"city":"Kobuleti"},{"i":4,"city":null},{"i":5,"city":"Regensburg"},{"i":6,"city":null}]}'
)


def _openai_batch(comments, key, model, retries=4):
    import requests

    numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(comments))
    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _FEWSHOT_USER},
            {"role": "assistant", "content": _FEWSHOT_ASSISTANT},
            {"role": "user", "content": numbered},
        ],
    }
    for attempt in range(retries):
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=body,
                timeout=120,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            data = json.loads(resp.json()["choices"][0]["message"]["content"])
            return {int(x["i"]): x.get("city") for x in data.get("results", [])}
        except (requests.RequestException, ValueError, KeyError):
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    return {}


def cmd_extract(args):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY not set")
    cands = _read_jsonl(args.candidates)

    done = set()
    if os.path.exists(args.out):
        done = {o["d"] for o in _read_jsonl(args.out)}
    todo = [c for c in cands if c["d"] not in done]
    print(f"{len(todo)} to process (skipping {len(done)} already done)")

    kept = 0
    with open(args.out, "a", encoding="utf-8") as out:
        for b in range(0, len(todo), args.batch):
            chunk = todo[b : b + args.batch]
            res = _openai_batch([c["comment"] for c in chunk], key, args.model)
            for i, c in enumerate(chunk):
                city = res.get(i)
                if isinstance(city, str) and city.strip():
                    out.write(json.dumps({"d": c["d"], "destination": city.strip()}, ensure_ascii=False) + "\n")
                    kept += 1
            out.flush()
            print(f"  {b + len(chunk)}/{len(todo)} processed, {kept} kept", flush=True)
    print(f"done: {kept} destinations from {len(todo)} candidates")


# ---------------------------------------------------------------------------
# Stage 3: geocode + store
# ---------------------------------------------------------------------------


def _ensure_table(conn):
    # CREATE IF NOT EXISTS mirrors DerivedRideLocation; there is no migration framework.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS derived_ride_location (
             d TEXT PRIMARY KEY,
             latitude REAL NOT NULL,
             longitude REAL NOT NULL,
             is_exact BOOLEAN NOT NULL DEFAULT 0,
             location_name TEXT,
             source_comment TEXT,
             kind TEXT,
             created_at INTEGER
           )"""
    )


def cmd_geocode_store(args):
    gaz = load_gazetteer(args.gazetteer)
    cand = {}
    for path in args.candidates:
        for o in _read_jsonl(path):
            cand[o["d"]] = o

    rows, unresolved = [], []
    now = int(time.time())
    for o in _read_jsonl(args.extractions):
        d, dest = o["d"], o.get("destination")
        if not dest:
            continue
        c = cand.get(d)
        if not c:
            unresolved.append((dest, "no-candidate"))
            continue
        g = geocode(dest, c["start_lat"], c["start_lon"], gaz)
        if not g:
            unresolved.append((dest, "no-gazetteer-match"))
            continue
        lat, lon, canon = g
        rows.append((d, lat, lon, 0, canon, c.get("comment"), "derived-comment-city", now))

    print(f"resolved {len(rows)}, unresolved {len(unresolved)}")
    if args.dry_run:
        for dest, why in unresolved[:40]:
            print(f"  UNRESOLVED [{why}] {dest!r}")
        return

    conn = sqlite3.connect(args.db)
    _ensure_table(conn)
    conn.executemany(
        """INSERT INTO derived_ride_location
             (d, latitude, longitude, is_exact, location_name, source_comment, kind, created_at)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(d) DO UPDATE SET
             latitude=excluded.latitude, longitude=excluded.longitude,
             is_exact=excluded.is_exact, location_name=excluded.location_name,
             source_comment=excluded.source_comment, kind=excluded.kind""",
        rows,
    )
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM derived_ride_location").fetchone()[0]
    conn.close()
    print(f"stored/updated {len(rows)} rows; table now has {total}")


# ---------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prefilter", help="scan RideEvent for no-destination arrival comments")
    p.add_argument("--out", default="dist/enrichment/dest_candidates.jsonl")
    p.add_argument("--gazetteer", default="dist/worldcities.csv")
    p.add_argument(
        "--no-require-arrival",
        dest="require_arrival",
        action="store_false",
        help="keep every no-destination comment, not only arrival-to-a-known-city ones",
    )
    p.set_defaults(func=cmd_prefilter, require_arrival=True)

    p = sub.add_parser("extract", help="LLM-extract the reached city per comment")
    p.add_argument("--candidates", default="dist/enrichment/dest_candidates.jsonl")
    p.add_argument("--out", default="dist/enrichment/dest_extractions.jsonl")
    p.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    p.add_argument("--batch", type=int, default=25)
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("geocode-store", help="geocode extracted cities and upsert into the DB")
    p.add_argument("--extractions", default="dist/enrichment/dest_extractions.jsonl")
    p.add_argument("--candidates", nargs="+", default=["dist/enrichment/dest_candidates.jsonl"])
    p.add_argument("--gazetteer", default="dist/worldcities.csv")
    p.add_argument("--db", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_geocode_store)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
