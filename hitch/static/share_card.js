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

  // ── projection ──────────────────────────────────────────────────────────────
  // Plain Web Mercator, in pixels at a given zoom (world = 256 * 2^z px).
  function lonToX(lon, z) {
    return ((lon + 180) / 360) * TILE * Math.pow(2, z);
  }
  function latToY(lat, z) {
    const s = Math.sin((Math.max(-85.05, Math.min(85.05, lat)) * Math.PI) / 180);
    return (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * TILE * Math.pow(2, z);
  }

  // Highest zoom at which both points still fit inside the map area with padding.
  function fitZoom(a, b) {
    for (let z = MAX_ZOOM; z >= MIN_ZOOM; z--) {
      const dx = Math.abs(lonToX(a.lon, z) - lonToX(b.lon, z));
      const dy = Math.abs(latToY(a.lat, z) - latToY(b.lat, z));
      if (dx <= CARD_W - 2 * MAP_PAD && dy <= MAP_H - 2 * MAP_PAD) return z;
    }
    return MIN_ZOOM;
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
  function drawRoute(ctx, from, to) {
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    // White casing under the coloured stroke so the line stays readable over both
    // pale fields and dark forest on the basemap.
    ctx.strokeStyle = "rgba(255,255,255,0.95)";
    ctx.lineWidth = 20;
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
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
  function build(ride) {
    const from = { lat: num(ride.pickupLat), lon: num(ride.pickupLon) };
    if (from.lat === null || from.lon === null) return Promise.reject(new Error("no pickup"));
    const dLat = num(ride.destLat);
    const dLon = num(ride.destLon);
    const to = dLat !== null && dLon !== null ? { lat: dLat, lon: dLon } : null;
    // A ride that crosses the antimeridian would otherwise span the whole world in
    // pixel space and zoom out to z=2; project the destination at the nearest
    // equivalent longitude and let the tile loop wrap the x index instead. Only the
    // projection uses it — `to.lon` stays in [-180,180] for Photon and haversine.
    const toProj = to
      ? { lat: to.lat, lon: to.lon + (Math.abs(to.lon - from.lon) > 180 ? (to.lon < from.lon ? 360 : -360) : 0) }
      : null;

    const facts = { waitMin: null, rideMin: null, distance: null };
    const wait = num(ride.waitMin);
    if (wait !== null) facts.waitMin = Math.round(wait);
    if (ride.departedAt && ride.arrivedAt) {
      const mins = Math.round((new Date(ride.arrivedAt) - new Date(ride.departedAt)) / 60000);
      if (isFinite(mins) && mins > 0) facts.rideMin = mins;
    }
    if (to) facts.distance = displayDistance(haversineKm(from, to));

    const canvas = document.createElement("canvas");
    canvas.width = CARD_W;
    canvas.height = CARD_H;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#dfe3e0"; // shows through wherever a tile failed to load
    ctx.fillRect(0, 0, CARD_W, MAP_H);

    const z = toProj ? fitZoom(from, toProj) : SOLO_ZOOM;
    const fx = lonToX(from.lon, z);
    const fy = latToY(from.lat, z);
    const tx = toProj ? lonToX(toProj.lon, z) : fx;
    const ty = toProj ? latToY(toProj.lat, z) : fy;
    const originX = (fx + tx) / 2 - CARD_W / 2;
    const originY = (fy + ty) / 2 - MAP_H / 2;

    const p1 = { x: fx - originX, y: fy - originY };
    const p2 = { x: tx - originX, y: ty - originY };

    return Promise.all([
      drawBasemap(ctx, z, originX, originY),
      loadLogo(),
      nearestTown(from.lat, from.lon),
      to ? nearestTown(to.lat, to.lon) : Promise.resolve(null),
    ]).then(function (res) {
      const logo = res[1];
      facts.fromName = res[2] || coordLabel(from.lat, from.lon);
      facts.toName = to ? res[3] || coordLabel(to.lat, to.lon) : null;

      if (to) drawRoute(ctx, p1, p2);
      drawPin(ctx, p1, GREEN);
      if (to) drawPin(ctx, p2, ORANGE);
      drawAttribution(ctx);
      drawPanel(ctx, facts, logo);

      // The ride has no permalink yet — it only gets one once the Nostr fetch cron
      // ingests it (/ride/<d_tag> 404s until then), so we share the starting spot,
      // whose page renders for any well-formed coordinate.
      const spotId = from.lat.toFixed(5) + "_" + from.lon.toFixed(5);
      const url = window.location.origin + "/spot/" + spotId;
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
