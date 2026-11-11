// #1388: pick the start city's Hitchwiki "<direction> towards ..." section that faces the destination.
// Pure functions. cities: [{title, la, lo, h: ["Northwest towards Hamburg", ...]}] (wiki_exits.json).
(function (root) {
  const R = Math.PI / 180;
  const DIR = { north: 0, northeast: 45, east: 90, southeast: 135, south: 180, southwest: 225, west: 270, northwest: 315 };
  function km(a, b) {
    const s = Math.sin((b[0]-a[0])*R/2)**2 + Math.cos(a[0]*R)*Math.cos(b[0]*R)*Math.sin((b[1]-a[1])*R/2)**2;
    return 12742 * Math.asin(Math.sqrt(s));
  }
  function bearing(a, b) {
    const y = Math.sin((b[1]-a[1])*R) * Math.cos(b[0]*R);
    const x = Math.cos(a[0]*R)*Math.sin(b[0]*R) - Math.sin(a[0]*R)*Math.cos(b[0]*R)*Math.cos((b[1]-a[1])*R);
    return (Math.atan2(y, x) / R + 360) % 360;
  }
  // Compass angles named before "toward(s)" in a heading, e.g. "East, South towards X" -> [90, 180].
  function headingAngles(h) {
    const head = h.split(/toward|→/i)[0].toLowerCase();
    const out = [];
    (head.match(/north-?east|north-?west|south-?east|south-?west|north|south|east|west/g) || []).forEach((w) => {
      const k = w.replace("-", "");
      if (k in DIR) out.push(DIR[k]);
    });
    return out;
  }
  function angDiff(a, b) { const d = Math.abs(a - b) % 360; return d > 180 ? 360 - d : d; }
  // Returns {title, heading, anchor, url} or null. Start must be within maxKm of an indexed city.
  function pick(cities, from, to, maxKm) {
    let best = null, bd = (maxKm || 12) + 1e-9;
    for (const c of cities) { const d = km(from, [c.la, c.lo]); if (d < bd) { bd = d; best = c; } }
    if (!best) return null;
    const b = bearing(from, to);
    let hit = null, hd = 40;
    for (const h of best.h) {
      for (const a of headingAngles(h)) { const d = angDiff(a, b); if (d < hd) { hd = d; hit = h; } }
    }
    if (!hit) return null;
    const anchor = hit.replace(/\s+/g, "_");
    return { title: best.title, heading: hit, anchor: anchor,
      url: "https://hitchwiki.org/en/" + encodeURIComponent(best.title.replace(/ /g, "_")) + "#" + encodeURIComponent(anchor) };
  }
  const api = { pick: pick, headingAngles: headingAngles, bearing: bearing };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.WikiExit = api;
})(typeof window !== "undefined" ? window : this);
