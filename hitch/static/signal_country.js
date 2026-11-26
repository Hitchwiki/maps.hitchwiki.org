// maps#732: in Kazakhstan and Kyrgyzstan drivers are flagged with a palm-down hand wave, not a
// thumb, so the "thumb" signal chip is labelled "🫳 Hand wave" when the pickup lies there. Only the
// label changes: the stored code stays "thumb", so stats and filters are unaffected.
// Browser: window.SignalCountry; Node: module.exports (same dual-export as safety_stats.js).
(function () {
  const HAND_WAVE = new Set(["KZ", "KG"]);
  // Bounding box around KZ+KG together. Outside it no lookup runs, so the ~250 KB countries.geojson
  // is fetched only for pickups that might actually be in one of these two countries.
  const BOX = { s: 39.1, n: 55.5, w: 46.4, e: 87.4 };
  let geoPromise = null;

  function ptInRing(lat, lon, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  function countryCodeIn(geo, lat, lon) {
    for (const f of (geo && geo.features) || []) {
      const g = f.geometry; if (!g) continue;
      const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
      for (const poly of polys) {
        if (ptInRing(lat, lon, poly[0]) && !poly.slice(1).some((h) => ptInRing(lat, lon, h))) return (f.properties && f.properties.cc) || null;
      }
    }
    return null;
  }
  function inBox(lat, lon) {
    return lat >= BOX.s && lat <= BOX.n && lon >= BOX.w && lon <= BOX.e;
  }
  // Resolves true/false and never rejects: a failed lookup keeps the plain thumb label.
  function isHandWaveAt(lat, lon, fetchGeo) {
    lat = Number(lat); lon = Number(lon);
    if (!isFinite(lat) || !isFinite(lon) || !inBox(lat, lon)) return Promise.resolve(false);
    if (!geoPromise) {
      geoPromise = (fetchGeo || (() => fetch("/static/countries.geojson").then((r) => r.json())))()
        .catch(() => { geoPromise = null; return null; });
    }
    return geoPromise.then((geo) => HAND_WAVE.has(countryCodeIn(geo, lat, lon))).catch(() => false);
  }
  const api = { HAND_WAVE, countryCodeIn, inBox, isHandWaveAt };
  if (typeof window !== "undefined") window.SignalCountry = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
