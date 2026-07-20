"""Mine ride waiting times from free-text comments and store them keyed by Nostr `d` tag.

Many hitchmap.com / hitchwiki.org rides arrive on Nostr with no `waiting_duration` on their
first stop, yet the comment states how long the hitchhiker waited before being picked up
("waited 20 min and a truck stopped"). This is data only we hold; we store the inferred
wait in `derived_ride_wait` (minutes) so it can later be merged back onto the ride's first
stop as its `waiting_duration` (DerivedRideWait.to_iso()).

Standalone script (plain `python3`, not `flask generate`) — an occasional batch job, not a
cron task. Mirrors extract_destinations.py. Three stages, run in order:

    python3 hitch/scripts/extract_wait_times.py prefilter                      # 1. candidates
    OPENAI_API_KEY=... python3 hitch/scripts/extract_wait_times.py extract     # 2. LLM
    python3 hitch/scripts/extract_wait_times.py store --db db/...              # 3. store

Stage 1 (`prefilter`) builds its own Flask app context (needs the RideEvent table) and
finds rides that have NO waiting time yet whose comment mentions a "<number> min" span —
the cheap gate the user asked for. It writes candidates.jsonl.

Stage 2 (`extract`) asks an LLM for the minutes the writer WAITED, applying the rule the
regex cannot: accept only a comment that says the person waited N minutes and then got a
ride, never a driving/journey duration ("30 min to Berlin"), an offer, or a failure. The
OpenAI key comes from the environment and is never written to disk.

Stage 3 (`store`) upserts the extracted minutes into the DB (no geocoding needed).

Stages 2 and 3 are plain stdlib (+requests) so they can run outside the app context and,
for stage 3, against the root-owned prod DB via sudo.

After running, regenerate map data + routing graph in the container (`show --force`, then
`build_ride_routes.py --skip-detailed`) so the new waits reach the map and route weights.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time

# A comment is worth an LLM call only if it names a "<number> min[ute[s]]" span. This is
# the user-specified cheap gate: it fires on both real waits ("waited 20 min") and journey
# durations ("30 min to Berlin"); the LLM stage removes the latter. \b before the digit so
# we don't fire on things like "10min" embedded in a URL/word, but still catch "20min".
_WAIT_HINT_RE = re.compile(r"\b\d{1,4}\s*min(?:ute)?s?\b", re.I)


def has_wait_hint(comment):
    return bool(comment) and bool(_WAIT_HINT_RE.search(comment))


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _existing_wait_minutes(stops):
    """Return the recorded waiting time (minutes) on the ride's first stop, or None.

    A ride already carrying a `waiting_duration` needs no enrichment, so it is skipped.
    Mirrors build_ride_routes.parse_wait: ISO 8601 'PT30M' / 'PT1H15M' -> minutes.
    """
    if not isinstance(stops, list) or not stops:
        return None
    iso = (stops[0] or {}).get("waiting_duration")
    if not iso or not isinstance(iso, str):
        return None
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso.strip())
    if not m or (m.group(1) is None and m.group(2) is None):
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


# ---------------------------------------------------------------------------
# Stage 1: prefilter
# ---------------------------------------------------------------------------


def cmd_prefilter(args):
    # Imported here so stages 2/3 stay free of the Flask/app dependency.
    from hitch import create_app
    from hitch.models import RideEvent

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
            # Only rides that don't already record a wait, and only those whose comment
            # mentions a "<number> min" span worth spending an LLM call on.
            if _existing_wait_minutes(r.stops) is not None:
                continue
            if not has_wait_hint(r.comment):
                continue
            out.write(json.dumps({"d": r.d, "id": r.id, "source": r.source, "comment": r.comment}, ensure_ascii=False) + "\n")
            written += 1
    print(f"wrote {written} candidates -> {args.out}")


# ---------------------------------------------------------------------------
# Stage 2: LLM extraction
# ---------------------------------------------------------------------------

_SYSTEM = """You read short hitchhiking spot-review comments and extract how many MINUTES \
the writer WAITED for a ride before being picked up, if the comment states it.

Return the number of minutes ONLY when the comment says the writer waited that long and \
then GOT a ride (any mode: car, truck, lift, hitch, bus). Examples that qualify: "waited \
20 min and a truck stopped", "picked up after 10 minutes", "5 min wait", "got a ride \
within 15 minutes".

