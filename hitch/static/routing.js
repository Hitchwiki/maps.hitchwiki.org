/* Hitchhiking route planner for the main map.
 *
 * Self-contained: ports the corridor-aware routing engine (see
 * hitch/scripts/repeatable_router.py) into the browser, and drives a
 * Google-Maps-style start/destination UI that transforms the search bar.
 *
 * Relies on globals from map.js: `map` (the Leaflet map), `markerCluster`
 * (the spot cluster), `setSpotsVisible`, and `getMapMode`.
 */
(function () {
  "use strict";

  // ---- engine constants --------------------------------------------------
  const WALK_KMH = 5, CAR_KMH = 100, CAR_FACTOR = 1.25, EARTH_KM = 6371;
  // How far one is willing to walk — applied uniformly to first/last mile
  // (origin<->spot, spot<->dest) AND to hops between spots. A smaller transfer
  // cap disconnects sparse intercity corridors (Berlin<->Amsterdam needs ~8 km
  // hops), so we keep them equal; the graph stays small (~90k walk edges).
  const DEFAULT_MAX_WALK = 20;
  const TRANSFER_KM = DEFAULT_MAX_WALK;
  const ORIGIN = -2, DEST = -1, NO_TREE = -1;
  // Mirrors MIN_SUPPORT in build_ride_routes.py: an edge below this was taken by
  // one hitchhiker once, and only exists in the lazily loaded fallback graph.
  const MIN_SUPPORT = 2;
  const ALT_COLORS = ["#1a73e8", "#e8710a", "#188038"]; // fastest first

  // ---- small helpers -----------------------------------------------------
  function haversineKm(a, b) {
    const r = Math.PI / 180;
    const dlat = (b[0] - a[0]) * r, dlon = (b[1] - a[1]) * r;
    const s = Math.sin(dlat / 2) ** 2 +
      Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dlon / 2) ** 2;
    return EARTH_KM * 2 * Math.asin(Math.sqrt(s));
  }
  class MinHeap {
    constructor() { this.h = []; }
    push(x) { const h = this.h; h.push(x); let i = h.length - 1;
      while (i > 0) { const p = (i - 1) >> 1; if (h[p][0] <= h[i][0]) break; [h[p], h[i]] = [h[i], h[p]]; i = p; } }
    pop() { const h = this.h, top = h[0], last = h.pop();
      if (h.length) { h[0] = last; let i = 0; for (;;) { let l = 2 * i + 1, r = 2 * i + 2, m = i;
        if (l < h.length && h[l][0] < h[m][0]) m = l; if (r < h.length && h[r][0] < h[m][0]) m = r;
        if (m === i) break; [h[m], h[i]] = [h[i], h[m]]; i = m; } } return top; }
    get size() { return this.h.length; }
  }

  // ---- graph construction ------------------------------------------------
  function buildRouter(rep) {
    const spots = rep.spots;
    const treeAdj = [];            // t_id -> Map u -> [[v, km, wait], ...]
    const board = new Map();       // u -> [[t_id, v, km, wait], ...]
    const edgeKm = new Map();      // u*1e7+v -> km
    const edgeSupport = new Map(); // u*1e7+v -> rides that took this edge
    const carSpots = new Set();
    const waits = [];
    rep.trees.forEach((t) => {
      const tId = treeAdj.length, adj = new Map(), nodes = t.nodes;
      nodes.forEach((n) => {
        const from = n[1] === -1 ? t.s : nodes[n[1]][0], to = n[0];
        const support = n[2];
        const wait = n.length > 3 ? n[3] : null;
        const km = haversineKm(spots[from], spots[to]) * CAR_FACTOR;
        if (!adj.has(from)) adj.set(from, []);
        adj.get(from).push([to, km, wait]);
        // Boarding is only allowed at a corridor's root (t.s) — the spot where its
        // rides actually start. Mid-corridor nodes are pass-through points the car
        // drives past; you can't flag a fresh ride there. Downstream edges are
        // reached by continuing the ride (treeAdj), not by boarding here.
        if (from === t.s) {
          if (!board.has(from)) board.set(from, []);
          board.get(from).push([tId, to, km, wait]);
        }
        edgeKm.set(from * 1e7 + to, km);
        // The same (from, to) pair can appear in several corridors; the strongest
        // evidence for that road segment is what we report to the user.
        const key = from * 1e7 + to;
        edgeSupport.set(key, Math.max(edgeSupport.get(key) || 0, support));
        if (wait != null) waits.push(wait);
        carSpots.add(from); carSpots.add(to);
      });
      treeAdj.push(adj);
    });
    const defaultWait = waits.length ? waits.reduce((a, b) => a + b, 0) / waits.length : 0;
    const R = { spots, treeAdj, board, edgeKm, edgeSupport, defaultWait, nTrees: treeAdj.length,
      carSpots: [...carSpots], walkAdj: new Map(), grid: null, cellDeg: 0, walkReady: false };
    return R;
  }

  // Walk adjacency between spots within TRANSFER_KM, plus a grid for lookups.
  function ensureWalk(R) {
    if (R.walkReady) return;
    R.cellDeg = TRANSFER_KM / (EARTH_KM * Math.PI / 180);
    const key = (cy, cx) => cy * 100000 + cx;
    const grid = new Map();
    R.carSpots.forEach((idx) => {
      const s = R.spots[idx];
      const k = key(Math.floor(s[0] / R.cellDeg), Math.floor(s[1] / R.cellDeg));
      if (!grid.has(k)) grid.set(k, []); grid.get(k).push(idx);
    });
    R.grid = grid; R.key = key;
    const walkAdj = new Map();
    R.carSpots.forEach((idx) => {
      const s = R.spots[idx], cy = Math.floor(s[0] / R.cellDeg), cx = Math.floor(s[1] / R.cellDeg);
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
        const arr = grid.get(key(cy + dy, cx + dx)); if (!arr) continue;
        arr.forEach((j) => { if (j <= idx) return; const km = haversineKm(s, R.spots[j]);
          if (km <= TRANSFER_KM) {
            if (!walkAdj.has(idx)) walkAdj.set(idx, []); walkAdj.get(idx).push([j, km]);
            if (!walkAdj.has(j)) walkAdj.set(j, []); walkAdj.get(j).push([idx, km]); } });
      }
    });
    R.walkAdj = walkAdj; R.walkReady = true;
  }

  // Car-graph spots within maxKm of a point (first/last mile can be long, so we
  // scan a wider neighbourhood than the transfer grid cell).
  function spotsNear(R, pt, maxKm) {
    const rad = Math.ceil(maxKm / TRANSFER_KM);
    const cy = Math.floor(pt[0] / R.cellDeg), cx = Math.floor(pt[1] / R.cellDeg), out = [];
    for (let dy = -rad; dy <= rad; dy++) for (let dx = -rad; dx <= rad; dx++) {
      const arr = R.grid.get(R.key(cy + dy, cx + dx)); if (!arr) continue;
      arr.forEach((idx) => { const km = haversineKm(pt, R.spots[idx]); if (km <= maxKm) out.push([idx, km]); });
    }
    return out;
  }

  // ---- query -------------------------------------------------------------
  function route(R, start, dest, maxWalk, penalty) {
    const wmin = (km) => km / WALK_KMH * 60, cmin = (km) => km / CAR_KMH * 60;
    const M = R.nTrees + 2, enc = (spot, cor) => spot * M + (cor + 1);
    const dist = new Map(), prev = new Map(), pq = new MinHeap();
    const relax = (nst, t, entry) => {
      if (t < (dist.get(nst) ?? Infinity)) { dist.set(nst, t); prev.set(nst, entry); pq.push([t, nst]); } };
    spotsNear(R, start, maxWalk).forEach(([idx, km]) => relax(enc(idx, NO_TREE), wmin(km), [ORIGIN, "walk", km, 0]));
    const destSpots = new Map(spotsNear(R, dest, maxWalk));
    let best = Infinity;
    const directKm = haversineKm(start, dest);
    if (directKm <= maxWalk) { best = wmin(directKm); prev.set(DEST, [ORIGIN, "walk", directKm, 0]); }
    while (pq.size) {
      const [d, st] = pq.pop();
      if (d > (dist.get(st) ?? Infinity)) continue;
      if (d >= best) break;
      const spot = Math.floor(st / M), corridor = st % M - 1;
      if (corridor !== NO_TREE) {
        const cont = R.treeAdj[corridor].get(spot);
        if (cont) cont.forEach(([v, km]) => {
          const mult = penalty ? (penalty.get(spot * 1e7 + v) || 1) : 1;
          relax(enc(v, corridor), d + cmin(km) * mult, [st, "car", km, 0]); });
      }
      const bd = R.board.get(spot);
      if (bd) bd.forEach(([tId, v, km, wait]) => {
        const w = (wait == null) ? R.defaultWait : wait;
        const mult = penalty ? (penalty.get(spot * 1e7 + v) || 1) : 1;
        relax(enc(v, tId), d + cmin(km) * mult + w, [st, "board", km, w]); });
      const wk = R.walkAdj.get(spot);
      if (wk) wk.forEach(([v, km]) => relax(enc(v, NO_TREE), d + wmin(km), [st, "walk", km, 0]));
      if (destSpots.has(spot)) { const t = d + wmin(destSpots.get(spot));
        if (t < best) { best = t; prev.set(DEST, [st, "walk", destSpots.get(spot), 0]); } }
    }
    if (best === Infinity) return { found: false };
    const markOf = (n) => (n === ORIGIN || n === DEST) ? n : Math.floor(n / M);
    const coord = (m) => m === ORIGIN ? start : m === DEST ? dest : R.spots[m];
    const raw = []; const carEdges = new Set(); let node = DEST;
    while (node !== ORIGIN) { const [p, kind, km, wait] = prev.get(node); const a = markOf(p), b = markOf(node);
      raw.push([kind, a, b, km, wait]); if ((kind === "car" || kind === "board") && a >= 0 && b >= 0) carEdges.add(a * 1e7 + b); node = p; }
    raw.reverse();
    const legs = [];
    raw.forEach(([kind, a, b, km, wait]) => {
      const mode = kind === "walk" ? "walk" : "car";
      // A ride is only as well-evidenced as its weakest edge, so a leg carries the
      // minimum support of the edges it absorbs (undefined on walk legs).
      const sup = mode === "car" ? (R.edgeSupport.get(a * 1e7 + b) || 1) : Infinity;
      const last = legs[legs.length - 1];
      if (last && last.mode === mode && kind !== "board") {
        last.km += km; last.path.push(coord(b)); last.to = coord(b);
        last.support = Math.min(last.support, sup);
      } else legs.push({ mode, from: coord(a), to: coord(b), km, path: [coord(a), coord(b)],
        waitMin: kind === "board" ? wait : 0, support: sup });
    });
    legs.forEach((l) => { l.minutes = l.km / (l.mode === "walk" ? WALK_KMH : CAR_KMH) * 60; });
    const walkKm = legs.filter((l) => l.mode === "walk").reduce((s, l) => s + l.km, 0);
    const carKm = legs.filter((l) => l.mode === "car").reduce((s, l) => s + l.km, 0);
    const walkMin = legs.filter((l) => l.mode === "walk").reduce((s, l) => s + l.minutes, 0);
    const waitMin = legs.reduce((s, l) => s + l.waitMin, 0);
    const totalMin = legs.reduce((s, l) => s + l.minutes, 0) + waitMin;
    // Weakest link over the whole route: < MIN_SUPPORT means at least one ride
    // here was logged by a single hitchhiker, which the UI has to disclose.
    const minSupport = legs.reduce((s, l) => Math.min(s, l.support), Infinity);
    return { found: true, totalMin, waitMin, walkMin, walkKm, carKm, legs, carEdges, minSupport };
  }

  // Up to k sufficiently-different routes (penalty method).
  function alternatives(R, start, dest, maxWalk, k, maxOverlap) {
    const pen = new Map(), kept = [], keptEdges = [];
    for (let attempt = 0; attempt < k * 8 && kept.length < k; attempt++) {
      const res = route(R, start, dest, maxWalk, pen);
      if (!res.found) break;
      res.carEdges.forEach((e) => pen.set(e, (pen.get(e) || 1) * 2.5));
      let similar = false;
      for (const [edges, km] of keptEdges) {
        let shared = 0;
        res.carEdges.forEach((e) => { if (edges.has(e)) shared += R.edgeKm.get(e) || 0; });
        if (shared / (Math.min(res.carKm, km) || 1) >= maxOverlap) { similar = true; break; }
      }
      if (similar) continue;
      kept.push(res); keptEdges.push([res.carEdges, res.carKm]);
    }
    return kept;
  }

  // ======================================================================
  // UI
  // ======================================================================
  const RJ = {
    active: false, router: null,
    spots: null,                    // shared spot array, indexed by both graphs
    fallback: { promise: null, router: null },
    searchToken: null,              // invalidates an in-flight fallback search
    start: null, dest: null,        // { latlng:[lat,lon], label }
    activeField: "start",
    routes: [], highlight: 0,
    routeLayer: null, spotLayer: null, tagLayer: null, tagMarker: null,
    startMarker: null, destMarker: null,
    streetCache: new Map(),
  };
  window.RoutingUI = RJ;
  // Expose the control methods on the shared object too — map.js (navigateHome,
  // the map-click guard) calls RoutingUI.close()/.active. RJ itself is only the
  // state bag; open/close are closures, so they must be attached explicitly
  // (function declarations are hoisted, so this runs before they're defined).
  RJ.open = open;
  RJ.close = close;
  RJ.showAgain = showAgain;

  fetch("/repeatable_routes.json").then((r) => r.json()).then((rep) => {
    RJ.spots = rep.spots;
    RJ.router = buildRouter(rep); ensureWalk(RJ.router);
    // A shared #dir link may have opened the planner before the data arrived
    // (compute() showed "Loading route data…"); run it now that we can.
    if (RJ.active && RJ.start && RJ.dest && !RJ.routes.length) compute();
  }).catch((e) => console.error("routing data failed", e));

  // Pass 2's graph: every corridor, including the ones a single ride established.
  // ~4 MB against repeatable_routes.json's 1.3 MB, and most searches never need
  // it — so it is fetched the first time a search comes back empty, not on load.
  // Resolves to null (once, cached) if it can't be used, so we degrade to the
  // old "no route found" message instead of retrying the download per search.
  function loadFallbackRouter() {
    if (RJ.fallback.promise) return RJ.fallback.promise;
    RJ.fallback.promise = fetch("/oneoff_routes.json")
      .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then((weak) => {
        // Its node indices address repeatable_routes.json's spot array. If only
        // one of the pair was regenerated they no longer agree, and every route
        // we drew from it would run through the wrong spots — refuse instead.
        if (weak.spot_count !== RJ.spots.length) throw new Error("spot index mismatch");
        const R = buildRouter({ spots: RJ.spots, trees: weak.trees });
        ensureWalk(R);
        RJ.fallback.router = R;
        return R;
      })
      .catch((e) => { console.error("one-off routing data failed", e); return null; });
    return RJ.fallback.promise;
  }

  const photon = (typeof L !== "undefined" && L.Control && L.Control.Geocoder)
    ? L.Control.Geocoder.photon() : null;

  function fmtTime(min) {
    min = Math.round(min);
    const h = Math.floor(min / 60), m = min % 60;
    return h ? `${h}h${String(m).padStart(2, "0")}` : `${m}m`;
  }
  function fmtClock(d) { return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); }
  function fmtDay(d) { return d.toLocaleDateString([], { weekday: "short" }); }
  // Sub-10 km legs are usually walks, where 0.4 vs 0 km is the whole message.
  function fmtKm(km) { return km < 10 ? km.toFixed(1) : String(Math.round(km)); }

  const WALK_ICON = "fa-solid fa-person-walking";
  const RIDE_ICON = "fa-solid fa-thumbs-up";

  // Transit-app style mode strip: one glyph per leg, in travel order, so the shape
  // of a route (walk, two rides, walk) reads before any of the numbers do. A long
  // intercity route can have a dozen legs, which would wrap into a wall of chips —
  // truncate and count the rest, as a transit app does with its line badges.
  const MAX_CHIPS = 7;
  function chipStrip(rt) {
    const chip = (l) => `<span class="rp-chip rp-chip-${l.mode}"><i class="${
      l.mode === "walk" ? WALK_ICON : RIDE_ICON}"></i><span>${fmtKm(l.km)} km</span></span>`;
    const shown = rt.legs.slice(0, MAX_CHIPS).map(chip);
    const rest = rt.legs.length - MAX_CHIPS;
    if (rest > 0) shown.push(`<span class="rp-chip rp-chip-more">+${rest}</span>`);
    return shown.join('<i class="fa-solid fa-chevron-right rp-chip-sep"></i>');
  }

  // Permalink to a spot's own page, same id as generate_spot_id() in show.py.
  function spotHref(c) { return `/spot/${c[0].toFixed(5)}_${c[1].toFixed(5)}`; }

  // Reverse-geocoded names for the spots on a route, filled in asynchronously:
  // the itinerary renders with coordinates and swaps in a place name when Photon
  // answers. Cached per coordinate so re-expanding a route costs no requests.
  const labelCache = new Map();
  function fillSpotLabel(el, c) {
    const key = c[0].toFixed(5) + "_" + c[1].toFixed(5);
    if (labelCache.has(key)) { el.textContent = labelCache.get(key); return; }
    if (!photon || !photon.reverse) return;
    photon.reverse(L.latLng(c[0], c[1]), 4096, (results) => {
      const r = results && results[0];
      if (!r) return;
      const p = r.properties || {};
      // Photon's `name` is the nearest street or POI; `city` is what a person
      // would say. Prefer city, matching route_preview.py's endpoint labels.
      const name = p.city || p.name || p.county || (r.name || "").split(",")[0];
      if (!name) return;
      labelCache.set(key, name);
      el.textContent = name;
    });
  }

  // The first/last-mile walk (origin -> first spot, last spot -> destination) is
  // often a city hop you'd do by transit, not on foot, and can dominate the total.
  // Split it out so the headline shows the core hitch time (first spot -> last
  // spot, incl. mid-route transfers & waits); the full time is still used for
  // routing/ranking.
  function routeEnds(rt) {
    const legs = rt.legs;
    const first = legs[0] && legs[0].mode === "walk" ? legs[0] : null;
    const last = legs.length > 1 && legs[legs.length - 1].mode === "walk" ? legs[legs.length - 1] : null;
    const endsMin = (first ? first.minutes : 0) + (last ? last.minutes : 0);
    const endsKm = (first ? first.km : 0) + (last ? last.km : 0);
    return { endsMin, endsKm, coreMin: rt.totalMin - endsMin, midWalkMin: rt.walkMin - endsMin };
  }
  // Non-bold secondary line describing how to reach/leave the hitching spots.
  function endsLabel(rt) {
    const e = routeEnds(rt);
    if (e.endsKm < 0.2) return "";
    // Too far to reasonably walk in a city -> suggest public transport.
    return e.endsKm > 3
      ? "+ transit to start &amp; end"
      : `+ ${fmtTime(e.endsMin)} walk to start &amp; end`;
  }
  function pinIcon(kind) {
    return L.divIcon({
      className: `rp-pin rp-pin-${kind}`,
      html: `<i class="fa-solid fa-location-dot"></i>`,
      iconSize: [30, 30], iconAnchor: [15, 28],
    });
  }

  // ---- panel DOM ---------------------------------------------------------
  let panel;
  function buildPanel() {
    panel = document.createElement("div");
    panel.id = "route-panel";
    panel.hidden = true;
    panel.innerHTML = `
      <button class="rp-close" title="Close" aria-label="Close route planning">
        <i class="fa-solid fa-arrow-left"></i>
      </button>
      <div class="rp-fields">
        <div class="rp-field" data-field="start">
          <span class="rp-dot rp-dot-start"></span>
          <input type="text" autocomplete="off" placeholder="Choose starting point, or click on the map" />
          <button class="rp-clear" tabindex="-1" aria-label="Clear">&times;</button>
        </div>
        <div class="rp-field" data-field="dest">
          <span class="rp-dot rp-dot-dest"></span>
          <input type="text" autocomplete="off" placeholder="Choose destination, or click on the map" />
          <button class="rp-clear" tabindex="-1" aria-label="Clear">&times;</button>
        </div>
      </div>
      <div class="rp-suggest" hidden></div>
      <div class="rp-options" hidden></div>
      <div class="rp-status" hidden></div>`;
    document.body.appendChild(panel);

    panel.querySelector(".rp-close").addEventListener("click", close);
    panel.querySelectorAll(".rp-field").forEach((f) => {
      const field = f.dataset.field;
      const input = f.querySelector("input");
      input.addEventListener("focus", () => { RJ.activeField = field; });
      input.addEventListener("input", () => onType(field, input.value));
      f.querySelector(".rp-clear").addEventListener("click", () => {
        input.value = ""; clearPoint(field); hideSuggest();
      });
    });
    L.DomEvent.disableClickPropagation(panel);
    L.DomEvent.disableScrollPropagation(panel);
  }

  // ---- geocode suggestions ----------------------------------------------
  let typeTimer = null;
  function onType(field, text) {
    RJ.activeField = field;
    clearTimeout(typeTimer);
    if (!text || text.length < 3 || !photon) { hideSuggest(); return; }
    typeTimer = setTimeout(() => {
      photon.geocode(text, (results) => renderSuggest(field, results || []));
    }, 300);
  }
  function renderSuggest(field, results) {
    const box = panel.querySelector(".rp-suggest");
    if (!results.length) { hideSuggest(); return; }
    box.innerHTML = "";
    results.slice(0, 5).forEach((res) => {
      const item = document.createElement("div");
      item.className = "rp-suggest-item";
      item.innerHTML = `<i class="fa-solid fa-location-dot"></i> <span>${res.html || res.name}</span>`;
      item.addEventListener("click", () => {
        const c = res.center;
        setPoint(field, [c.lat, c.lng], (res.name || "").split(",")[0] || "Location");
        hideSuggest();
      });
      box.appendChild(item);
    });
    box.hidden = false;
  }
  function hideSuggest() { const b = panel.querySelector(".rp-suggest"); if (b) { b.hidden = true; b.innerHTML = ""; } }

  // ---- point setting -----------------------------------------------------
  function fieldInput(field) { return panel.querySelector(`.rp-field[data-field="${field}"] input`); }

  function setPoint(field, latlng, label) {
    RJ[field] = { latlng, label: label || `${latlng[0].toFixed(4)}, ${latlng[1].toFixed(4)}` };
    fieldInput(field).value = RJ[field].label;
    const marker = field === "start" ? "startMarker" : "destMarker";
    if (RJ[marker]) RJ[marker].setLatLng(latlng);
    else RJ[marker] = L.marker(latlng, { icon: pinIcon(field), zIndexOffset: 1000, interactive: false }).addTo(map);
    // Move focus to the empty field so the next map click fills it.
    RJ.activeField = RJ.start && !RJ.dest ? "dest" : RJ.dest && !RJ.start ? "start" : field === "start" ? "dest" : "start";
    if (RJ.start && RJ.dest) compute();
  }
  function clearPoint(field) {
    RJ[field] = null;
    const marker = field === "start" ? "startMarker" : "destMarker";
    if (RJ[marker]) { map.removeLayer(RJ[marker]); RJ[marker] = null; }
    RJ.activeField = field;
    clearRoutes();
  }

  // ---- open / close ------------------------------------------------------
  function open() {
    if (RJ.active) return;
    RJ.active = true;
    document.body.classList.add("routing-active");
    if (!panel) buildPanel();
    panel.hidden = false;
    if (typeof setSpotsVisible === "function") setSpotsVisible(false);
    map.getContainer().style.cursor = "crosshair";
    setTimeout(() => fieldInput("start").focus(), 50);
  }
  function close() {
    if (!RJ.active) return;
    RJ.active = false;
    document.body.classList.remove("routing-active");
    if (panel) panel.hidden = true;
    hideSuggest();
    clearRoutes();
    hideResultsSheet();
    ["start", "dest"].forEach(clearPoint);
    if (panel) { fieldInput("start").value = ""; fieldInput("dest").value = ""; }
    // Countries mode hides the spots itself; restoring them here would make them
    // reappear on top of the choropleth, where they were never shown.
    const inCountriesMode = typeof getMapMode === "function" && getMapMode() === "countries";
    if (typeof setSpotsVisible === "function" && !inCountriesMode) setSpotsVisible(true);
    map.getContainer().style.cursor = "";
    // Drop a shared route link so closing returns to a clean URL. The path form
    // must fall back to BASE_PATH (map.js): leaving "/dir/…" in the address bar
    // would make the next navigate() reopen the planner we just closed.
    const dirHash = location.hash.slice(1).startsWith("dir/");
    if (DIR_PATH_RE.test(location.pathname)) {
      // BASE_PATH is a top-level const in map.js: a global lexical binding, so it
      // resolves here but never as a window property.
      const home = typeof BASE_PATH === "string" ? BASE_PATH : "/";
      history.replaceState(null, "", home + location.search + (dirHash ? "" : location.hash));
    } else if (dirHash) {
      history.replaceState(null, "", location.pathname + location.search);
    }
  }

  // ---- routing + drawing -------------------------------------------------
  function clearRoutes() {
    RJ._token = {}; // stop any in-flight street upgrades from touching old layers
    [RJ.routeLayer, RJ.spotLayer, RJ.tagLayer].forEach((l) => { if (l) map.removeLayer(l); });
    RJ.routeLayer = RJ.spotLayer = RJ.tagLayer = RJ.tagMarker = null;
    RJ.routes = [];
    // Any fallback search still downloading its graph must not draw onto a map
    // the user has since cleared or navigated away from.
    RJ.searchToken = null;
    disableRoutePanePointerEvents();
    const sheet = resultsSheet();
    const opts = sheet && sheet.querySelector(".rp-options");
    if (opts) opts.innerHTML = "";
    setStatus(null);
  }
  function setStatus(msg) {
    const s = panel && panel.querySelector(".rp-status");
    if (!s) return;
    if (!msg) { s.hidden = true; s.textContent = ""; } else { s.hidden = false; s.textContent = msg; }
  }

  function compute() {
    if (!RJ.router) { setStatus("Loading route data…"); return; }
    if (!RJ.start || !RJ.dest) return;
    hideSuggest();
    clearRoutes();
    setStatus("Finding routes…");
    // Defer so "Finding routes…" paints before the (sync) search runs. Cancel any
    // pending compute so two quick clicks can't both draw and orphan a layer.
    clearTimeout(RJ._computeTimer);
    const search = RJ.searchToken = {};   // a later compute() invalidates this one
    RJ._computeTimer = setTimeout(() => {
      const from = RJ.start.latlng, to = RJ.dest.latlng;
      logRouteRequest(from, to);   // record which route was asked for (server has no other signal)
      const res = alternatives(RJ.router, from, to, DEFAULT_MAX_WALK, 3, 0.6);
      clearRoutes(); // drop anything a previous run left before drawing fresh
      if (res.length) { showRoutes(res); return; }

      // Nothing repeats between these points. Retry on the one-off graph before
      // giving up — a corridor one hitchhiker logged once still beats nothing.
      // (clearRoutes above cancelled the token; this search is still the live one.)
      RJ.searchToken = search;
      setStatus("No repeatable route — checking one-off rides…");
      loadFallbackRouter().then((FB) => {
        if (search !== RJ.searchToken) return;   // superseded while downloading
        const alt = FB ? alternatives(FB, from, to, DEFAULT_MAX_WALK, 3, 0.6) : [];
        clearRoutes();
        if (!alt.length) { setStatus(diagnoseNoRoute(FB || RJ.router, from, to, DEFAULT_MAX_WALK, !!FB)); return; }
        showRoutes(alt);
      });
    }, 30);
  }

  function showRoutes(res) {
    setStatus(null);
    // Show fastest by core (hitching) time first — that's the headline figure,
    // so ordering, colours and deltas all stay consistent.
    res.sort((a, b) => routeEnds(a).coreMin - routeEnds(b).coreMin);
    RJ.routes = res;
    const token = {};
    RJ._token = token;      // invalidates any in-flight street upgrades
    drawRoutes();
    renderOptions();
    highlight(0);
    upgradeAllToStreets(token);
    updateShareUrl();       // make this search shareable (#dir/from/to)
  }

  // When no route is found, explain which end is the problem so the user can act
  // (move a point, or search only the part of the trip that has coverage). An
  // endpoint is "covered" if any repeatable-route spot sits within walking range;
  // if both are covered but still unconnected, the middle lacks logged rides.
  function diagnoseNoRoute(R, start, dest, maxWalk, triedOneOff) {
    const startCovered = spotsNear(R, start, maxWalk).length > 0;
    const destCovered = spotsNear(R, dest, maxWalk).length > 0;
    if (!startCovered && !destCovered) {
      return "No route found: both your start and destination are in areas where too few people have hitchhiked. " +
        "Try points nearer to major roads or cities.";
    }
    if (!startCovered) {
      return "No route found: your starting point is in an area where too few people have hitchhiked. " +
        "Move it closer to a major road or city, or search just the later part of your trip.";
    }
    if (!destCovered) {
      return "No route found: your destination is in an area where too few people have hitchhiked. " +
        "Move it closer to a major road or city, or search just the earlier part of your trip.";
    }
    // The middle is the gap. Say so — and, when the one-off graph was searched
    // too, that no single logged ride bridges it either.
    return "No route found: we couldn't connect these two points" +
      (triedOneOff ? ", even using rides only one person has logged" : " with repeatable rides") +
      ". Try searching for part of the route — e.g. between larger cities along the way.";
  }

  // ---- shareable route URL (/dir/<slat>,<slon>/<dlat>,<dlon>) ------------
  // Google-Maps-style: the current start+destination live in the URL so the link
  // reopens the same route. The endpoints sit in the path, not a #dir/ fragment,
  // for the same reason spot ids do (see map.js): messengers strip the fragment
  // when auto-linking a pasted URL — and a fragment never reaches the server, so
  // a hash link could never carry the OpenGraph preview Flask renders for /dir/.
  // replaceState (not assignment) avoids firing a navigate/popstate loop; a fresh
  // load / paste is handled in init().
  const DIR_PATH_RE = /^\/dir\/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)\/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)\/?$/;

  // Beacon the requested route to the server so we can see which corridors are in
  // demand — routing is computed client-side, so this is the only server signal.
  // sendBeacon is fire-and-forget and survives the page being navigated away.
  function logRouteRequest(from, to) {
    try {
      const body = JSON.stringify({
        slat: +from[0].toFixed(5), slon: +from[1].toFixed(5),
        dlat: +to[0].toFixed(5), dlon: +to[1].toFixed(5),
      });
      const blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon) navigator.sendBeacon("/log-route-request", blob);
    } catch (e) { /* logging must never break routing */ }
  }

  function updateShareUrl() {
    if (!RJ.start || !RJ.dest) return;
    const f = RJ.start.latlng, t = RJ.dest.latlng;
    const path = `/dir/${f[0].toFixed(5)},${f[1].toFixed(5)}/${t[0].toFixed(5)},${t[1].toFixed(5)}`;
    // A legacy #dir hash described this very route; drop it rather than carry a
    // second, staler copy of the state. A #map= viewport is kept.
    const hash = location.hash.slice(1).startsWith("dir/") ? "" : location.hash;
    history.replaceState(null, "", path + location.search + hash);
  }
  function parseDirPath(pathname) {
    const m = DIR_PATH_RE.exec(pathname || "");
    if (!m) return null;
    return { from: [+m[1], +m[2]], to: [+m[3], +m[4]] };
  }
  function parseShareUrl(hash) {
    // Legacy "#dir/<slat>,<slon>/<dlat>,<dlon>" -> {from:[lat,lon], to:[lat,lon]} or null
    const parts = hash.replace(/^#/, "").split("/");
    if (parts[0] !== "dir" || parts.length < 3) return null;
    const a = parts[1].split(",").map(Number), b = parts[2].split(",").map(Number);
    if (a.length !== 2 || b.length !== 2 || a.concat(b).some((n) => !isFinite(n))) return null;
    return { from: a, to: b };
  }
  function routeFromUrl() {
    return parseDirPath(location.pathname) || parseShareUrl(location.hash);
  }
  function openFromUrl() {
    const p = routeFromUrl();
    if (!p) return false;
    open();
    // setPoint fills the input and auto-computes once both ends are set.
    setPoint("start", p.from, coordLabel(p.from));
    setPoint("dest", p.to, coordLabel(p.to));
    // Reverse-geocode nicer labels in the background.
    reverseLabel("start", p.from); reverseLabel("dest", p.to);
    return true;
  }
  function coordLabel(ll) { return ll[0].toFixed(4) + ", " + ll[1].toFixed(4); }
  function reverseLabel(field, ll) {
    if (!photon || !photon.reverse) return;
    photon.reverse(L.latLng(ll[0], ll[1]), map.getZoom(), (results) => {
      if (results && results[0] && RJ[field]) {
        RJ[field].label = (results[0].name || "").split(",").slice(0, 2).join(",") || RJ[field].label;
        if (fieldInput(field)) fieldInput(field).value = RJ[field].label;
      }
    });
  }

  // Routes must not live in the default overlay pane: style.css dims it to 30%
  // opacity while zoomed out (body.zoomed-out, set below zoom 9) and hides it
  // outright while filtering. Both rules exist to keep a spot's destination
  // arrows from cluttering a wide view — but drawRoutes() fitBounds()es onto a
  // whole intercity route, which lands below zoom 9 every time, so the routes
  // would draw at ~0.07-0.28 effective opacity. Own pane, above the overlay pane
  // (400) and the country choropleth (450), below the markers (600).
  function routePane() {
    if (!map.getPane("routes")) {
      const p = map.createPane("routes");
      p.style.zIndex = 460;
    }
    // With preferCanvas, Leaflet keeps this pane's renderer canvas — sized to the
    // whole map — in the DOM after clearRoutes() removes the polylines. An empty
    // canvas above the choropleth would swallow every country click, so the pane
    // only accepts pointer events while routes are actually drawn.
    map.getPane("routes").style.pointerEvents = "";
    return "routes";
  }

  // Let clicks fall through to the layers underneath (choropleth, spot markers)
  // once no route is drawn. See routePane().
  function disableRoutePanePointerEvents() {
    const p = map.getPane("routes");
    if (p) p.style.pointerEvents = "none";
  }

  function drawRoutes() {
    // Defensive: never stack layers if one already exists.
    [RJ.routeLayer, RJ.spotLayer, RJ.tagLayer].forEach((l) => { if (l) map.removeLayer(l); });
    RJ.routeLayer = L.layerGroup().addTo(map);
    RJ.tagLayer = L.layerGroup().addTo(map);
    RJ.spotLayer = L.layerGroup().addTo(map);
    // Draw slowest first so the fastest ends up on top.
    RJ.routes.forEach((rt) => { rt._layers = []; });
    for (let i = RJ.routes.length - 1; i >= 0; i--) drawOneRoute(i);
    // Fit to the fastest route.
    const pts = [].concat(...RJ.routes[0].legs.map((l) => l.path));
    map.fitBounds(L.latLngBounds(pts), { paddingTopLeft: [30, 140], paddingBottomRight: [30, 40] });
  }

  function drawOneRoute(i) {
    const rt = RJ.routes[i], color = ALT_COLORS[i % ALT_COLORS.length];
    rt._layers = [];
    rt.legs.forEach((leg) => {
      const pl = L.polyline(leg.path, {
        color, opacity: 0.35, weight: leg.mode === "walk" ? 3 : 5,
        dashArray: leg.mode === "walk" ? "2 8" : null, lineCap: "round", lineJoin: "round",
        pane: routePane(),
      });
      pl.options._car = leg.mode === "car";
      // Stop the click here: with preferCanvas a polyline click otherwise also
      // fires the map click, which would drop a new point and recompute.
      pl.on("click", (e) => { RJ._pickAt = Date.now(); L.DomEvent.stopPropagation(e); highlight(i); });
      pl.addTo(RJ.routeLayer); rt._layers.push(pl);
    });
  }

  function tagIcon(rt, i) {
    const color = ALT_COLORS[i % ALT_COLORS.length];
    const e = routeEnds(rt);
    const mid = e.midWalkMin > 0.5 ? ` · ${fmtTime(e.midWalkMin)} walk` : "";
    const ends = endsLabel(rt);
    return L.divIcon({
      className: "route-tag-wrap",
      html: `<div class="route-tag active" style="--rc:${color}">
        <b>${fmtTime(e.coreMin)}</b><span class="rt-sub">${rt.carKm.toFixed(0)} km${mid}</span>
        ${ends ? `<span class="rt-ends">${ends}</span>` : ""}</div>`,
      iconSize: null, iconAnchor: [0, 12],
    });
  }

  function highlight(i) {
    RJ.highlight = i;
    RJ.routes.forEach((rt, j) => {
      const on = j === i;
      // Non-selected routes stay as faint real roads; the selected one is solid.
      rt._layers.forEach((pl) => pl.setStyle({
        opacity: on ? 0.95 : 0.22,
        weight: pl.options._car ? (on ? 6 : 4) : (on ? 4 : 3),
      }));
      if (on) rt._layers.forEach((pl) => pl.bringToFront());
    });
    // A single time tag, only on the selected route.
    if (RJ.tagMarker) { RJ.tagLayer.removeLayer(RJ.tagMarker); RJ.tagMarker = null; }
    const rt = RJ.routes[i];
    const all = [].concat(...rt.legs.map((l) => l.path));
    const tp = all[Math.floor(all.length * 0.45)];
    RJ.tagMarker = L.marker(tp, { icon: tagIcon(rt, i), interactive: true, zIndexOffset: 600 });
    RJ.tagMarker.on("click", (e) => { RJ._pickAt = Date.now(); L.DomEvent.stopPropagation(e); });
    RJ.tagMarker.addTo(RJ.tagLayer);
    // Only the highlighted route's spots are shown.
    drawRouteSpots(i);
    const sheet = resultsSheet();
    if (sheet) sheet.querySelectorAll(".rp-option").forEach((r) => r.classList.toggle("active", Number(r.dataset.i) === i));
  }

  // Marker for a spot where you get in or out of a car. The first boarding spot
  // and the final drop-off get their own symbols (thumb / finish flag) so the
  // two ends of the hitchhiking part of the route read at a glance; every other
  // boarding spot is an intermediate car change.
  function carStopIcon(kind, color) {
    const glyph = kind === "first" ? "fa-solid fa-thumbs-up"
      : kind === "last" ? "fa-solid fa-flag-checkered" : "fa-solid fa-right-left";
    return L.divIcon({ className: "route-change-spot route-stop-" + kind,
      html: `<div style="--rc:${color}"><i class="${glyph}"></i></div>`,
      iconSize: [22, 22], iconAnchor: [11, 11] });
  }

  // Only the highlighted route's spots are shown: every spot along it, with the
  // change points (where you board a new car) highlighted. Clicking any spot
  // opens the normal spot bottom sheet (all rides at that spot).
  function drawRouteSpots(i) {
    if (RJ.spotLayer) RJ.spotLayer.clearLayers();
    const rt = RJ.routes[i], color = ALT_COLORS[i % ALT_COLORS.length];
    const seen = new Set();
    const carLegs = rt.legs.filter((l) => l.mode === "car");
    const firstLeg = carLegs[0], lastLeg = carLegs[carLegs.length - 1];
    rt.legs.forEach((leg) => {
      if (leg.mode !== "car") return;
      leg.path.forEach((c, idx) => {
        const key = c[0].toFixed(5) + "_" + c[1].toFixed(5);
        // First spot of the first car leg = where you board the first car;
        // last spot of the last car leg = where you get off for good.
        const kind = leg === firstLeg && idx === 0 ? "first"
          : leg === lastLeg && idx === leg.path.length - 1 ? "last"
            : idx === 0 ? "change" : null;
        const change = kind !== null; // boarding / final drop-off spot
        if (seen.has(key) && !change) return; seen.add(key);
        let m;
        if (change) {
          const tip = kind === "first" ? "Start hitchhiking here — tap for rides"
            : kind === "last" ? "Get off here — tap for rides" : "Change car here — tap for rides";
          m = L.marker(c, { icon: carStopIcon(kind, color), zIndexOffset: 400 })
            .bindTooltip(tip, { direction: "top" });
        } else {
          // Same pane as the route lines — a circleMarker is a Path, so it would
          // otherwise be dimmed with the default overlay pane (see routePane).
          m = L.circleMarker(c, { radius: 4.5, color: "#fff", weight: 1, fillColor: color, fillOpacity: 0.95,
            pane: routePane() });
        }
        m.on("click", (e) => { RJ._pickAt = Date.now(); L.DomEvent.stopPropagation(e); openSpotSheet(c, e); });
        m.addTo(RJ.spotLayer);
      });
    });
  }

  // Open the normal spot bottom sheet for the real map spot nearest a route spot
  // (that marker already carries the right spotId + rides), reusing map.js.
  function openSpotSheet(latlng, e) {
    const markers = window.allMarkers;
    if (!markers || !markers.length || typeof handleMarkerClick !== "function") return false;
    const target = L.latLng(latlng[0], latlng[1]);
    let best = null, bestD = Infinity;
    for (const mk of markers) {
      const d = mk.getLatLng().distanceTo(target);
      if (d < bestD) { bestD = d; best = mk; }
    }
    if (!best || bestD >= 150) return false;
    handleMarkerClick(best, best.getLatLng(), e);
    return true;
  }

  // Itinerary spot links: open the spot sheet in place when the marker is on the
  // map, otherwise let the browser follow the permalink (markers are filtered out
  // by the active filters, or not loaded yet).
  function spotLink(c) {
    const a = document.createElement("a");
    a.href = spotHref(c);
    a.className = "rp-spot-link";
    a.textContent = coordLabel(c);
    a.addEventListener("click", (e) => { if (openSpotSheet(c, e)) e.preventDefault(); });
    return a;
  }

  // ---- street-following geometry (OSRM) for ALL routes -------------------
  async function upgradeAllToStreets(token) {
    // Snap the highlighted route first, then the rest, so the focused route
    // gets real roads soonest. Sequential to stay gentle on the OSRM demo server.
    const order = RJ.routes.map((_, i) => i).sort((a, b) => (a === RJ.highlight ? -1 : b === RJ.highlight ? 1 : 0));
    for (const i of order) {
      const rt = RJ.routes[i];
      for (let li = 0; li < rt.legs.length; li++) {
        const leg = rt.legs[li];
        if (leg.mode !== "car" || leg.path.length < 2) continue;
        const pl = rt._layers[li];
        const geo = await streetGeometry(leg.path, leg.km);
        if (token !== RJ._token) return;      // a newer compute superseded us
        if (geo && map.hasLayer(pl)) pl.setLatLngs(geo);
      }
    }
  }

  // A car leg is a single ride: you board at leg.path[0] and get out at the last
  // anchor. Everything between is a corridor spot the driver merely passed, and
  // those sit at petrol stations, rest areas and on-ramps rather than on the
  // carriageway. Passed to OSRM as via points they become hard constraints, so
  // the line left the motorway and looped back at every one of them — two
  // anchors 2.6 km apart on the AP-7 cost 13 km of phantom driving. The rider
  // only has to be at the two ends, so only those are sent; the corridor
  // anchors keep their own markers (drawRouteSpots) and no longer bend the line.
  const BEARING_RANGE_DEG = 90;
  // The one snap that still matters is at the two ends, where a frontage road
  // running alongside the motorway heads the same way and is an equally valid
  // match. Hinting the direction of travel picks the carriageway that goes there.
  // The hint must be read from an anchor a corridor-length away, not the nearest
  // one: an interchange packs several anchors into ~100 m in near-random order
  // (the AP-7 leg starts with three inside 130 m, bearing 181/187/315 on a route
  // heading 33), so a close anchor hints the opposite carriageway.
  const BEARING_HINT_MIN_KM = 1;
  const COINCIDENT_KM = 0.01;
  // Compared against leg.km, which is already crow-flight * CAR_FACTOR. With no
  // vias left to inflate it, anything past this is OSRM snapping to a road it
  // could not leave, and the straight line is the better lie.
  const MAX_DETOUR_RATIO = 1.6;

  function bearingDeg(a, b) {
    const r = Math.PI / 180;
    const y = Math.sin((b[1] - a[1]) * r) * Math.cos(b[0] * r);
    const x = Math.cos(a[0] * r) * Math.sin(b[0] * r) -
      Math.sin(a[0] * r) * Math.cos(b[0] * r) * Math.cos((b[1] - a[1]) * r);
    return (Math.atan2(y, x) / r + 360) % 360;
  }
  // Direction of travel at each end of the leg, read off the first corridor
  // anchor far enough out to carry the corridor's direction rather than the
  // local scatter. A leg shorter than the hint distance falls back to its own
  // end-to-end bearing.
  function bearingsParam(path) {
    const end = path.length - 1;
    let i = 1;
    while (i < end && haversineKm(path[0], path[i]) < BEARING_HINT_MIN_KM) i++;
    let j = end - 1;
    while (j > 0 && haversineKm(path[j], path[end]) < BEARING_HINT_MIN_KM) j--;
    const hint = (a, b) => (haversineKm(a, b) < COINCIDENT_KM
      // Coincident anchors give no direction; let OSRM snap freely there.
      ? "0,180"
      : `${Math.round(bearingDeg(a, b))},${BEARING_RANGE_DEG}`);
    return `${hint(path[0], path[i])};${hint(path[j], path[end])}`;
  }

  async function streetGeometry(path, legKm) {
    const pts = [path[0], path[path.length - 1]];
    const key = pts.map((p) => p[0].toFixed(4) + "," + p[1].toFixed(4)).join(";");
    if (RJ.streetCache.has(key)) return RJ.streetCache.get(key);
    const coords = pts.map((p) => `${p[1]},${p[0]}`).join(";");
    const params = `overview=full&geometries=geojson&bearings=${bearingsParam(path)}`;
    try {
      const r = await fetch(`https://router.project-osrm.org/route/v1/driving/${coords}?${params}`);
      const d = await r.json();
      if (d.code !== "Ok" || !d.routes || !d.routes[0]) { RJ.streetCache.set(key, null); return null; }
      if (legKm > 0 && d.routes[0].distance / 1000 > legKm * MAX_DETOUR_RATIO) {
        RJ.streetCache.set(key, null); return null;
      }
      const geo = d.routes[0].geometry.coordinates.map((c) => [c[1], c[0]]);
      RJ.streetCache.set(key, geo);
      return geo;
    } catch (e) { RJ.streetCache.set(key, null); return null; }
  }

  // ---- results: the 3 options live in the bottom snap sheet --------------
  function resultsSheet() { return document.querySelector(".sidebar.routing"); }
  function optionsBox() {
    const sheet = resultsSheet();
    if (!sheet) return null;
    let body = sheet.querySelector(".sheet-body");
    // Replace the placeholder body with our options container once we have routes.
    // The share button carries no data-share-url: the delegated handler in
    // base.html falls back to the current URL, which updateShareUrl() keeps as the
    // /dir/<from>/<to> permalink for whatever route is currently shown.
    if (!body.querySelector(".rp-options")) {
      body.innerHTML =
        '<div class="rp-sheet-head">' +
        '<h3 class="rp-sheet-title">Routes</h3>' +
        '<button type="button" class="share-btn" data-share-title="Hitchhiking route – Hitchwiki Maps">' +
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>' +
        '<span class="share-btn-label">Share</span></button>' +
        '</div><div class="rp-options"></div>';
    }
    return body.querySelector(".rp-options");
  }
  function showResultsSheet() {
    const sheet = resultsSheet();
    if (!sheet) return;
    // Keep the user's chosen snap height across re-computes and across
    // re-showing after a spot pane closes; only pick a default on first open.
    const hasSnap = /\bsnap-/.test(sheet.className);
    if (typeof bar === "function") bar(".sidebar.routing"); else sheet.classList.add("visible");
    if (!hasSnap) {
      const snaps = typeof ROUTING_SHEET_SNAPS !== "undefined" ? ROUTING_SHEET_SNAPS : { half: 55, full: 0 };
      if (typeof setSheetSnap === "function") setSheetSnap(sheet, "half", snaps);
    }
    if (typeof updateBottomPaneVar === "function") updateBottomPaneVar();
  }
  // Re-show the route view after a spot pane (opened from a route marker) closes:
  // the drawn route layers were never removed, so just reopen the options sheet
  // and restore the shareable #dir URL (the spot click had swapped it for ?lat,lon).
  function showAgain() {
    if (!RJ.active || !RJ.routes.length) return;
    showResultsSheet();
    updateShareUrl();
  }
  function hideResultsSheet() {
    const sheet = resultsSheet();
    if (sheet) sheet.classList.remove("visible");
  }
  // "Details" expands the route into a step-by-step itinerary. Selecting the route
  // as well, so the map always shows what the open itinerary describes.
  function toggleDetails(row, rt, i) {
    const steps = row.querySelector(".rp-steps");
    const btn = row.querySelector(".rp-details-btn");
    const open = steps.hidden;
    if (open && !steps.childElementCount) steps.appendChild(buildItinerary(rt));
    steps.hidden = !open;
    btn.setAttribute("aria-expanded", String(open));
    btn.textContent = open ? "Hide details" : "Details";
    if (open) highlight(i);
  }

  // A node on the itinerary rail: an endpoint, or a spot where you get in or out
  // of a car. Spots link to their own page and open the spot sheet in place.
  function nodeRow(minutes, base, kind, label, c) {
    const li = document.createElement("li");
    li.className = "rp-step rp-node rp-node-" + kind;
    li.innerHTML = `
      <span class="rp-time">${fmtClock(new Date(base + minutes * 60000))}</span>
      <span class="rp-rail"><span class="rp-dotm"></span></span>
      <span class="rp-place"></span>`;
    const place = li.querySelector(".rp-place");
    if (kind === "start" || kind === "dest") {
      place.textContent = label || coordLabel(c);
    } else {
      const a = spotLink(c);
      place.appendChild(a);
      fillSpotLabel(a, c);
    }
    return li;
  }

  // An edge on the rail: the walk or the ride between two nodes.
  function edgeRow(leg) {
    const li = document.createElement("li");
    li.className = "rp-step rp-edge rp-edge-" + leg.mode;
    const via = leg.mode === "car" ? leg.path.slice(1, -1) : [];
    // How many hitchhikers this ride is inferred from. Only worth saying when it
    // is the one that makes the route a guess rather than a pattern.
    const weak = leg.mode === "car" && leg.support < MIN_SUPPORT;
    li.innerHTML = `
      <span class="rp-time"></span>
      <span class="rp-rail"><span class="rp-line"></span></span>
      <span class="rp-edge-body">
        <span class="rp-edge-head"><i class="${leg.mode === "walk" ? WALK_ICON : RIDE_ICON}"></i>
          <b>${leg.mode === "walk" ? "Walk" : "Ride"}</b></span>
        <span class="rp-edge-sub">${fmtKm(leg.km)} km · ${fmtTime(leg.minutes)}${
          weak ? ' · <span class="rp-weak">1 logged ride</span>' : ""}</span>
      </span>`;
    if (weak) li.classList.add("rp-edge-weak");
    // Corridor spots the driver merely passes: worth listing (you can be dropped
    // at one), but noise by default — collapsed behind a count, as transit apps
    // collapse intermediate stops.
    if (via.length) {
      const body = li.querySelector(".rp-edge-body");
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "rp-via-toggle";
      toggle.textContent = `${via.length} spot${via.length > 1 ? "s" : ""} on the way`;
      const list = document.createElement("ul");
      list.className = "rp-via"; list.hidden = true;
      via.forEach((c) => {
        const item = document.createElement("li");
        item.appendChild(spotLink(c));
        list.appendChild(item);
      });
      toggle.addEventListener("click", () => {
        list.hidden = !list.hidden;
        toggle.classList.toggle("open", !list.hidden);
        // Only pay for geocoding the corridor once the user asks to see it.
        if (!list.hidden) list.querySelectorAll("a").forEach((a, k) => fillSpotLabel(a, via[k]));
      });
      body.appendChild(toggle);
      body.appendChild(list);
    }
    return li;
  }

  // Waiting happens at the spot you just reached, before the car that boards
  // there. Its own row, so the clock times on the nodes stay consistent.
  function waitRow(min) {
    const li = document.createElement("li");
    li.className = "rp-step rp-edge rp-wait";
    li.innerHTML = `
      <span class="rp-time"></span>
      <span class="rp-rail"><span class="rp-line rp-line-wait"></span></span>
      <span class="rp-edge-body"><span class="rp-edge-head"><i class="fa-regular fa-clock"></i>
        <b>Wait</b></span> <span class="rp-edge-sub">about ${fmtTime(min)}</span></span>`;
    return li;
  }

  // Clock times assume you leave now; each leg and each wait advances the clock,
  // exactly as the ranking does (rt.totalMin is the same sum).
  function buildItinerary(rt) {
    const ol = document.createElement("ol");
    ol.className = "rp-itin";
    const base = Date.now();
    let t = 0;
    const legs = rt.legs;
    ol.appendChild(nodeRow(t, base, "start", RJ.start && RJ.start.label, legs[0].from));
    legs.forEach((leg, li) => {
      if (leg.waitMin > 0.5) { ol.appendChild(waitRow(leg.waitMin)); t += leg.waitMin; }
      ol.appendChild(edgeRow(leg));
      t += leg.minutes;
      const last = li === legs.length - 1;
      ol.appendChild(nodeRow(t, base, last ? "dest" : "spot",
        last ? (RJ.dest && RJ.dest.label) : null, leg.to));
    });
    return ol;
  }

  function renderOptions() {
    const box = optionsBox();
    if (!box) return;
    box.innerHTML = "";
    // Rank by core (hitching) time so the headline figures match the sort.
    const fastest = routeEnds(RJ.routes[0]).coreMin;
    RJ.routes.forEach((rt, i) => {
      const e = routeEnds(rt);
      const cars = rt.legs.filter((l) => l.mode === "car").length;
      const oneOff = rt.minSupport < MIN_SUPPORT;
      const delta = i === 0 ? "fastest" : "+" + fmtTime(e.coreMin - fastest);
      const mid = e.midWalkMin > 0.5 ? ` · ${fmtTime(e.midWalkMin)} walk` : "";
      const ends = endsLabel(rt);
      // Depart-now clock line, as a transit app shows it. rt.totalMin includes the
      // first/last-mile walks and every wait, so it is the honest door-to-door span.
      const depart = new Date();
      const arrive = new Date(depart.getTime() + rt.totalMin * 60000);
      const dayTag = arrive.toDateString() === depart.toDateString() ? "" : ` (${fmtDay(arrive)})`;
      // A <button> can't contain the buttons and links the itinerary needs, so the
      // card is a div and only its summary row is the route-selecting control.
      const row = document.createElement("div");
      row.className = "rp-option"; row.dataset.i = i;
      row.style.setProperty("--rc", ALT_COLORS[i % ALT_COLORS.length]);
      row.innerHTML = `
        <span class="rp-opt-bar"></span>
        <div class="rp-opt-body">
          <button class="rp-opt-summary" type="button">
            <span class="rp-opt-clock">${fmtClock(depart)}—${fmtClock(arrive)}${dayTag}</span>
            <span class="rp-opt-chips">${chipStrip(rt)}</span>
            <span class="rp-opt-head"><b>${fmtTime(e.coreMin)}</b> <span class="rp-opt-delta">${delta}</span></span>
            <span class="rp-opt-sub">${rt.carKm.toFixed(0)} km${mid} · ${cars} ride${cars > 1 ? "s" : ""} · ${Math.round(rt.waitMin)} min wait</span>
            ${ends ? `<span class="rp-opt-ends">${ends}</span>` : ""}
            ${oneOff ? '<span class="rp-opt-weak"><i class="fa-solid fa-circle-info"></i>' +
              "Includes a leg only one hitchhiker has logged</span>" : ""}
          </button>
          <button class="rp-details-btn" type="button" aria-expanded="false">Details</button>
          <div class="rp-steps" hidden></div>
        </div>`;
      row.querySelector(".rp-opt-summary").addEventListener("click", () => highlight(i));
      row.querySelector(".rp-details-btn").addEventListener("click", () => toggleDetails(row, rt, i));
      box.appendChild(row);
    });
    showResultsSheet();
  }

  // ---- map click while planning -----------------------------------------
  function onMapClick(e) {
    if (!RJ.active) return;
    // Backup for canvas hit-testing: ignore a map click that immediately follows
    // a route/tag click (which set RJ._pickAt) so selecting a route never drops a pin.
    if (RJ._pickAt && Date.now() - RJ._pickAt < 200) return;
    const latlng = [e.latlng.lat, e.latlng.lng];
    const field = RJ.activeField || "start";
    // Reverse-geocode for a friendly label; fall back to coordinates.
    setPoint(field, latlng, null);
    if (photon && photon.reverse) {
      photon.reverse(e.latlng, map.getZoom(), (results) => {
        if (results && results[0] && RJ[field]) {
          RJ[field].label = (results[0].name || "").split(",").slice(0, 2).join(",") || RJ[field].label;
          fieldInput(field).value = RJ[field].label;
        }
      });
    }
  }

  // ---- init --------------------------------------------------------------
  function init() {
    const btn = document.querySelector(".geocoder-route-btn");
    if (btn) {
      btn.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); open(); }, true);
    }
    map.on("click", onMapClick);
    // The route pane's X is wired in map.js (setupRoutingSheet -> closeRoutingPane),
    // which calls RoutingUI.close(). Don't rebind it here: init() runs at script-parse
    // time, while setupRoutingSheet runs after loadMarkers() resolves, so anything we
    // set now would be overwritten a moment later.
    // Esc closes the planner.
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && RJ.active) close(); });
    // A shared/deep route link reopens the same route on load and on back/forward.
    // The canonical form lives in the path, so back/forward onto it is a popstate,
    // not a hashchange; only reopen when the planner isn't already showing it.
    openFromUrl();
    const reopen = () => {
      const p = routeFromUrl();
      if (!p) return;
      if (RJ.active && RJ.start && RJ.dest &&
          RJ.start.latlng[0] === p.from[0] && RJ.start.latlng[1] === p.from[1] &&
          RJ.dest.latlng[0] === p.to[0] && RJ.dest.latlng[1] === p.to[1]) return;
      openFromUrl();
    };
    window.addEventListener("hashchange", reopen);
    window.addEventListener("popstate", reopen);
  }

  function waitFor(cond, cb, tries) {
    tries = tries || 0;
    if (cond()) { cb(); return; }
    if (tries > 200) return;
    setTimeout(() => waitFor(cond, cb, tries + 1), 50);
  }
  waitFor(() => window.map && document.querySelector(".geocoder-route-btn") && typeof L !== "undefined", init);
})();
