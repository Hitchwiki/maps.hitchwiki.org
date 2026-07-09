"""Routing engine over the repeatable hitchhiking routes.

TL;DR
-----
Construct a graph of of ride we think are repeatable (that is a route that was taken by at least two rides starting from the same spot
- if there is one longer and one shorter route only the overlapping route counts, as one could just have taken the longer ride and
asked to exit earlier, but the rest of the longer route is not considered because there is not enough evidence that it is repeatable).
For a route we consider all spots that it passes along as possibilities to switch cars such that we can not only recommend to do the exact ride as in our database but
also account for asking to exit earlier (e.g. on a rest station on a highway). To calculate times of routes we consider walking to 
and in between spots that are not reachable by a car ride, naive travel times for the car rides and the average waiting time for a ride at a spot.

Every leg costs minutes: walking at WALK_SPEED_KMH, riding at CAR_SPEED_KMH, plus the measured
average *waiting time* each time you catch a new ride. `routes()` returns up to k
genuinely different alternatives.

TODO: Weight how certain one can get a suggested ride: we should prefer a route that was taken 10 times reliabily over one that was just
taken 2 time.

Assumed parameters
------------------
  WALK_SPEED_KMH      = 5     walking pace
  CAR_SPEED_KMH       = 100   average speed once you're in a car
  CAR_ROAD_FACTOR     = 1.25  great-circle -> road distance fudge for car edges
  DEFAULT_MAX_WALK_KM = 20.0  how far you'll walk: origin->spot, spot->dest and
                              spot<->spot (override via --max-walk-km; the web UI
                              in static/routing.js uses the same 20 km)
  waiting time        = the average waiting time of all rides recorded on that
                        edge; edges with no data fall back to the global average
                        (self.default_wait), so an unknown edge is never "free".

The data (dist/repeatable_routes.json)
--------------------------------------
build_ride_routes.py groups each ride's start into a canonical spot (matching the
map's spots), routes the ride with OSRM, records which other spots that route
passes, and merges those sequences into a prefix tree per start spot. Branches
supported by fewer than 2 rides are pruned. What survives is a set of
*corridors*: trees rooted at a spot where rides actually begin.

    corridor rooted at A          spots: A B C D E
                                  "3 rides went A->B->C, 2 of them continued to D,
      A --> B --> C --> D          2 other rides went A->B->E"
             \\
              --> E

Graph model
-----------
  * Nodes are spots. A **car edge** is one parent->child step of a corridor tree,
    directed (rides flow outward from the root), length = great-circle *
    CAR_ROAD_FACTOR, cost = travel time.
  * **Boarding is only allowed at a corridor's root** — the spot where its rides
    actually start. A mid-corridor node is a place the car merely drives past at
    speed; you cannot flag down a new ride there. You may *alight* anywhere, and
    you ride onward through a corridor for free (you're already in the car).
  * **Walk edges** (undirected) connect the origin to nearby spots, spots to the
    destination, and spot<->spot within max_walk_km — the last kind lets you hop
    between two corridors that pass close but share no spot. A direct
    origin->destination walk is allowed too.
  * Only spots taking part in a car edge are walkable; a spot no car passes is a
    dead end.

The search: corridor-aware Dijkstra
-----------------------------------
A plain shortest-path over spots can't tell "still in the same car" from "got out
and flagged a new one" — only the latter costs a wait. So a **state is
(spot, corridor)**, where `corridor` is the tree you're currently riding, or
NO_TREE (-1) when you're on foot:

    (A, NO_TREE) --board, +wait(A,B)--> (B, corridor_1)   caught a ride at root A
    (B, corridor_1) --car, free-------> (C, corridor_1)   still in the same car
    (C, corridor_1) --walk------------> (C', NO_TREE)     got out, walked over
    (C', NO_TREE) --board, +wait------> (D, corridor_2)   caught a different ride

Continuing a corridor is free; every *board* pays that edge's waiting time. Thus a
journey pays exactly one wait per distinct ride, whether the change of car happens
after a walk or by switching corridors at a shared spot. Dijkstra over these
states then yields the fastest realistic journey, and _itinerary() collapses the
step-by-step predecessor chain into human-readable legs (each "board" starts a new
car leg).

    origin ~~walk~~> A ==car==> C ~~walk~~> C' ==car==> E ~~walk~~> destination
           (first mile)                                        (last mile)

Alternatives (`routes`) use the penalty method: find the fastest route, multiply
the car edges it used by `penalty`, search again, and keep a candidate only if it
shares less than `max_overlap` of its car distance with every route already kept.
Reported times are always the true, unpenalised ones.

Everything is time-based (minutes); the returned itinerary is the fastest journey.

Note: static/routing.js is a JS port of this engine and must stay numerically
identical — apply engine changes to both.
"""