Return null when the "<number> min" refers to anything other than the wait that ended in \
a pickup, including: the driving/journey duration ("30 min to Berlin", "1h drive", "the \
ride was 45 minutes"); walking time ("10 min walk to the ramp"); how long the writer \
waited but then GAVE UP without a ride; an offer not clearly taken; advice/habit ("usually \
wait 10 min here"); or any span not clearly a wait-then-ride.

If a range is given ("20-30 min"), return the upper bound. If several waits appear, return \
the one for the writer's own successful ride from THIS spot. Output whole minutes only.

Reply ONLY with JSON: {"results":[{"i":<index>,"minutes":<number or null>}, ...]} for every index."""

_FEWSHOT_USER = """0. waited about 20 min and a truck stopped
1. 30 min to get to Berlin, easy ride
2. picked up after 10 minutes, super friendly driver
3. waited an hour, gave up and took the bus
4. usually you wait 10 min here, good spot
5. 5 min wait then a car to Lyon
6. it's a 15 min walk from the station to this ramp"""

_FEWSHOT_ASSISTANT = (
    '{"results":[{"i":0,"minutes":20},{"i":1,"minutes":null},{"i":2,"minutes":10},'
    '{"i":3,"minutes":null},{"i":4,"minutes":null},{"i":5,"minutes":5},{"i":6,"minutes":null}]}'
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
            return {int(x["i"]): x.get("minutes") for x in data.get("results", [])}
        except (requests.RequestException, ValueError, KeyError):
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    return {}


def _coerce_minutes(v):
    """Accept an int or a clean numeric string; reject 0/negatives and implausible waits."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    # 0 is not a wait; cap absurd values (>24 h) that would be a model/parse error.
    if n <= 0 or n > 1440:
        return None
    return n


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
                minutes = _coerce_minutes(res.get(i))
                if minutes is not None:
                    out.write(json.dumps({"d": c["d"], "minutes": minutes, "comment": c["comment"]}, ensure_ascii=False) + "\n")
                    kept += 1
            out.flush()
            print(f"  {b + len(chunk)}/{len(todo)} processed, {kept} kept", flush=True)
    print(f"done: {kept} waits from {len(todo)} candidates")


# ---------------------------------------------------------------------------
# Stage 3: store
# ---------------------------------------------------------------------------


def _ensure_table(conn):
    # CREATE IF NOT EXISTS mirrors DerivedRideWait; there is no migration framework.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS derived_ride_wait (
             d TEXT PRIMARY KEY,
             waiting_minutes INTEGER NOT NULL,
             source_comment TEXT,
             kind TEXT,
             created_at INTEGER
           )"""
    )


def cmd_store(args):
    rows = []
    now = int(time.time())
    for o in _read_jsonl(args.extractions):
        minutes = _coerce_minutes(o.get("minutes"))
        if minutes is None:
            continue
        rows.append((o["d"], minutes, o.get("comment"), "derived-comment-wait", now))

    print(f"storing {len(rows)} waits")
    if args.dry_run:
        for _d, minutes, comment, _kind, _now in rows[:40]:
            print(f"  {minutes:>4} min  {(comment or '')[:80]!r}")
        return

    conn = sqlite3.connect(args.db)
    _ensure_table(conn)
    conn.executemany(
        """INSERT INTO derived_ride_wait (d, waiting_minutes, source_comment, kind, created_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(d) DO UPDATE SET
             waiting_minutes=excluded.waiting_minutes,
             source_comment=excluded.source_comment, kind=excluded.kind""",
        rows,
    )
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM derived_ride_wait").fetchone()[0]
    conn.close()
    print(f"stored/updated {len(rows)} rows; table now has {total}")


# ---------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prefilter", help="scan RideEvent for no-wait comments that mention '<n> min'")
    p.add_argument("--out", default="dist/enrichment/wait_candidates.jsonl")
    p.set_defaults(func=cmd_prefilter)

    p = sub.add_parser("extract", help="LLM-extract the minutes waited per comment")
    p.add_argument("--candidates", default="dist/enrichment/wait_candidates.jsonl")
    p.add_argument("--out", default="dist/enrichment/wait_extractions.jsonl")
    p.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    p.add_argument("--batch", type=int, default=25)
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("store", help="upsert extracted waits into the DB")
    p.add_argument("--extractions", default="dist/enrichment/wait_extractions.jsonl")
    p.add_argument("--db", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_store)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
