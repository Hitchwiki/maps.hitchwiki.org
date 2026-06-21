// Renders a trip's spots and route on a Leaflet map.
//
//   initTripMap(containerId, points, { interactive })
//
// `points` is [{lat, lon}, ...] in chronological order. We draw a small circle
// marker at every spot and connect them with a line that follows actual roads,
// fetched from the public OSRM demo server. If routing is unavailable (offline,
// rate-limited, a gap with no drivable road) we fall back to a smoothed curve so
// the connection still reads as a road rather than a ruler-straight line.
(function () {
  const ROUTE_COLOR = "#2d7dd2";
  const OSRM_MAX_WAYPOINTS = 25; // keep the demo-server URL and load reasonable

  function initTripMap(containerId, points, opts) {
    opts = opts || {};
    const interactive = !!opts.interactive;
    const el = document.getElementById(containerId);
    if (!el || !points || !points.length || typeof L === "undefined") return null;

    const latlngs = points.map((p) => [p.lat, p.lon]);

    const map = L.map(containerId, {
      zoomControl: interactive,
      attributionControl: interactive,
      scrollWheelZoom: interactive,
      doubleClickZoom: interactive,
      dragging: interactive,
      boxZoom: interactive,
      keyboard: interactive,
      touchZoom: interactive,
      tap: interactive,
    });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: interactive ? "&copy; OpenStreetMap" : "",
    }).addTo(map);

    // Fit to the spots immediately so something shows before routing returns.
    if (latlngs.length === 1) {
      map.setView(latlngs[0], 9);
    } else {
      map.fitBounds(L.latLngBounds(latlngs), { padding: [22, 22] });
    }

    // Small markers for every spot. On non-interactive thumbnails they're
    // click-through (interactive:false) so the whole card stays clickable.
    points.forEach((p) => {
      L.circleMarker([p.lat, p.lon], {
        radius: interactive ? 6 : 4,
        color: "#fff",
        weight: 2,
        fillColor: ROUTE_COLOR,
        fillOpacity: 1,
        interactive: interactive,
      }).addTo(map);
    });

    drawRoute(map, latlngs, interactive);
    return map;
  }

  function drawRoute(map, latlngs, interactive) {
    if (latlngs.length < 2) return;
    fetchOsrmGeometry(latlngs)
      .then((geometry) => {
        if (geometry && geometry.length > 1) {
          L.polyline(geometry, {
            color: ROUTE_COLOR,
            weight: interactive ? 4 : 3,
            opacity: 0.85,
            interactive: false,
          }).addTo(map);
        } else {
          drawCurved(map, latlngs, interactive);
        }
      })
      .catch(() => drawCurved(map, latlngs, interactive));
  }

  function fetchOsrmGeometry(latlngs) {
    const sampled = samplePoints(latlngs, OSRM_MAX_WAYPOINTS);
    const cacheKey = "triproute:" + JSON.stringify(sampled);
    try {
      const cached = sessionStorage.getItem(cacheKey);
      if (cached) return Promise.resolve(JSON.parse(cached));
    } catch (e) {}

    // OSRM expects lon,lat pairs.
    const coords = sampled.map((p) => `${p[1]},${p[0]}`).join(";");
    const url = `https://router.project-osrm.org/route/v1/driving/${coords}?overview=full&geometries=geojson`;
    return fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data || !data.routes || !data.routes.length) return null;
        const geom = data.routes[0].geometry.coordinates.map((c) => [c[1], c[0]]);
        try {
          sessionStorage.setItem(cacheKey, JSON.stringify(geom));
        } catch (e) {}
        return geom;
      });
  }

  // Pick at most `max` points spread evenly across the list (endpoints kept).
  function samplePoints(latlngs, max) {
    if (latlngs.length <= max) return latlngs;
    const step = (latlngs.length - 1) / (max - 1);
    const out = [];
    for (let i = 0; i < max; i++) out.push(latlngs[Math.round(i * step)]);
    return out;
  }

  // Fallback: a Catmull-Rom spline through the points so the connection curves
  // like a winding road instead of straight segments.
  function drawCurved(map, latlngs, interactive) {
    const curve = catmullRom(latlngs, 16);
    L.polyline(curve, {
      color: ROUTE_COLOR,
      weight: interactive ? 4 : 3,
      opacity: 0.85,
      lineCap: "round",
      lineJoin: "round",
      interactive: false,
    }).addTo(map);
  }

  function catmullRom(p, segments) {
    if (p.length < 3) return p; // nothing to smooth between just two points
    const res = [];
    for (let i = 0; i < p.length - 1; i++) {
      const p0 = p[i === 0 ? 0 : i - 1];
      const p1 = p[i];
      const p2 = p[i + 1];
      const p3 = p[i + 2 < p.length ? i + 2 : i + 1];
      for (let t = 0; t < segments; t++) {
        const s = t / segments;
        const s2 = s * s;
        const s3 = s2 * s;
        const lat =
          0.5 *
          (2 * p1[0] +
            (-p0[0] + p2[0]) * s +
            (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * s2 +
            (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * s3);
        const lng =
          0.5 *
          (2 * p1[1] +
            (-p0[1] + p2[1]) * s +
            (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * s2 +
            (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * s3);
        res.push([lat, lng]);
      }
    }
    res.push(p[p.length - 1]);
    return res;
  }

  window.initTripMap = initTripMap;
})();
