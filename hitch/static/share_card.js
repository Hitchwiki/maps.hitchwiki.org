// Renders the portrait "I hitchhiked X → Y" image that the success overlay offers
// for sharing. Everything happens on a <canvas> in the browser: the ride does not
// exist server-side yet at this point (it only reaches our DB once the Nostr cron
// picks it up, up to ~15 min later), so a server-rendered card is impossible here.
//
// Layout: OSM basemap fitted to the start + destination spots on top, a stats panel
// with the two nearest towns, wait/ride minutes and distance in the lower third, and
// the Hitchwiki Maps wordmark at the very bottom.
(function () {
  "use strict";

  const CARD_W = 1080;
  const CARD_H = 1350; // 4:5 — the tallest portrait ratio Instagram/WhatsApp show uncropped
  const PANEL_H = 450; // the "lower third"
  const MAP_H = CARD_H - PANEL_H;

  const TILE = 256;
  const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  const MAP_PAD = 150; // keep both pins clear of the edges and of the panel seam
  const MAX_ZOOM = 15;
  const MIN_ZOOM = 2;
  const SOLO_ZOOM = 13; // no destination logged: just frame the pickup spot

  const GREEN = "#2f8f46";
  const ORANGE = "#e8622c";
  const INK = "#1d1d1b";
  const MUTED = "#6b6b6b";

  const SANS = "'Helvetica Neue', Helvetica, Arial, sans-serif";

  // ── road routing ────────────────────────────────────────────────────────────
  // The same public OSRM the route planner (routing.js) and the trip map already
  // use. One request per card — i.e. per logged ride — which is a rounding error
  // next to what the planner sends.
  const OSRM_URL = "https://router.project-osrm.org/route/v1/driving/";
  const OSRM_TIMEOUT_MS = 5000; // in line with the 6 s tile timeout: never stall the card
  // overview=full, not simplified. Simplified thins an 863 km route down to 28
  // points — ~25 px apart on this card, which visibly cuts the corners off the
  // line that is the whole point of the feature. Full costs 35 KB there, against
  // the ~30 basemap tiles (several hundred KB) the same card already downloads.
  //
  // A driving route is normally 1.1-1.4x the crow flight. Anything past 3x is not
  // a detour but a wrong answer — OSRM bridging a sea crossing the rider actually
  // took by ferry, or snapping a sloppily logged destination onto the far side of
  // an estuary. Fall back to the straight line, which at least does not lie about
  // the roads taken.
  const MAX_DETOUR_RATIO = 3;
  // Under a kilometre the road line and the straight line are the same two pixels,
  // and the ratio guard above is meaningless at that scale. Skip the request.
  const MIN_ROUTE_KM = 1;

  // ── projection ──────────────────────────────────────────────────────────────
  // Plain Web Mercator, in pixels at a given zoom (world = 256 * 2^z px).
  function lonToX(lon, z) {
    return ((lon + 180) / 360) * TILE * Math.pow(2, z);
  }
  function latToY(lat, z) {
    const s = Math.sin((Math.max(-85.05, Math.min(85.05, lat)) * Math.PI) / 180);
    return (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * TILE * Math.pow(2, z);
  }

  // Highest zoom at which every point still fits inside the map area with padding.
  // It takes the whole path, not just the two ends: a road route that bows out —
  // around a bay, over a pass — would otherwise be framed on its endpoints and cut
  // off at the edge of the card.
  function fitZoom(points) {
    for (let z = MAX_ZOOM; z >= MIN_ZOOM; z--) {
      const b = pixelBounds(points, z);
      if (b.maxX - b.minX <= CARD_W - 2 * MAP_PAD && b.maxY - b.minY <= MAP_H - 2 * MAP_PAD) return z;
    }
    return MIN_ZOOM;
  }

  function pixelBounds(points, z) {
    const xs = points.map(function (p) { return lonToX(p.lon, z); });
    const ys = points.map(function (p) { return latToY(p.lat, z); });
    return {
      minX: Math.min.apply(null, xs),
      maxX: Math.max.apply(null, xs),
      minY: Math.min.apply(null, ys),
      maxY: Math.max.apply(null, ys),
    };
  }

  // A route crossing the antimeridian would span the whole world in pixel space and
  // zoom the card out to z=2. Express every longitude as the equivalent nearest to
  // the pickup instead (so 179 next to -179 becomes 181) and let the tile loop wrap
  // the x index. Only the projection sees these values; the real lon/lat go to
  // Photon and to the distance maths untouched.
  function unwrapLon(lon, refLon) {
    if (Math.abs(lon - refLon) <= 180) return lon;
    return lon + (lon < refLon ? 360 : -360);
  }

  // ── road route ──────────────────────────────────────────────────────────────
  // Google's encoded-polyline format, precision 5. OSRM will hand back GeoJSON
  // instead, but that is 6.6x the bytes for the identical line (Basel-Berlin at
  // overview=full: 35 KB against 228 KB), which is worth 25 lines of decoder.
  function decodePolyline(str) {
    const points = [];
    let i = 0;
    let lat = 0;
    let lon = 0;
    while (i < str.length) {
      let shift = 0;
      let result = 0;
      let b;
      do {
        b = str.charCodeAt(i++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      lat += result & 1 ? ~(result >> 1) : result >> 1;
      shift = 0;
      result = 0;
      do {
        b = str.charCodeAt(i++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      lon += result & 1 ? ~(result >> 1) : result >> 1;
      points.push({ lat: lat / 1e5, lon: lon / 1e5 });
    }
    return points;
  }

  // The driving route between the two spots, or null to fall back to the straight
  // line. Null on every failure path — a dead network, a slow response, a pair OSRM
  // cannot connect, or a route long enough to be obviously wrong — because a card
  // with a straight line is fine and a card that never appears is not.
  function roadGeometry(from, to, crowKm) {
    if (!(crowKm >= MIN_ROUTE_KM)) return Promise.resolve(null);
    const coords = from.lon + "," + from.lat + ";" + to.lon + "," + to.lat;
    const url = OSRM_URL + coords + "?overview=full&geometries=polyline";

    // AbortController rather than a bare Promise.race, so a stalled request is
    // actually torn down instead of left running behind the finished card.
    let controller = null;
    let timer = null;
    try {
      controller = new AbortController();
      timer = setTimeout(function () { controller.abort(); }, OSRM_TIMEOUT_MS);
    } catch (e) {
      controller = null;
    }

    return fetch(url, controller ? { signal: controller.signal } : undefined)
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || d.code !== "Ok" || !d.routes || !d.routes[0]) return null;
        const route = d.routes[0];
        const km = route.distance / 1000;
        if (km > crowKm * MAX_DETOUR_RATIO) return null;
        const points = decodePolyline(route.geometry || "");
        if (points.length < 2) return null;
        return { points: points, km: km };
      })
      .catch(function () { return null; })
      .then(function (result) {
        if (timer) clearTimeout(timer);
        return result;
      });
  }

  // ── tiles ───────────────────────────────────────────────────────────────────
  // crossOrigin is mandatory: without it the canvas is tainted and toBlob() throws,
  // so there would be no image to share. tile.openstreetmap.org sends
  // Access-Control-Allow-Origin: *, and our service worker's offline fallback tile
  // sets it too, so both the online and the offline path stay exportable.
  function loadTile(url) {
    return new Promise(function (resolve) {
      const img = new Image();
      img.crossOrigin = "anonymous";
      // A single dead tile must not stall the card — resolve with null and leave
      // that square on the background colour.
      const done = function (v) {
        clearTimeout(timer);
        resolve(v);
      };
      const timer = setTimeout(function () { done(null); }, 6000);
      img.onload = function () { done(img); };
      img.onerror = function () { done(null); };
      img.src = url;
    });
  }

  function drawBasemap(ctx, z, originX, originY) {
    const n = Math.pow(2, z);
    const x0 = Math.floor(originX / TILE);
    const x1 = Math.floor((originX + CARD_W) / TILE);
    const y0 = Math.floor(originY / TILE);
    const y1 = Math.floor((originY + MAP_H) / TILE);

    const jobs = [];
    for (let tx = x0; tx <= x1; tx++) {
      for (let ty = y0; ty <= y1; ty++) {
        if (ty < 0 || ty >= n) continue; // above the north / below the south edge
        const wx = ((tx % n) + n) % n; // wrap across the antimeridian
        const url = TILE_URL.replace("{z}", z).replace("{x}", wx).replace("{y}", ty);
        jobs.push(
          loadTile(url).then(function (img) {
            if (img) ctx.drawImage(img, tx * TILE - originX, ty * TILE - originY, TILE, TILE);
          })
        );
      }
    }
    return Promise.all(jobs);
  }

  // ── map decorations ─────────────────────────────────────────────────────────
  // path: [{x, y}, ...] — the road route when OSRM answered, otherwise the two
  // endpoints, which draws exactly the straight line this used to.
  function drawRoute(ctx, path) {
    if (path.length < 2) return;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(path[0].x, path[0].y);
    for (let i = 1; i < path.length; i++) ctx.lineTo(path[i].x, path[i].y);
    // White casing under the coloured stroke so the line stays readable over both
    // pale fields and dark forest on the basemap.
    ctx.strokeStyle = "rgba(255,255,255,0.95)";
    ctx.lineWidth = 20;
    ctx.stroke();
    ctx.strokeStyle = GREEN;
    ctx.lineWidth = 10;
    ctx.stroke();
  }

  function drawPin(ctx, p, color) {
    ctx.beginPath();
    ctx.arc(p.x, p.y, 26, 0, Math.PI * 2);
    ctx.fillStyle = "#fff";
    ctx.fill();
    ctx.beginPath();
    ctx.arc(p.x, p.y, 18, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  }

  function drawAttribution(ctx) {
    const text = "© OpenStreetMap contributors";
    ctx.font = "20px " + SANS;
    const w = ctx.measureText(text).width;
    ctx.fillStyle = "rgba(255,255,255,0.8)";
    ctx.fillRect(CARD_W - w - 28, MAP_H - 36, w + 28, 36);
    ctx.fillStyle = "#444";
    ctx.textAlign = "right";
    ctx.textBaseline = "alphabetic";
    ctx.fillText(text, CARD_W - 14, MAP_H - 11);
  }

  // ── panel ───────────────────────────────────────────────────────────────────
  // Shrink the font until the string fits maxW, so a long town pair never overflows.
  function fitFont(ctx, text, maxW, startPx, weight) {
    let px = startPx;
    while (px > 22) {
      ctx.font = (weight ? weight + " " : "") + px + "px " + SANS;
      if (ctx.measureText(text).width <= maxW) break;
      px -= 2;
    }
    return px;
  }

  function drawPanel(ctx, facts, logo) {
    const top = MAP_H;
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, top, CARD_W, PANEL_H);
    ctx.fillStyle = GREEN;
    ctx.fillRect(0, top, CARD_W, 8);

    ctx.textBaseline = "alphabetic";
    ctx.textAlign = "center";

    // Route line: "Basel → Dresden", or just the pickup town when no destination
    // was logged (a ride that only records where it started is still shareable).
    const route = facts.toName ? facts.fromName + "  →  " + facts.toName : facts.fromName;
    fitFont(ctx, route, CARD_W - 100, 62, "bold");
    ctx.fillStyle = INK;
    ctx.fillText(route, CARD_W / 2, top + 100);

    // Stats row — only the facts this ride actually has. A ride with no arrival
    // time logged shows two columns rather than an empty "0 min".
    const stats = [];
    if (facts.waitMin != null) stats.push([formatMinutes(facts.waitMin), "waiting"]);
    if (facts.rideMin != null) stats.push([formatMinutes(facts.rideMin), "on the road"]);
    if (facts.distance) stats.push([facts.distance, "travelled"]);

    if (stats.length) {
      const colW = CARD_W / stats.length;
      stats.forEach(function (s, i) {
        const cx = colW * i + colW / 2;
        fitFont(ctx, s[0], colW - 40, 58, "bold");
        ctx.fillStyle = GREEN;
        ctx.fillText(s[0], cx, top + 210);
        ctx.font = "26px " + SANS;
        ctx.fillStyle = MUTED;
        ctx.fillText(s[1].toUpperCase(), cx, top + 252);
      });
    }

    // Wordmark: logo + "Hitchwiki Maps", centred as one block.
    const label = "Hitchwiki Maps";
    ctx.font = "bold 44px " + SANS;
    const labelW = ctx.measureText(label).width;
    const logoW = logo ? Math.round((logo.width / logo.height) * 64) : 0;
    const gap = logo ? 20 : 0;
    const blockX = (CARD_W - (logoW + gap + labelW)) / 2;
    const baseY = top + PANEL_H - 78;
    if (logo) ctx.drawImage(logo, blockX, baseY - 50, logoW, 64);
    ctx.textAlign = "left";
    ctx.fillStyle = INK;
    ctx.fillText(label, blockX + logoW + gap, baseY);

    ctx.textAlign = "center";
    ctx.font = "26px " + SANS;
    ctx.fillStyle = MUTED;
    ctx.fillText("maps.hitchwiki.org", CARD_W / 2, top + PANEL_H - 32);
  }

  function loadLogo() {
    return new Promise(function (resolve) {
      const img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = function () { resolve(null); }; // wordmark alone still reads fine
      img.src = "/static/logo.png";
    });
  }

  // ── facts ───────────────────────────────────────────────────────────────────
  // The stashed ride comes straight from form fields, so an unfilled one is "" —
  // and +"" is 0, which would put a phantom destination off the coast of Ghana.
  // Anything not a real number becomes null.
  function num(v) {
    if (v === null || v === undefined || v === "") return null;
    const n = +v;
    return isFinite(n) ? n : null;
  }

  function formatMinutes(min) {
    if (min < 60) return min + " min";
    const h = Math.floor(min / 60);
    const m = min % 60;
    return m ? h + " h " + m + " min" : h + " h";
  }

  // Same great-circle distance show.py records for a ride, so the number on the
  // card matches the one the spot page will show later.
  function haversineKm(a, b) {
    const R = 6371;
    const dLat = ((b.lat - a.lat) * Math.PI) / 180;
    const dLon = ((b.lon - a.lon) * Math.PI) / 180;
    const la1 = (a.lat * Math.PI) / 180;
    const la2 = (b.lat * Math.PI) / 180;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  // Photon's `name` is whatever feature is nearest — often a street or a petrol
  // station, which is useless as a headline. CLAUDE.md's rule for the route-preview
  // script applies here too: prefer the administrative place fields.
  function nearestTown(lat, lon) {
    const url = "https://photon.komoot.io/reverse?lat=" + lat + "&lon=" + lon + "&limit=1";
    return fetch(url)
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        const p = (j && j.features && j.features[0] && j.features[0].properties) || {};
        return p.city || p.town || p.village || p.county || p.district || p.state || p.name || null;
      })
      .catch(function () { return null; });
  }

  function coordLabel(lat, lon) {
    return lat.toFixed(2) + ", " + lon.toFixed(2);
  }

  function displayDistance(km) {
    // Reuse the map's unit preference so a reader who set miles gets miles.
    const imperial = window.DISTANCE_UNIT === "imperial";
    const v = imperial ? km / 1.609344 : km;
    return (v >= 100 ? Math.round(v) : v.toFixed(1).replace(/\.0$/, "")) + (imperial ? " mi" : " km");
  }

  // ── public API ──────────────────────────────────────────────────────────────
  // ride: {pickupLat, pickupLon, destLat, destLon, waitMin, departedAt, arrivedAt}
  // Resolves to {blob, dataUrl, fromName, toName, text, url} — everything the
  // success overlay needs to preview and to hand to the Web Share API.
  function build(ride, dTag) {
    const from = { lat: num(ride.pickupLat), lon: num(ride.pickupLon) };
    if (from.lat === null || from.lon === null) return Promise.reject(new Error("no pickup"));
    const dLat = num(ride.destLat);
    const dLon = num(ride.destLon);
    const to = dLat !== null && dLon !== null ? { lat: dLat, lon: dLon } : null;
    const crowKm = to ? haversineKm(from, to) : null;

    const facts = { waitMin: null, rideMin: null, distance: null };
    const wait = num(ride.waitMin);
    if (wait !== null) facts.waitMin = Math.round(wait);
    if (ride.departedAt && ride.arrivedAt) {
      const mins = Math.round((new Date(ride.arrivedAt) - new Date(ride.departedAt)) / 60000);
      if (isFinite(mins) && mins > 0) facts.rideMin = mins;
    }

    const canvas = document.createElement("canvas");
    canvas.width = CARD_W;
    canvas.height = CARD_H;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#dfe3e0"; // shows through wherever a tile failed to load
    ctx.fillRect(0, 0, CARD_W, MAP_H);

    // The route has to be in hand before anything else: it decides the zoom, which
    // decides which tiles to fetch. So this one request is serial ahead of the rest
    // rather than alongside them — a second or so onto a build that already waits
    // on ~30 tiles and two reverse geocodes, spent behind the overlay's status line.
    return (to ? roadGeometry(from, to, crowKm) : Promise.resolve(null)).then(function (road) {
      // Longitudes unwrapped relative to the pickup, for projection only.
      const path = road
        ? road.points.map(function (p) { return { lat: p.lat, lon: unwrapLon(p.lon, from.lon) }; })
        : to
          ? [from, { lat: to.lat, lon: unwrapLon(to.lon, from.lon) }]
          : [from];
      // Headline the distance actually travelled when we know the roads taken; the
      // great-circle figure show.py records for the spot page is the fallback.
      if (road) facts.distance = displayDistance(road.km);
      else if (to) facts.distance = displayDistance(crowKm);

      const z = to ? fitZoom(path) : SOLO_ZOOM;
      const b = pixelBounds(path, z);
      const originX = (b.minX + b.maxX) / 2 - CARD_W / 2;
      const originY = (b.minY + b.maxY) / 2 - MAP_H / 2;
      const toPx = function (p) {
        return { x: lonToX(p.lon, z) - originX, y: latToY(p.lat, z) - originY };
      };

      const line = path.map(toPx);
      const p1 = line[0];
      const p2 = line[line.length - 1];

      return Promise.all([
        drawBasemap(ctx, z, originX, originY),
        loadLogo(),
        nearestTown(from.lat, from.lon),
        to ? nearestTown(to.lat, to.lon) : Promise.resolve(null),
      ]).then(function (res) {
        return { res: res, line: line, p1: p1, p2: p2 };
      });
    }).then(function (stage) {
      const res = stage.res;
      const logo = res[1];
      facts.fromName = res[2] || coordLabel(from.lat, from.lon);
      facts.toName = to ? res[3] || coordLabel(to.lat, to.lon) : null;

      const p1 = stage.p1;
      const p2 = stage.p2;
      if (to) drawRoute(ctx, stage.line);
      drawPin(ctx, p1, GREEN);
      if (to) drawPin(ctx, p2, ORANGE);
      drawAttribution(ctx);
      drawPanel(ctx, facts, logo);

      // The ride's own permalink. It resolves as soon as the submit POST returns —
      // the server writes the published event into the local DB rather than waiting
      // for the Nostr fetch cron. Falls back to the starting spot when no d tag
      // reached us: the offline outbox submits over fetch without navigating, and a
      // returning visitor can be running this file against a cached older page.
      const spotId = from.lat.toFixed(5) + "_" + from.lon.toFixed(5);
      const url = dTag
        ? window.location.origin + "/ride/" + encodeURIComponent(dTag)
        : window.location.origin + "/spot/" + spotId;
      const text = facts.toName
        ? "Check out my hitchhiking ride from " + facts.fromName + " to " + facts.toName
        : "Check out my hitchhiking ride from " + facts.fromName;

      return new Promise(function (resolve, reject) {
        canvas.toBlob(function (blob) {
          if (!blob) return reject(new Error("toBlob failed"));
          resolve({
            blob: blob,
            dataUrl: URL.createObjectURL(blob),
            fromName: facts.fromName,
            toName: facts.toName,
            text: text,
            url: url,
          });
        }, "image/png");
      });
    });
  }

  window.hmShareCard = { build: build };
})();
