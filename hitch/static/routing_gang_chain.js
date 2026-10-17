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
    let ok = 0;
    for (let i = 0; i < n; i++) {
      const d = [s.dest_lats[i], s.dest_lons[i]];
      let diff = Math.abs(bearing(p, d) - brg); if (diff > 180) diff = 360 - diff;
      if (diff <= 45 && km(d, b) < dB) ok++;
    }
    return { share: ok / n, n, ok };
  }
  // A stop counts as evidenced when at least MIN_EVIDENCE logged rides from it went toward B.
  const MIN_EVIDENCE = 3;
  function score(s, t) {
    return (t.share || 0) * 3 + Math.min(s.review_count || 0, 10) / 10 + (s.rating || 0) / 10;
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
  // New: departure spot = best-scoring spot within 15 km of A; then the best one in each
  // 20-80 km window along the route; the rest is a hop to B, or a flagged gap.
  function newChain(a, b, near, routeKm) {
    const chain = [];
    const score_ = (c) => { c.t = toward(c.s, b); c.weak = c.t.ok < MIN_EVIDENCE; c.score = score(c.s, c.t) - (c.weak ? 10 : 0); return c; };
    near.forEach(score_);
    // First stop: prefer spots close to A (-0.2 score per km); a spot 14 km out used to win on score alone.
    const fscore = (c) => c.score - 0.2 * km(a, [c.s.lat, c.s.lon]);
    const first = near.filter(c => km(a, [c.s.lat, c.s.lon]) <= 15).sort((x, y) => fscore(y) - fscore(x))[0];
    let pos = first ? first.at : 0;
    if (first) chain.push(first);
    for (let guard = 0; guard < 60 && routeKm - pos > 80; guard++) {
      const win = near.filter(c => c.at >= pos + 20 && c.at <= pos + 80).sort((x, y) => y.score - x.score)[0];
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
  const api = { MIN_EVIDENCE, km, bearing, toward, score, densify, nearRoute, oldChain, newChain, driverList };
  if (typeof module !== "undefined") module.exports = api; else root.RGChain = api;
})(typeof window !== "undefined" ? window : this);
