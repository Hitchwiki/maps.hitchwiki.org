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
  const api = { kindOf, fallback, overpassQuery };
  if (typeof module !== "undefined") module.exports = api; else root.RGFallback = api;
})(typeof window !== "undefined" ? window : this);
