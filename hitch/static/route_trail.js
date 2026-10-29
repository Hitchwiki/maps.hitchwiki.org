// Local-only live route trail for the in-ride state (maps#471). Draws where the
// rider has been on the map while a ride is in progress. Nothing is sent anywhere:
// points live in memory and in localStorage until the journey ends, then are wiped.
// Starts only if location permission was already granted, so it never prompts.
// Browser: window.RouteTrail; Node: module.exports (same shape as ride_submit.js).
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = mod;
  else root.RouteTrail = mod;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const KEY = "route_trail_v1";
  const MIN_STEP_M = 50;
  const MAX_POINTS = 500;

  function distM(a, b) {
    const R = 6371000, rad = Math.PI / 180;
    const dLat = (b[0] - a[0]) * rad, dLon = (b[1] - a[1]) * rad;
    const h = Math.sin(dLat / 2) ** 2 +
      Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  // Append a fix if it is >= MIN_STEP_M from the last point; cap length by dropping
  // every second point of the older half so the whole trip stays represented.
  function addPoint(points, p) {
    if (!p || !isFinite(p[0]) || !isFinite(p[1])) return false;
    if (points.length && distM(points[points.length - 1], p) < MIN_STEP_M) return false;
    points.push(p);
    if (points.length > MAX_POINTS) {
      const half = points.length >> 1;
      const thinned = points.slice(0, half).filter((_, i) => i % 2 === 0);
      points.splice(0, half, ...thinned);
    }
    return true;
  }

  // Pick up to `max` points along a finished trail to offer as "towns you passed".
  // Needs a real trip (>= 10 points, >= 20 km); the first and last 5 km are excluded
  // so neither the pickup nor the drop-off area is echoed back. Evenly spaced by distance.
  function pickStopCandidates(points, max) {
    max = max || 4;
    if (!Array.isArray(points) || points.length < 10) return [];
    const cum = [0];
    for (let i = 1; i < points.length; i++) cum.push(cum[i - 1] + distM(points[i - 1], points[i]));
    const total = cum[cum.length - 1];
    if (total < 20000) return [];
    const lo = 5000, hi = total - 5000;
    const out = [];
    for (let k = 1; k <= max; k++) {
      const target = lo + ((hi - lo) * k) / (max + 1);
      let best = -1, bestD = Infinity;
      for (let i = 0; i < points.length; i++) {
        if (cum[i] < lo || cum[i] > hi) continue;
        const d = Math.abs(cum[i] - target);
        if (d < bestD) { bestD = d; best = i; }
      }
      if (best >= 0 && !out.some((p) => p === points[best])) out.push(points[best]);
    }
    return out;
  }

  function load(storage) {
    try {
      const v = JSON.parse((storage && storage.getItem(KEY)) || "[]");
      return Array.isArray(v) ? v : [];
    } catch (e) { return []; }
  }

  function clear(storage) {
    try { storage && storage.removeItem(KEY); } catch (e) {}
  }

  // env: { L, map, geo (navigator.geolocation), permissions (navigator.permissions),
  //        storage (localStorage) }. Returns a handle with stop().
  function start(env) {
    const handle = { stop() {}, points: [] };
    if (!env || !env.L || !env.map || !env.geo || !env.permissions) return handle;
    let stopped = false, watchId = null, line = null;
    handle.stop = function (keepStored) {
      stopped = true;
      if (watchId != null) env.geo.clearWatch(watchId);
      watchId = null;
      if (line) env.map.removeLayer(line);
      line = null;
      handle.points.length = 0;
      if (!keepStored) clear(env.storage);
    };
    env.permissions.query({ name: "geolocation" }).then(function (st) {
      if (stopped || !st || st.state !== "granted") return;
      try {
        const saved = JSON.parse((env.storage && env.storage.getItem(KEY)) || "[]");
        if (Array.isArray(saved)) handle.points.push(...saved);
      } catch (e) {}
      line = env.L.polyline(handle.points, { color: "#ff6b35", weight: 4, opacity: 0.8 }).addTo(env.map);
      watchId = env.geo.watchPosition(function (pos) {
        if (stopped) return;
        const c = pos && pos.coords;
        if (!c || (c.accuracy != null && c.accuracy > 200)) return;
        if (!addPoint(handle.points, [c.latitude, c.longitude])) return;
        line.setLatLngs(handle.points);
        try { env.storage && env.storage.setItem(KEY, JSON.stringify(handle.points)); } catch (e) {}
      }, function () {}, { enableHighAccuracy: false, maximumAge: 30000, timeout: 60000 });
    }, function () {});
    return handle;
  }

  return { start, clear, load, pickStopCandidates, addPoint, distM, KEY, MIN_STEP_M, MAX_POINTS };
});