import argparse
import heapq
import json
import math
import os

WALK_SPEED_KMH = 5
CAR_SPEED_KMH = 100

# Great-circle distances underestimate real roads; nudge car segments up a little.
CAR_ROAD_FACTOR = 1.25

# How far one is willing to walk (origin->spot, spot->dest, spot<->spot), km.
DEFAULT_MAX_WALK_KM = 20.0

EARTH_RADIUS_KM = 6371.0

ORIGIN = -2
DEST = -1


def haversine_km(lat1, lon1, lat2, lon2):
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


class RepeatableRouter:
    def __init__(self, data, max_walk_km=DEFAULT_MAX_WALK_KM):
        self.spots = data["spots"]  # [[lat, lon], ...]
        self.max_walk_km = max_walk_km
        self._build_graph(data["trees"])
        self._build_walk_edges()

    # -- graph construction ---------------------------------------------------

    def _build_graph(self, trees):
        """Per-corridor (tree) car adjacency so the router can tell continuing the
        same ride from switching cars.

        A single physical ride is a path within one tree, so:
          * tree_adj[t][u] = onward edges of corridor t from spot u  (continue: free)
          * board[u]       = corridor edges you may BOARD at u        (board / change
                             car: costs that edge's waiting time)
        edge_km / edge_wait key each (u, v) once for overlap scoring and wait lookup.

        Boarding is only allowed at a corridor's ROOT — the spot where its rides
        actually start. A mid-corridor node is a place the car merely passes at
        speed; you can't flag a new ride there unless rides are also known to
        start there (which would be its own corridor with its own root). Allowing
        boarding at pass-through nodes produced routes that told the user to
        "change here" at a spot whose only ride doesn't even go that direction.
        """
        self.edge_km = {}
        self.edge_wait = {}
        self.tree_adj = []   # tree_id -> {u: [(v, km, wait)]}
        self.board = {}      # u -> [(tree_id, v, km, wait)]  (boardable edges at u)
        car_spots = set()
        waits = []
        for tree in trees:
            t_id = len(self.tree_adj)
            root = tree["s"]
            nodes = tree["nodes"]
            adj = {}
            for node in nodes:
                spot, parent = node[0], node[1]
                wait = node[3] if len(node) > 3 else None
                frm = root if parent == -1 else nodes[parent][0]
                a, b = self.spots[frm], self.spots[spot]
                km = haversine_km(a[0], a[1], b[0], b[1]) * CAR_ROAD_FACTOR
                adj.setdefault(frm, []).append((spot, km, wait))
                # Only the root's own first-hop edges are boardable; downstream
                # edges are reachable by continuing the ride (tree_adj), not by
                # boarding fresh at a pass-through spot.
                if frm == root:
                    self.board.setdefault(frm, []).append((t_id, spot, km, wait))
                self.edge_km[(frm, spot)] = km
                self.edge_wait[(frm, spot)] = wait
                if wait is not None:
                    waits.append(wait)
                car_spots.add(frm)
                car_spots.add(spot)
            self.tree_adj.append(adj)
        # Fallback wait for edges lacking recorded data: the global average, so an
        # unknown-wait corridor isn't treated as instant boarding.
        self.default_wait = round(sum(waits) / len(waits), 1) if waits else 0.0
        self.car_spots = sorted(car_spots)

    def _cell(self, lat, lon):
        # Cell sized to the walk radius so a 3x3 neighbourhood covers it.
        deg = self.max_walk_km / (EARTH_RADIUS_KM * math.pi / 180.0)
        return (int(lat / deg), int(lon / deg))

    def _build_walk_edges(self):
        """Undirected walk adjacency between car-graph spots within max_walk_km."""
        grid = {}
        for idx in self.car_spots:
            lat, lon = self.spots[idx]
            grid.setdefault(self._cell(lat, lon), []).append(idx)
        self._grid = grid

        walk_adj = {}
        for idx in self.car_spots:
            lat, lon = self.spots[idx]
            cy, cx = self._cell(lat, lon)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    for jdx in grid.get((cy + dy, cx + dx), ()):
                        if jdx <= idx:
                            continue
                        km = haversine_km(lat, lon, self.spots[jdx][0], self.spots[jdx][1])
                        if km <= self.max_walk_km:
                            walk_adj.setdefault(idx, []).append((jdx, km))
                            walk_adj.setdefault(jdx, []).append((idx, km))
        self.walk_adj = walk_adj

    def _spots_near(self, lat, lon):
        """Car-graph spots within max_walk_km of a point → [(spot_idx, km)]."""
        cy, cx = self._cell(lat, lon)
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for idx in self._grid.get((cy + dy, cx + dx), ()):
                    km = haversine_km(lat, lon, self.spots[idx][0], self.spots[idx][1])
                    if km <= self.max_walk_km:
                        out.append((idx, km))
        return out

    # -- querying -------------------------------------------------------------

    def route(self, start, dest):
        """Fastest single itinerary (found=False if none exists within walk limits)."""
        prev = self._search(start, dest, penalty=None)
        if prev is None:
            return {"found": False, "reason": "no spot within walking distance of origin and destination"}
        itin, _edges = self._itinerary(start, dest, prev)
        return itin

    def routes(self, start, dest, k=3, penalty=2.5, max_overlap=0.6, max_attempts=None):
        """Up to k fastest itineraries that are *sufficiently different* from each
        other, via the penalty method: find the fastest route, multiply the car
        edges it used by `penalty`, search again, and so on. A candidate is kept
        only if its shared car distance with every already-kept route is below
        `max_overlap` (as a fraction of the shorter route), so alternatives are
        genuinely distinct corridors (e.g. via Hannover vs via Hamburg) rather
        than trivial detours. Reported times are always the true (unpenalised)
        travel times.
        """
        if max_attempts is None:
            max_attempts = k * 8
        pen = {}
        kept = []          # itinerary dicts
        kept_edges = []    # (edge_set, car_km) per kept route
        for _ in range(max_attempts):
            if len(kept) >= k:
                break
            prev = self._search(start, dest, penalty=pen)
            if prev is None:
                break
            itin, edges = self._itinerary(start, dest, prev)
            car_km = itin["car_km"]

            # Push future searches off this path regardless of whether we keep it.
            for e in edges:
                pen[e] = pen.get(e, 1.0) * penalty

            too_similar = False
            for prev_edges, prev_km in kept_edges:
                shared = sum(self.edge_km[e] for e in edges & prev_edges)
                denom = min(car_km, prev_km) or 1.0
                if shared / denom >= max_overlap:
                    too_similar = True
                    break
            if too_similar:
                continue
            kept.append(itin)
            kept_edges.append((edges, car_km))

        for rank, itin in enumerate(kept):
            itin["rank"] = rank
        return kept

    def _wait(self, u, v):
        """Boarding wait (minutes) to catch a ride along car edge (u, v)."""
        w = self.edge_wait.get((u, v))
        return w if w is not None else self.default_wait

    def _search(self, start, dest, penalty=None):
        """Corridor-aware Dijkstra returning the predecessor map or None.

        A state is (spot, corridor) where corridor is the tree you are currently
        riding, or NO_TREE when on foot. Continuing the same corridor is free;
        *boarding* a car — the first ride, or switching to any other corridor at a
        shared spot — costs that edge's waiting time. So a route pays one wait per
        distinct ride, whether the ride change happens after a walk or by swapping
        cars mid-way.

        `penalty` optionally scales a car edge's travel time to push alternative
        searches onto different corridors; it never affects reported real times.
        """
        NO_TREE = -1
        walk_min = lambda km: km / WALK_SPEED_KMH * 60
        car_min = lambda km: km / CAR_SPEED_KMH * 60

        origin_spots = self._spots_near(*start)
        dest_spots = {idx: km for idx, km in self._spots_near(*dest)}

        dist = {}
        prev = {}  # state -> (pred_state_or_ORIGIN, kind, km, wait)
        pq = []
        # Reaching a spot from the origin is a walk, so we arrive on foot.
        for idx, km in origin_spots:
            st = (idx, NO_TREE)
            t = walk_min(km)
            if t < dist.get(st, math.inf):
                dist[st] = t
                prev[st] = (ORIGIN, "walk", km, 0.0)
                heapq.heappush(pq, (t, st))

        best_dest = math.inf
        direct_km = haversine_km(start[0], start[1], dest[0], dest[1])
        if direct_km <= self.max_walk_km:
            best_dest = walk_min(direct_km)
            prev[DEST] = (ORIGIN, "walk", direct_km, 0.0)

        def relax(nst, t, entry):
            if t < dist.get(nst, math.inf):
                dist[nst] = t
                prev[nst] = entry
                heapq.heappush(pq, (t, nst))

        while pq:
            d, st = heapq.heappop(pq)
            if d > dist.get(st, math.inf):
                continue
            if d >= best_dest:
                break
            spot, corridor = st
            # Continue the current ride along its corridor — no new wait.
            if corridor != NO_TREE:
                for v, km, _wait in self.tree_adj[corridor].get(spot, ()):
                    mult = penalty.get((spot, v), 1.0) if penalty else 1.0
                    relax((v, corridor), d + car_min(km) * mult, (st, "car", km, 0.0))
            # Board a car / switch corridors — costs the edge's waiting time.
            for t_id, v, km, wait in self.board.get(spot, ()):
                w = wait if wait is not None else self.default_wait
                mult = penalty.get((spot, v), 1.0) if penalty else 1.0
                relax((v, t_id), d + car_min(km) * mult + w, (st, "board", km, w))
            # Walk to a nearby spot (leaves you on foot).
            for v, km in self.walk_adj.get(spot, ()):
                relax((v, NO_TREE), d + walk_min(km), (st, "walk", km, 0.0))
            if spot in dest_spots:
                t = d + walk_min(dest_spots[spot])
                if t < best_dest:
                    best_dest = t
                    prev[DEST] = (st, "walk", dest_spots[spot], 0.0)

        return prev if best_dest != math.inf else None

    def _itinerary(self, start, dest, prev):
        def mark(node):
            # State (spot, corridor) -> spot index; ORIGIN/DEST pass through.
            return node if node in (ORIGIN, DEST) else node[0]

        def coord(m):
            if m == ORIGIN:
                return list(start)
            if m == DEST:
                return list(dest)
            return self.spots[m]

        # Reconstruct the raw step path (destination back to origin). kind is
        # "walk", "board" (start of a ride, carries its wait) or "car" (continuing
        # the same ride, free).
        raw = []  # (kind, from_mark, to_mark, km, wait)
        car_edges = set()  # (u, v) spot pairs, for overlap scoring
        node = DEST
        while node != ORIGIN:
            pred, kind, km, wait = prev[node]
            a, b = mark(pred), mark(node)
            raw.append((kind, a, b, km, wait))
            if kind in ("car", "board") and a >= 0 and b >= 0:
                car_edges.add((a, b))
            node = pred
        raw.reverse()

        # Group steps into legs. A car leg is one ride: it begins at a "board"
        # (which carries the ride's waiting time) and absorbs following "car"
        # continuations; a new "board" starts a new ride (car switch => new wait).
        legs = []
        for kind, a, b, km, wait in raw:
            mode = "walk" if kind == "walk" else "car"
            extend = legs and legs[-1]["mode"] == mode and kind != "board"
            if extend:
                leg = legs[-1]
                leg["km"] += km
                if b not in (ORIGIN, DEST):
                    leg["via"].append(self.spots[b])
                leg["to"] = coord(b)
            else:
                legs.append({
                    "mode": mode,
                    "from": coord(a),
                    "to": coord(b),
                    "km": km,
                    "via": [] if b in (ORIGIN, DEST) else [self.spots[b]],
                    "wait_minutes": round(wait, 1) if kind == "board" else 0.0,
                })
        for leg in legs:
            speed = WALK_SPEED_KMH if leg["mode"] == "walk" else CAR_SPEED_KMH
            leg["minutes"] = round(leg["km"] / speed * 60, 1)  # travel only
            leg["km"] = round(leg["km"], 3)
            leg["via"] = leg["via"][:-1]  # last via == leg["to"]

        walk_km = sum(leg["km"] for leg in legs if leg["mode"] == "walk")
        car_km = sum(leg["km"] for leg in legs if leg["mode"] == "car")
        wait_min = sum(leg["wait_minutes"] for leg in legs)
        # True total time = travel + waiting (penalised search must not inflate it).
        total_min = sum(leg["minutes"] for leg in legs) + wait_min
        itin = {
            "found": True,
            "total_minutes": round(total_min, 1),
            "wait_minutes": round(wait_min, 1),
            "walk_km": round(walk_km, 2),
            "car_km": round(car_km, 2),
            "num_car_legs": sum(1 for leg in legs if leg["mode"] == "car"),
            "legs": legs,
        }
        return itin, car_edges


