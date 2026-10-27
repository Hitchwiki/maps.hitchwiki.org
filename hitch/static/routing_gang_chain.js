// Spot chain for the routing-gang test page. Pure functions, no DOM: used by
// templates/routing_gang.html and by scripts/routing_gang_firstspot_eval.js.
// spots: [{lat, lon, rating, review_count, latest_ms, dest_lats, dest_lons}] (/spots.json)
(function (root) {
  const R = Math.PI / 180;
  function km(a, b) {
    const s = Math.sin((b[0]-a[0])*R/2)**2 + Math.cos(a[0]*R)*Math.cos(b[0]*R)*Math.sin((b[1]-a[1])*R/2)**2;
    return 12742 * Math.asin(Math.sqrt(s));
  }
  function bearing(a, b) {
    const y = Math.sin((b[1]-a[1])*R) * Math.cos(b[0]*R);
    const x = Math.cos(a[0]*R)*Math.sin(b[0]*R) - Math.sin(a[0]*R)*Math.cos(b[0]*R)*Math.cos((b[1]-a[1])*R);
    return (Math.atan2(y, x) / R + 360) % 360;
  }
  // Share of this spot's logged destinations that lie toward B: within 45 degrees of
  // the spot->B bearing and closer to B than the spot is. null if no destinations logged.
  function toward(s, b) {
    const n = (s.dest_lats || []).length;
    if (!n) return { share: null, n: 0, ok: 0 };
    const p = [s.lat, s.lon], brg = bearing(p, b), dB = km(p, b);
    let ok = 0; const kms = [];
    for (let i = 0; i < n; i++) {
      const d = [s.dest_lats[i], s.dest_lons[i]];
      let diff = Math.abs(bearing(p, d) - brg); if (diff > 180) diff = 360 - diff;
      if (diff <= 45 && km(d, b) < dB) { ok++; kms.push(km(p, d)); }
    }
    kms.sort((x, y) => x - y);
    // medKm: median distance of the rides that went toward B (null if none)
    return { share: ok / n, n, ok, medKm: ok ? kms[Math.floor(ok / 2)] : null };
  }
  // A stop counts as evidenced when at least MIN_EVIDENCE logged rides from it went toward B.
  const MIN_EVIDENCE = 3;
  // Rides from fuel/rest-area spots go a median 55 km vs 24 km from town spots (621 riders: 1.7x as far for the
  // same people, 20 vs 15 min wait), so a fuel spot gets a modest bonus; evidence toward B still dominates (x3).
  const FUEL_BONUS = 0.5;
  function score(s, t) {
    return (t.share || 0) * 3 + Math.min(s.review_count || 0, 10) / 10 + (s.rating || 0) / 10 + (s.fuel ? FUEL_BONUS : 0);
  }
  // Densify a polyline to ~2 km steps; returns [points, cumulative km at each point].
  function densify(raw) {
    const line = [raw[0]], cum = [0];
    for (let i = 1; i < raw.length; i++) {
      const seg = km(raw[i-1], raw[i]), n = Math.max(1, Math.ceil(seg / 2));
      for (let k = 1; k <= n; k++) {
        line.push([raw[i-1][0] + (raw[i][0]-raw[i-1][0])*k/n, raw[i-1][1] + (raw[i][1]-raw[i-1][1])*k/n]);
        cum.push(cum[cum.length-1] + seg / n);
      }
    }
    return [line, cum];
  }
  // Spots within maxOff km of the route, each with its distance along the route.
  function nearRoute(spots, line, cum, maxOff) {
    const out = [];
    for (const s of spots) {
      let best = 1e9, bi = -1;
      const p = [s.lat, s.lon];
      for (let i = 0; i < line.length; i++) {
        const d = km(p, line[i]);
        if (d < best) { best = d; bi = i; }
      }
      if (best <= maxOff) out.push({ s, off: best, at: cum[bi] });
    }
    return out.sort((x, y) => x.at - y.at);
  }
  // Old behaviour (step 2): first spot along the route >= 10 km from A, then every >= 10 km.
  function oldChain(a, b, near) {
    const chain = [], last = [a];
    for (const c of near) {
      const p = [c.s.lat, c.s.lon];
      if (km(last[last.length-1], p) >= 10) { chain.push(c); last.push(p); }
    }
    return chain;
  }
  // Riders dropped within 5 km of a city centre needed a median 1.91 km to reach their next pickup (42% over 3 km),
  // against 0.1 km elsewhere (n=899 transfers), so a mid-route stop in a city is penalised. cities: [[lat, lon], ...].
  const CITY_PENALTY = 10, CITY_KM = 5;
  function nearCity(s, cities) {
    if (!cities) return false;
    for (const c of cities) {
      if (Math.abs(c[0] - s.lat) > 0.05 || Math.abs(c[1] - s.lon) > 0.08) continue;
      if (km([s.lat, s.lon], c) < CITY_KM) return true;
    }
    return false;
  }
  // New: departure spot = best-scoring spot within 15 km of A; then the best one in each
  // 20-80 km window along the route; the rest is a hop to B, or a flagged gap.
  // forceFirst (optional): a near-route entry the rider picked as their start instead of the best one.
  function newChain(a, b, near, routeKm, cities, forceFirst) {
    const chain = [];
    const score_ = (c) => { c.t = toward(c.s, b); c.weak = c.t.ok < MIN_EVIDENCE; c.score = score(c.s, c.t) - (c.weak ? 10 : 0); c.wscore = c.score - (nearCity(c.s, cities) ? CITY_PENALTY : 0); return c; };
    near.forEach(score_);
    // The city penalty (wscore) applies to mid-route windows only: a city start must keep its nearby first stop.
    // First stop: prefer spots close to A (-0.2 score per km); a spot 14 km out used to win on score alone.
    const fscore = (c) => c.score - 0.2 * km(a, [c.s.lat, c.s.lon]);
    const first = forceFirst || near.filter(c => km(a, [c.s.lat, c.s.lon]) <= 15).sort((x, y) => fscore(y) - fscore(x))[0];
    let pos = first ? first.at : 0;
    if (first) chain.push(first);
    // No spot within 15 km of A and a short route (<= 80 km): the loop below adds nothing, so the page
    // showed zero stops. Suggest the best-scoring spot in the first half of the route instead (flagged weak if so).
    if (!first && near.length) {
      const firstHalf = near.filter(c => c.at <= routeKm / 2);
      const early = (firstHalf.length ? firstHalf : near).sort((x, y) => fscore(y) - fscore(x))[0];
      if (early) { chain.push(early); pos = early.at; }
    }
    for (let guard = 0; guard < 60 && routeKm - pos > 80; guard++) {
      const win = near.filter(c => c.at >= pos + 20 && c.at <= pos + 80).sort((x, y) => y.wscore - x.wscore)[0];
      if (win) { chain.push(win); pos = win.at; continue; }
      const next = near.find(c => c.at > pos + 80);
      if (!next) break;
      next.gapBefore = true; chain.push(next); pos = next.at;
    }
    return chain;
  }
  // Driver view: spots within maxOff km of the car route, newest ride first, with the detour
  // (there and back) a driver would add by stopping there.
  function driverList(near, nowMs, maxOff) {
    return near.filter(c => c.off <= maxOff)
      .map(c => ({ s: c.s, at: c.at, detour: 2 * c.off, ageDays: c.s.latest_ms ? Math.max(0, (nowMs - c.s.latest_ms) / 864e5) : null }))
      .sort((x, y) => (x.ageDays === null) - (y.ageDays === null) || x.ageDays - y.ageDays);
  }
  // Detour waypoint for a forced alternative: an evidenced spot (>= MIN_EVIDENCE rides toward B) in the
  // middle part of the route that lies 15-80 km off the main road, the one with most rides toward B.
  function pickVia(spots, a, b, line, cum) {
    const total = cum[cum.length - 1];
    let best = null;
    for (const s of spots) {
      const t = toward(s, b);
      if (t.ok < MIN_EVIDENCE) continue;
      let off = 1e9, at = 0;
      for (let i = 0; i < line.length; i++) { const d = km([s.lat, s.lon], line[i]); if (d < off) { off = d; at = cum[i]; } }
      if (off < 15 || off > 80 || at < total * 0.25 || at > total * 0.75) continue;
      const v = t.ok - off / 20;
      if (!best || v > best.v) best = { s, off, at, v, ok: t.ok };
    }
    return best;
  }
  // "The way other riders went": BFS over logged legs [lat, lon, dest_lat, dest_lon] on 0.1-degree cells, <= 6 hops,
  // from A's cell (or a neighbour) to B's. Returns the polyline [A, leg origin, leg dest, ..., B] and its length, or null.
  const cellOf = (la, lo) => [Math.round(la / 0.1), Math.round(lo / 0.1)];
  const ck = (c) => c[0] + "," + c[1];
  function ridersPath(legs, a, b, maxHops) {
    const edges = new Map();
    for (const l of legs) {
      const x = cellOf(l[0], l[1]), y = cellOf(l[2], l[3]);
      if (ck(x) === ck(y)) continue;
      const k = ck(x); if (!edges.has(k)) edges.set(k, []);
      edges.get(k).push({ y: ck(y), o: [l[0], l[1]], d: [l[2], l[3]], len: km([l[0], l[1]], [l[2], l[3]]) });
    }
    const nb = (c) => { const r = []; for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) r.push((c[0] + i) + "," + (c[1] + j)); return r; };
    const goal = new Set(nb(cellOf(b[0], b[1]))), start = ck(cellOf(a[0], a[1]));
    const seen = new Map([[start, null]]); let q = [start], found = null;
    for (let h = 0; h < (maxHops || 6) && !found; h++) {
      const nq = [];
      for (const x of q) {
        for (const sx of nb(x.split(",").map(Number))) for (const e of (edges.get(sx) || [])) {
          if (seen.has(e.y)) continue;
          seen.set(e.y, { from: x, e });
          if (goal.has(e.y)) { found = e.y; break; }
          nq.push(e.y);
        }
        if (found) break;
      }
      q = nq;
    }
    if (!found) return null;
    let pts = [], total = 0, z = found;
    while (seen.get(z)) { const { from, e } = seen.get(z); pts = [e.o, e.d].concat(pts); total += e.len; z = from; }
    return { pts: [a].concat(pts, [b]), km: total };
  }
  // Usable as a second route: <= 1.3x the fastest road length and >= 20% of the path more than 3 km from the fastest road.
  function ridersUsable(path, fastLine, fastKm) {
    if (!path || path.km > 1.3 * fastKm) return false;
    const [dl] = densify(path.pts);
    let off = 0;
    for (const p of dl) { let near = false; for (const q of fastLine) if (km(p, q) <= 3) { near = true; break; } if (!near) off++; }
    return off / dl.length >= 0.2;
  }

  // Start options: the best departure spots within 15 km of A (same ranking as newChain's first stop),
  // at least 1 km apart, best first. The first one is the start newChain picks.
  function startOptions(a, b, near, n) {
    const out = [];
    const cand = near.filter(c => km(a, [c.s.lat, c.s.lon]) <= 15).map(c => {
      const t = c.t || toward(c.s, b), weak = t.ok < MIN_EVIDENCE;
      return { c, v: score(c.s, t) - (weak ? 10 : 0) - 0.2 * km(a, [c.s.lat, c.s.lon]) };
    }).sort((x, y) => y.v - x.v);
    for (const x of cand) {
      if (out.some(o => km([o.s.lat, o.s.lon], [x.c.s.lat, x.c.s.lon]) < 1)) continue;
      out.push(x.c);
      if (out.length >= (n || 3)) break;
    }
    return out;
  }
  // Trip time model. Driving = the car route's duration spread evenly over its km; one wait per ride.
  // A ride is assumed at every suggested stop, plus one per further ~60 km of a long leg (the median hop).
  // waitAt(lat, lon) -> logged area median wait in minutes, or null (then the global median, 20 min).
  // Spread: logged same-day trips took x0.8-1.6 of this estimate in 60% of cases, x0.7-2.0 in 78%
  // (1,094 trips, research/routing-door-to-door-time-2026-10-16.md), so it is shown as a range, never one number.
  const HOP_KM = 60, GLOBAL_WAIT = 20, FAST = 0.8, SLOW = 1.6;
  function timeModel(chain, routeKm, durMin, waitAt) {
    const perKm = routeKm > 0 ? durMin / routeKm : 0;
    const w = (lat, lon) => { const v = waitAt ? waitAt(lat, lon) : null; return v == null ? GLOBAL_WAIT : v; };
    const waits = []; // {at km, min}
    let prev = 0, prevPt = null;
    chain.forEach(c => {
      const extra = Math.max(0, Math.round((c.at - prev) / HOP_KM) - 1);
      for (let k = 1; k <= extra; k++) waits.push({ at: prev + (c.at - prev) * k / (extra + 1), min: GLOBAL_WAIT });
      waits.push({ at: c.at, min: w(c.s.lat, c.s.lon), stop: c });
      prev = c.at; prevPt = c;
    });
    if (!chain.length) waits.push({ at: 0, min: GLOBAL_WAIT });
    const tail = Math.max(0, Math.round((routeKm - prev) / HOP_KM) - 1);
    for (let k = 1; k <= tail; k++) waits.push({ at: prev + (routeKm - prev) * k / (tail + 1), min: GLOBAL_WAIT });
    waits.sort((x, y) => x.at - y.at);
    // Piecewise-linear km -> minutes: [[km, min before waiting], [km, min after waiting], ...].
    const pts = [[0, 0]];
    let t = 0, last = 0;
    for (const x of waits) { t += (x.at - last) * perKm; pts.push([x.at, t]); t += x.min; pts.push([x.at, t]); last = x.at; }
    t += (routeKm - last) * perKm; pts.push([routeKm, t]);
    return { pts, total: t, rides: waits.length, waits, lo: t * FAST, hi: t * SLOW };
  }
  // Model minutes at a given km, and km reached after `min` model minutes (the inverse).
  function minAt(model, at) {
    const p = model.pts;
    for (let i = 1; i < p.length; i++) if (p[i][0] >= at && p[i][0] > p[i - 1][0]) return p[i - 1][1] + (p[i][1] - p[i - 1][1]) * (at - p[i - 1][0]) / (p[i][0] - p[i - 1][0]);
    return at <= 0 ? 0 : p[p.length - 1][1];
  }
  function kmAt(model, min) {
    const p = model.pts;
    if (min <= 0) return 0;
    for (let i = 1; i < p.length; i++) {
      if (p[i][1] < min) continue;
      if (p[i][0] === p[i - 1][0]) return p[i][0]; // still waiting at this stop
      return p[i - 1][0] + (p[i][0] - p[i - 1][0]) * (min - p[i - 1][1]) / (p[i][1] - p[i - 1][1]);
    }
    return p[p.length - 1][0];
  }
  // How far a rider gets in `avail` minutes: likely (slow day) and possible (good day) km along the route.
  function reach(model, avail) {
    return { likely: kmAt(model, avail / SLOW), possible: kmAt(model, avail / FAST) };
  }
  // Sunset (UTC ms) for a date at lat/lon: NOAA low-precision solar formula, about +-2 min.
  // Polar day -> null with polar=day; polar night -> null with polar=night.
  function sunset(lat, lon, dateMs) {
    const d = new Date(dateMs), y0 = Date.UTC(d.getUTCFullYear(), 0, 1);
    const day0 = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
    const g = 2 * Math.PI / 365 * ((day0 - y0) / 864e5);
    const eq = 229.18 * (0.000075 + 0.001868 * Math.cos(g) - 0.032077 * Math.sin(g) - 0.014615 * Math.cos(2 * g) - 0.040849 * Math.sin(2 * g));
    const dec = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g) - 0.006758 * Math.cos(2 * g) + 0.000907 * Math.sin(2 * g) - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);
    const c = Math.cos(90.833 * R) / (Math.cos(lat * R) * Math.cos(dec)) - Math.tan(lat * R) * Math.tan(dec);
    if (c < -1) return { ms: null, polar: "day" };
    if (c > 1) return { ms: null, polar: "night" };
    const ha = Math.acos(c) / R;
    return { ms: day0 + (720 + 4 * (ha - lon) - eq) * 6e4, polar: null };
  }
  // Point and index on a densified line at km `at`.
  function pointAt(line, cum, at) {
    const i = cum.findIndex(c => c >= at);
    if (i <= 0) return { p: i === 0 ? line[0] : line[line.length - 1], i: i < 0 ? line.length - 1 : 0 };
    const f = cum[i] > cum[i - 1] ? (at - cum[i - 1]) / (cum[i] - cum[i - 1]) : 1;
    return { p: [line[i - 1][0] + f * (line[i][0] - line[i - 1][0]), line[i - 1][1] + f * (line[i][1] - line[i - 1][1])], i };
  }
  // Sub-line of a densified line between km `from` and `to` (for colouring and clicking route stretches).
  function slice(line, cum, from, to) {
    const a = pointAt(line, cum, from), b = pointAt(line, cum, to);
    const out = [a.p];
    for (let i = a.i; i < b.i; i++) out.push(line[i]);
    out.push(b.p);
    return out;
  }
  // Share of line a's points within `tol` km of line b (both densified): drops alternatives that are the same road.
  function overlap(a, b, tol) {
    let n = 0;
    for (const p of a) { for (const q of b) if (Math.abs(p[0] - q[0]) < 0.05 && km(p, q) <= (tol || 1)) { n++; break; } }
    return a.length ? n / a.length : 0;
  }
  const api = { overlap, startOptions, timeModel, minAt, kmAt, reach, sunset, pointAt, slice, HOP_KM, GLOBAL_WAIT, FAST, SLOW, ridersPath, ridersUsable, pickVia, MIN_EVIDENCE, km, bearing, toward, score, densify, nearRoute, oldChain, newChain, driverList };
  if (typeof module !== "undefined") module.exports = api; else root.RGChain = api;
})(typeof window !== "undefined" ? window : this);
