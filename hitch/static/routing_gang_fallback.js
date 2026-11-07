// Routing-gang fallback: where no hitchhiking spot is logged near an end of the trip, offer the
// OSM place (fuel station, rest area, motorway junction) nearest that end along the road route.
(function (root) {
  const KIND = { fuel: "fuel station", services: "service area", rest_area: "rest area", motorway_junction: "motorway junction" };
  function kindOf(tags) {
    if (tags.amenity === "fuel") return "fuel";
    if (tags.highway && KIND[tags.highway]) return tags.highway;
    return null;
  }
  // elements: Overpass `out center` elements; near: RGChain.nearRoute-style helper not needed,
  // we measure against the densified route (line, cum) with maxOff km.
  function fallback(elements, line, cum, maxOff, km) {
    let best = null;
    for (const e of elements) {
      const k = kindOf(e.tags || {});
      const lat = e.lat !== undefined ? e.lat : e.center && e.center.lat;
      const lon = e.lon !== undefined ? e.lon : e.center && e.center.lon;
      if (!k || lat === undefined) continue;
      let off = 1e9, at = 0;
      for (let i = 0; i < line.length; i++) {
        const d = km([lat, lon], line[i]);
        if (d < off) { off = d; at = cum[i]; }
      }
      if (off > maxOff) continue;
      if (!best || at < best.at) best = { lat, lon, kind: k, label: KIND[k] + " (OSM), no rides logged yet", off, at };
    }
    return best;
  }
  function overpassQuery(lat, lon, radiusM) {
    const r = `(around:${radiusM},${lat},${lon})`;
    return `[out:json][timeout:40];(node${r}[amenity=fuel];node${r}[highway=motorway_junction];` +
      `nwr${r}[highway=services];nwr${r}[highway=rest_area];);out center 200;`;
  }
  // Static tiles (scripts/build_osm_stop_tiles.py) stand in for public Overpass, which times out (EXP-1114).
  // Tile coverage: lat 32..79, lon -31..47 (the pull behind the files). Outside it callers fall back to Overpass.
  const TILE_BOX = { s: 32, n: 79, w: -31, e: 47 };
  function tileKeys(pts, padDeg) {
    const keys = new Set();
    for (const p of pts) {
      for (const la of [p[0] - padDeg, p[0] + padDeg]) for (const lo of [p[1] - padDeg, p[1] + padDeg]) {
        keys.add(Math.floor(la) + "_" + Math.floor(lo));
      }
    }
    return [...keys];
  }
  function inCoverage(pts) {
    return pts.every(p => p[0] >= TILE_BOX.s && p[0] <= TILE_BOX.n && p[1] >= TILE_BOX.w && p[1] <= TILE_BOX.e);
  }
  const TAGS = { f: { amenity: "fuel" }, j: { highway: "motorway_junction" }, s: { highway: "services" }, r: { highway: "rest_area" } };
  // tiles: arrays of [cls, lat, lon, name]; keeps stops within padDeg (lat/lon box) of any pt; returns Overpass-shaped nodes.
  function tileElements(tiles, pts, padDeg) {
    const cell = 0.01, pad = Math.ceil(padDeg / cell);
    const have = new Set();
    for (const p of pts) {
      const ci = Math.floor(p[0] / cell), cj = Math.floor(p[1] / cell);
      for (let i = -pad; i <= pad; i++) for (let j = -pad; j <= pad; j++) have.add((ci + i) + "," + (cj + j));
    }
    const out = [];
    let n = 0;
    for (const t of tiles) for (const r of t) {
      if (!have.has(Math.floor(r[1] / cell) + "," + Math.floor(r[2] / cell))) continue;
      const tags = Object.assign({}, TAGS[r[0]]);
      if (r[3]) tags.name = r[3];
      out.push({ type: "node", id: "t" + (n++), lat: r[1], lon: r[2], tags });
    }
    return out;
  }
  const api = { kindOf, fallback, overpassQuery, tileKeys, inCoverage, tileElements };
  if (typeof module !== "undefined") module.exports = api; else root.RGFallback = api;
})(typeof window !== "undefined" ? window : this);