def load_router(path=None, max_walk_km=DEFAULT_MAX_WALK_KM):
    if path is None:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        path = os.path.join(root, "dist", "repeatable_routes.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return RepeatableRouter(data, max_walk_km=max_walk_km)


def _parse_latlon(s):
    lat, lon = s.split(",")
    return (float(lat), float(lon))


def main():
    ap = argparse.ArgumentParser(description="Route over repeatable hitchhiking routes.")
    ap.add_argument("--from", dest="start", required=True, type=_parse_latlon, help="lat,lon")
    ap.add_argument("--to", dest="dest", required=True, type=_parse_latlon, help="lat,lon")
    ap.add_argument("--max-walk-km", type=float, default=DEFAULT_MAX_WALK_KM)
    ap.add_argument("--k", type=int, default=3, help="number of diverse alternatives to show")
    ap.add_argument("--max-overlap", type=float, default=0.6, help="max shared car distance between alternatives (0-1)")
    ap.add_argument("--data", default=None, help="path to repeatable_routes.json")
    args = ap.parse_args()

    router = load_router(args.data, max_walk_km=args.max_walk_km)
    print(f"Graph: {len(router.car_spots)} car-graph spots, {len(router.edge_km)} car edges, "
          f"{len(router.tree_adj)} corridors")
    alts = router.routes(args.start, args.dest, k=args.k, max_overlap=args.max_overlap)
    if not alts:
        print("No route within walking distance of origin and destination.")
        return
    for itin in alts:
        h, m = divmod(int(itin["total_minutes"]), 60)
        # Name the route by the biggest spot it passes (rough "via" hint = midpoint spot).
        car_legs = [leg for leg in itin["legs"] if leg["mode"] == "car"]
        mid = ""
        if car_legs and car_legs[0]["via"]:
            v = car_legs[0]["via"][len(car_legs[0]["via"]) // 2]
            mid = f"  ~via {v[0]:.2f},{v[1]:.2f}"
        print(f"\nOption {itin['rank'] + 1}: {h}h{m:02d}m  ({itin['car_km']} km car, {itin['walk_km']} km walk, "
              f"{itin['num_car_legs']} car leg(s), {itin['wait_minutes']:.0f} min waiting){mid}")
        for leg in itin["legs"]:
            icon = "🚶" if leg["mode"] == "walk" else "🚗"
            via = f" via {len(leg['via'])} spots" if leg["via"] else ""
            wait = f" +{leg['wait_minutes']:.0f}m wait" if leg["mode"] == "car" else ""
            print(f"  {icon} {leg['mode']:4} {leg['km']:7.2f} km  {leg['minutes']:6.1f} min{wait}  "
                  f"{leg['from'][0]:.5f},{leg['from'][1]:.5f} -> {leg['to'][0]:.5f},{leg['to'][1]:.5f}{via}")


if __name__ == "__main__":
    main()
