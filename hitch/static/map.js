// Register ServiceWorker
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch((e) => console.error(e));
}

// Helpers and variables
var $$ = (e) => document.querySelector(e);
var allMarkers = [],
  destinationMarkers = [],
  active = [],
  oldActive = [],
  oldMarkers = [],
  destLineGroup = null,
  filterDestLineGroup = null,
  filterMarkerGroup = null,
  map,
  bars = document.querySelectorAll(".sidebar, .topbar"),
  heatmapLayer = null,
  heatmapData = null,
  heatmapActive = false,
  normalLayer = null,
  heatmapLegend = null,
  spotsData = null,
  ridesIndex = null;

// Create the Leaflet map synchronously so controls are in their final position immediately
function createMap() {
  map = L.map("map", {
    center: [0, 0],
    zoom: 1,
    preferCanvas: true,
    attributionControl: false,
    zoomControl: false,
  });
  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.control.attribution({ position: "bottomright" }).addTo(map);

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> | Data: <a href="/copyright">maps.hitchwiki.org</a> &amp; <a href="https://hitchmap.com/copyright.html">Hitchmap</a> (<a href="https://opendatacommons.org/licenses/odbl/">ODbL</a>)',
  }).addTo(map);

  return map;
}

// Load markers from JSON data
async function loadMarkers(map) {
  // If the template warrants a variation, load that variation, otherwise all points
  const url =
    typeof MAP_VARIATION !== "undefined"
      ? `/spots_${MAP_VARIATION}.json`
      : `/spots.json`;

  return fetch(url)
    .then((response) => response.json())
    .then((data) => {
      var markerCluster = L.markerClusterGroup({
        disableClusteringAtZoom: 7,
        spiderfyOnMaxZoom: false,
      });

      // Store spots data globally
      spotsData = data;
      console.log(`Loaded ${data.length} spots`);
      
      data.forEach((m, index) => {
        // Add error handling for malformed spot data
        if (!m.lat || !m.lon) {
          console.warn(`Skipping spot ${index}: missing coordinates`, m);
          return;
        }
        // Handle null/undefined rating with fallback
        const rating = m.rating || 3; // Default to 3 if no rating
        
        var color = {
          1: "red",
          2: "orange",
          3: "yellow",
          4: "lightgreen",
          5: "lightgreen",
        }[Math.round(rating)];
        var opacity = { 1: 0.3, 2: 0.4, 3: 0.6, 4: 0.8, 5: 0.8 }[Math.round(rating)];
        var coords = new L.latLng(m.lat, m.lon);

        var marker = L.circleMarker(coords, {
          radius: 5,
          weight: 1 + (m.review_count > 2),
          fillOpacity: opacity,
          color: "black",
          fillColor: color,
          // spots.json carries no explicit id (redundant with lat/lon); re-derive
          // it the same way generate_spot_id does in show.py (coords already rounded
          // to 5 decimals there) so it matches the rides/by-spot/<id>.json filename.
          spotId: `${m.lat.toFixed(4)}_${m.lon.toFixed(4)}`,
          _data: Object.assign({}, m, { rating: rating, text: "" })
        });

        marker.on("click", async (e) => await handleMarkerClick(marker, coords, e));
        if (m.review_count >= 3)
          marker.on("add", (_) => setTimeout((_) => marker.bringToFront(), 0));
        if (m.dest_lats?.length) destinationMarkers.push(marker);

        marker.addTo(markerCluster);
        allMarkers.push(marker);
      });

      markerCluster.addTo(map);
    })
    .catch((error) => {
      console.error("Error loading markers:", error);
      throw error;
    })
    .finally(() => {
      const overlay = document.getElementById("spots-loading-overlay");
      if (overlay) overlay.classList.add("hidden");
    });
}

// Slim per-ride index for filtering (user, comment excerpt, distance, recency,
// official spot, hitchwiki). Used for filtering and lat/lon/spot_id lookups.
// Full ride details (comments, popup HTML) come from per-spot files served at
// /rides/by-spot/<sid>.json, fetched lazily in handleMarkerClick().
async function loadRidesIndex() {
  if (ridesIndex) {
    return ridesIndex;
  }

  // Show the filter-pane spinner while the index downloads — the index is
  // several MB and noticeable on slow connections.
  const spinner = document.getElementById("filter-loading-spinner");
  if (spinner) spinner.style.display = "inline-block";

  try {
    const response = await fetch('/rides_index.json');
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    ridesIndex = await response.json();
    console.log(`Loaded ${ridesIndex.length} rides (index)`);
    return ridesIndex;
  } catch (error) {
    console.error("Error loading rides index:", error);
    return [];
  } finally {
    if (spinner) spinner.style.display = "none";
  }
}

// Load heatmap data (legend + image URL)
async function loadHeatmapData() {
  if (heatmapData) return heatmapData;

  try {
    const response = await fetch('/heatmap.json');
    if (!response.ok) throw new Error('Heatmap data not available');
    heatmapData = await response.json();
    return heatmapData;
  } catch (error) {
    console.warn('Could not load heatmap data:', error);
    return null;
  }
}

// Toggle heatmap layer (also updates ?heatmap= query param so the state is shareable)
async function toggleHeatmap() {
  if (heatmapActive) {
    await setHeatmapActive(false);
    setQueryParameter('heatmap', false);
  } else {
    const ok = await setHeatmapActive(true);
    if (ok) setQueryParameter('heatmap', true);
  }
}

// Apply or remove the heatmap layer/legend without touching the URL.
// Returns true if the requested state was reached.
async function setHeatmapActive(active) {
  const btn = $$('#heatmap-toggle-btn');
  const text = $$('#heatmap-toggle-text');
  const legendPane = document.getElementById('heatmap-legend-pane');

  if (!active) {
    if (heatmapLayer) map.removeLayer(heatmapLayer);
    if (legendPane) legendPane.style.display = 'none';
    positionLegendPane();
    if (btn) btn.classList.remove('active');
    if (text) text.textContent = 'Heatmap';
    heatmapActive = false;
    return true;
  }

  if (!heatmapData) {
    heatmapData = await loadHeatmapData();
    if (!heatmapData) {
      alert('Heatmap data is not available');
      return false;
    }
  }

  if (!heatmapLayer) {
    heatmapLayer = L.imageOverlay(
      heatmapData.image_url,
      heatmapData.bounds,
      { opacity: 0.7, pane: "heatmap" }
    );
  }

  populateHeatmapLegend(heatmapData.legend);
  if (legendPane) legendPane.style.display = 'block';
  positionLegendPane();

  heatmapLayer.addTo(map);
  if (btn) btn.classList.add('active');
  if (text) text.textContent = 'Normal';
  heatmapActive = true;
  return true;
}

// Position the heatmap legend pane below the filter pane
function positionLegendPane() {
  var legendPane = document.getElementById('heatmap-legend-pane');
  var filterPane = document.getElementById('filter-pane');
  if (!legendPane || legendPane.style.display === 'none') return;
  if (filterPane) {
    var rect = filterPane.getBoundingClientRect();
    legendPane.style.top = (rect.bottom + 8) + 'px';
  }
}

// Populate the heatmap legend pane with data
function populateHeatmapLegend(legendData) {
  const gradient = document.getElementById('legend-gradient');
  const labels = document.getElementById('legend-labels');
  const uncertaintyGradient = document.getElementById('uncertainty-gradient');

  if (!gradient || !labels) return;

  labels.innerHTML = `<span>${legendData.vmin}</span><span>${legendData.vmax}</span>`;

  const colors = legendData.colors.map(color => {
    if (Array.isArray(color) && color.length >= 3) {
      return `rgb(${Math.round(color[0] * 255)}, ${Math.round(color[1] * 255)}, ${Math.round(color[2] * 255)})`;
    } else if (typeof color === 'string') {
      return color;
    } else {
      return 'rgb(128, 128, 128)';
    }
  });
  gradient.style.background = `linear-gradient(to right, ${colors.join(', ')})`;

  if (uncertaintyGradient) {
    uncertaintyGradient.style.background = `linear-gradient(to right, rgba(74, 144, 226, 0.3), rgba(74, 144, 226, 1.0))`;
  }
}

// Initialize the map and set up event listeners
(async () => {
  // Create map + geocoder synchronously so zoom/search appear in final position immediately
  map = createMap();
  setupGeocoder();

  // Load markers asynchronously
  await loadMarkers(map);

  setupEventListeners();
  
  // Set up filter pane collapse toggle
  var filterCollapseBtn = document.getElementById('filter-collapse-btn');
  var filterPaneEl = document.getElementById('filter-pane');
  if (filterCollapseBtn && filterPaneEl) {
    // Also allow clicking the header text to toggle
    filterCollapseBtn.closest('.filter-pane-header').addEventListener('click', function() {
      filterPaneEl.classList.toggle('collapsed');
      // Reposition legend after collapse animation
      setTimeout(positionLegendPane, 250);
    });
  }

  // Set up heatmap legend collapse toggle
  var legendCollapseBtn = document.getElementById('legend-collapse-btn');
  var legendPaneEl = document.getElementById('heatmap-legend-pane');
  if (legendCollapseBtn && legendPaneEl) {
    legendCollapseBtn.closest('.filter-pane-header').addEventListener('click', function() {
      legendPaneEl.classList.toggle('collapsed');
    });
  }

  // Set up heatmap toggle
  const heatmapBtn = $$('#heatmap-toggle-btn');
  if (heatmapBtn) {
    heatmapBtn.addEventListener('click', toggleHeatmap);
  }

  // These functions make the navigation work
  handleHashChange();
  window.onhashchange = navigate;
  // Spot selection now lives in ?lat=&lon= query params (changed via
  // pushState), so back/forward fires popstate rather than hashchange — listen
  // for it too, otherwise navigating history wouldn't update the map.
  window.addEventListener("popstate", navigate);
  navigate();
  
  // Focus on search input after page loads
  setTimeout(() => {
    const textFilterInput = document.getElementById('text-filter');
    if (textFilterInput) {
      textFilterInput.focus();
    }
  }, 500);

})();


// Set up the geocoder for location search
function setupGeocoder() {
  var geocoderOpts = {
    collapsed: false,
    defaultMarkGeocode: false,
    position: "topleft",
    provider: "photon",
    placeholder: "Search",
    zoom: 11,
    geocoder: L.Control.Geocoder.photon(),
  };

  let geocoderController = L.Control.geocoder(geocoderOpts).addTo(map);
  let geocoderInput = $$(".leaflet-control-geocoder input");
  geocoderInput.type = "search";


  geocoderController.on("markgeocode", function (e) {
    var zoom = geocoderOpts.zoom || map.getZoom();
    map.setView(e.geocode.center, zoom);
    geocoderInput.value = "";
  });
}

// Set up various event listeners for the map and UI elements
function setupEventListeners() {
  $$("#sb-close").onclick = navigateHome;
  setupSpotSheet();
  setupMenuSheet();
  setupRoutingSheet();
  const reportDup = $$(".report-dup");
  if (reportDup) reportDup.onclick = () =>
    document.body.classList.add("reporting-duplicate");
  $$(".topbar.duplicate button").onclick = () =>
    document.body.classList.remove("reporting-duplicate");


  map.on("click", handleMapClick);
  map.on("zoom", () =>
    document.body.classList.toggle("zoomed-out", map.getZoom() < 9)
  );

  clearFilters.onclick = () => {
    clearParams();
    navigateHome();
  };

  setupFilterEventListeners();

  // Bottom action pane handlers
  var addSpotBtn = document.getElementById('action-add-spot');
  if (addSpotBtn) {
    addSpotBtn.addEventListener('click', function() {
      window.location.href = "/ride";
    });
  }

  var menuBtn = document.getElementById('action-menu');
  if (menuBtn) {
    menuBtn.addEventListener('click', function() {
      if (document.body.classList.contains("menu")) {
        bar();
        document.body.classList.remove("menu");
      } else {
        clearSpotUrl();
        bar(".sidebar.menu");
        document.body.classList.add("menu");
        updateBottomPaneVar();
        setSheetSnap($$(".sidebar.menu"), "full", MENU_SHEET_SNAPS);
      }
    });
  }


  var routeBtn = document.getElementById('action-route');
  if (routeBtn) {
    routeBtn.addEventListener('click', function() {
      window.location.hash = '#routing';
    });
  }

  let filterMapPane = map.createPane("filtering");
  filterMapPane.style.zIndex = 450;

  map.createPane("arrowlines");
  filterMapPane.style.zIndex = 1450;

  // Dedicated pane for the heatmap image overlay so it stays visible while
  // filtering (the filtering CSS hides .leaflet-overlay-pane).
  let heatmapPane = map.createPane("heatmap");
  heatmapPane.style.zIndex = 350;
}

// Handle map click events
function handleMapClick(e) {
  var added = false;
  if (window.innerWidth < 780) {
    var layerPoint = map.latLngToLayerPoint(e.latlng);
    let markers = document.body.classList.contains("filtering")
      ? filterMarkerGroup
      : allMarkers;
    var circles = markers.sort(
      (a, b) =>
        a.getLatLng().distanceTo(e.latlng) - b.getLatLng().distanceTo(e.latlng)
    );
    if (
      circles[0] &&
      map.latLngToLayerPoint(circles[0].getLatLng()).distanceTo(layerPoint) < 20
    ) {
      added = true;
      circles[0].fire("click", e);
    }
  }

  if (
    !added &&
    !document.body.classList.contains("reporting-duplicate") &&
    $$(".sidebar.visible") &&
    !$$(".sidebar.spot-form-container.visible")
  ) {
    navigateHome();
  }

  L.DomEvent.stopPropagation(e);
}

// Set up event listeners for filter controls
function setupFilterEventListeners() {
  recentToggle.addEventListener("input", () =>
    setQueryParameter("recent", recentToggle.checked)
  );
  osmToggle.addEventListener("input", () =>
    setQueryParameter("osmonly", osmToggle.checked)
  );
  carPoolingToggle.addEventListener("input", () =>
    setQueryParameter("carpoolingonly", carPoolingToggle.checked)
  );
  hitchwikiToggle.addEventListener("input", () =>
    setQueryParameter("hitchwikionly", hitchwikiToggle.checked)
  );
  userFilter.addEventListener("input", () =>
    setQueryParameter("user", userFilter.value)
  );
  textFilter.addEventListener("input", () =>
    setQueryParameter("text", textFilter.value)
  );
  distanceFilter.addEventListener("input", () =>
    setQueryParameter("mindistance", distanceFilter.value)
  );
  minRidesFilter.addEventListener("input", () =>
    setQueryParameter("minrides", minRidesFilter.value)
  );
  vehicleFilter.addEventListener("change", () =>
    setQueryParameter("vehicle", vehicleFilter.value)
  );
  methodFilter.addEventListener("change", () =>
    setQueryParameter("method", methodFilter.value)
  );
  minDateFilter.addEventListener("change", () =>
    setQueryParameter("mindate", minDateFilter.value)
  );
  maxDateFilter.addEventListener("change", () =>
    setQueryParameter("maxdate", maxDateFilter.value)
  );
}

// Handle changes in the URL hash; used for initialization of the map
function handleHashChange() {
  if (!window.location.hash.includes(",")) {
    if (!restoreView.apply(map)) {
      map.fitBounds([
        [-35, -40],
        [60, 40],
      ]);
    }
  }

  if (window.location.hash == "#success") {
    history.replaceState(null, null, " ");
    showSuccessOverlay();
  }

  if (window.location.hash == "#success-duplicate") {
    history.replaceState(null, null, " ");
    bar(".sidebar.success-duplicate");
  }

  if (window.location.hash == "#failed") {
    history.replaceState(null, null, " ");
    bar(".sidebar.failed");
  }

  if (window.location.hash == "#registered") {
    history.replaceState(null, null, " ");
    bar(".sidebar.registered");
  }

  if (window.location.pathname === "/hitchhiking.html") {
    var actionAddSpot = document.getElementById('action-add-spot');
    if (actionAddSpot) actionAddSpot.remove();
    var filterPaneEl = document.getElementById('filter-pane');
    if (filterPaneEl) filterPaneEl.remove();
  }

  if (map.getZoom() > 17 && window.location.hash != "#success-duplicate")
    map.setZoom(17);
}

// View functions
function reportDuplicate(marker) {
  if (document.body.classList.contains("reporting-duplicate")) {
    var data = marker.options._data,
      point = marker.getLatLng();

    let activePoint = active[0].getLatLng();

    if (activePoint.equals(point)) {
      alert("A marker cannot be a duplicate of itself.");
      return;
    }

    if (confirm(`Are you sure you want to report a duplicate?`)) {
      document.body.innerHTML += `<form id=dupform method=POST action=report-duplicate><input name=report value=${[
        activePoint.lat,
        activePoint.lng,
        data.lat,
        data.lon,
      ].join(",")}>`;
      document.querySelector("#dupform").submit();
    }
  }
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatRideDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function formatRideDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return d.toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function highlightStars(stars, upTo) {
  stars.forEach((s) => {
    s.classList.toggle("active", Number(s.dataset.rate) <= upTo);
  });
}

function renderRideCards(rides) {
  if (!rides.length) return "";
  return rides.map((r) => {
    const rating = r.rating > 0 ? "&nbsp;" + "⭐".repeat(r.rating) : "";
    const wait = r.wait != null && !Number.isNaN(r.wait) ? `${r.wait} min wait` : "";
    const date = formatRideDate(r.ride_datetime || r.submission_time);
    const metaBits = [date, wait].filter(Boolean).join(" · ");
    const startTime = r.ride_datetime ? formatRideDateTime(r.ride_datetime) : "";
    const timesLine = startTime
      ? `<div class="ride-times" style="font-size:0.85em; color:#666;">▶ ${startTime}</div>`
      : "";
    const name = r.hitchhiker_name && r.hitchhiker_name !== "Anonymous"
      ? `<a class="hitchhiker-name" href="/account/${encodeURIComponent(r.hitchhiker_name)}">${escapeHtml(r.hitchhiker_name)}</a>`
      : `<span class="hitchhiker-name">Anonymous</span>`;
    const comment = r.comment ? `<div class="ride-comment">${escapeHtml(r.comment)}</div>` : "";
    const href = r.id ? `/ride/${encodeURIComponent(r.id)}` : "";
    const clickable = href ? ` data-ride-href="${href}" role="link" tabindex="0" style="cursor:pointer;"` : "";
    return `
      <div class="ride-card"${clickable}>
        <div class="ride-meta">${metaBits}${rating} &mdash; ${name}</div>
        ${timesLine}
        ${comment}
      </div>`;
  }).join("");
}

// Navigate to ride detail page when a ride-card is clicked, except when the
// click lands on a nested link (e.g. the hitchhiker username).
document.addEventListener("click", (e) => {
  const card = e.target.closest(".ride-card[data-ride-href]");
  if (!card) return;
  if (e.target.closest("a")) return;
  window.location.href = card.dataset.rideHref;
});

function summaryText(data) {
  const osmLink = data.osm_id ? `<br>🚏 <a href="https://www.openstreetmap.org/node/${data.osm_id}" target="_blank" rel="noopener noreferrer">Official hitchhiking spot</a>` : '';
  const carPoolingLink = data.car_pooling
    ? `<br>🚗 <a href="https://www.openstreetmap.org/${data.car_pooling.osm_type}/${data.car_pooling.id}" target="_blank" rel="noopener noreferrer">Car pooling spot</a>`
    : '';
  const hitchwikiLink = data.hitchwiki_article
    ? `<br>📄 <a href="${data.hitchwiki_article}" target="_blank" rel="noopener noreferrer">Mentioned on Hitchwiki</a>`
    : '';
  const hitchwikiMapLink = data.hitchwiki_map
    ? `<br>🗺️ <a href="${data.hitchwiki_map}" target="_blank" rel="noopener noreferrer">On Hitchwiki</a>`
    : '';
  
  return `Rating: ${data.rating && data.rating.toFixed(0)}/5<br>Waiting time: ${
      !data.wait || Number.isNaN(data.wait) ? "-" : data.wait.toFixed(0) + " min"
    }<br>Ride distance: ${
      !data.distance || Number.isNaN(data.distance) ? "-" : data.distance.toFixed(0) + " km"
    }${osmLink}${carPoolingLink}${hitchwikiLink}${hitchwikiMapLink}`;
}

async function handleMarkerClick(marker, point, e) {
  if ($$(".topbar.visible") || $$(".sidebar.spot-form-container.visible"))
    return;

  // Stop propagation synchronously — otherwise the click bubbles to the map
  // (handleMapClick) before the awaits below resolve, and on desktop the map
  // handler closes the spot pane we just opened.
  if (e) L.DomEvent.stopPropagation(e);

  reportDuplicate(marker);
  setSpotUrl(point.lat, point.lng);

  // Show the spot pane immediately with a loading spinner for rides
  markerClick(marker);

  // Load rides for this spot from the per-spot detail file.
  const spotId = marker.options.spotId;
  let spotRides = [];
  try {
    const resp = await fetch(`/rides/by-spot/${encodeURIComponent(spotId)}.json`);
    if (resp.ok) {
      const payload = await resp.json();
      // Current files are {spot, rides}; tolerate the older bare-array shape
      // so clicks keep working while a regeneration is still pending.
      if (Array.isArray(payload)) {
        spotRides = payload;
      } else {
        spotRides = payload.rides || [];
        // Click-time spot info (wait/distance averages, OSM / car-pooling /
        // Hitchwiki links) ships in the per-spot file, not spots.json.
        Object.assign(marker.options._data, payload.spot || {});
      }
    } else if (resp.status !== 404) {
      console.error(`Failed to load rides for spot ${spotId}: HTTP ${resp.status}`);
    }
  } catch (error) {
    console.error(`Error loading rides for spot ${spotId}:`, error);
  }

  // Sort newest-first by submission time so the freshest ride is at the top
  spotRides.sort((a, b) => {
    const ta = Date.parse(a.submission_time || a.ride_datetime || 0) || 0;
    const tb = Date.parse(b.submission_time || b.ride_datetime || 0) || 0;
    return tb - ta;
  });

  marker.options._data.rides = spotRides;

  // Re-render the summary now that the fetched spot details are merged in
  // (the first render in markerClick only had the slim spots.json fields).
  $$("#spot-summary").innerHTML = summaryText(marker.options._data);

  // Update rides content now that the fetch is complete
  $$("#spot-text").innerHTML = renderRideCards(spotRides);
  if (spotRides.length === 0 && (!marker.options._data.distance || Number.isNaN(marker.options._data.distance)))
    $$("#extra-text").innerHTML = "No comments/ride info.";
  else $$("#extra-text").innerHTML = "";
}

function markerClick(marker) {
  var data = marker.options._data;
  active = [marker];

  renderPoints();

  bar(".sidebar.show-spot");
  updateBottomPaneVar();
  setSpotSheetSnap("full");
  $$("#spot-header").innerText = `${data.lat.toFixed(4)}, ${data.lon.toFixed(4)}`;
  $$("#spot-google-link").href = window.ontouchstart
    ? `geo:${data.lat},${data.lon}`
    : `https://www.google.com/maps/place/${data.lat},${data.lon}`;
  $$("#spot-osm-link").href =
    `https://www.openstreetmap.org/?mlat=${data.lat}&mlon=${data.lon}#map=18/${data.lat}/${data.lon}`;

  $$("#spot-summary").innerHTML = summaryText(data);

  // Show a loading spinner while rides are fetched asynchronously
  $$("#spot-text").innerHTML = '<div class="spot-loading" role="status" aria-live="polite"><i class="fa-solid fa-circle-notch fa-spin" aria-hidden="true"></i><span class="sr-only">Loading rides</span></div>';
  $$("#extra-text").innerHTML = "";

  // Star rating prompt — clicking a star jumps straight into the ride form
  // with the chosen rating preselected and the spot's coords as pickup
  const stars = document.querySelectorAll("#spot-rate-stars .rate-star");
  stars.forEach((star) => {
    star.onmouseenter = () => highlightStars(stars, Number(star.dataset.rate));
    star.onmouseleave = () => highlightStars(stars, 0);
    star.onclick = () => {
      const rate = Number(star.dataset.rate);
      const formData = {
        pickup_lat: data.lat,
        pickup_lon: data.lon,
        destination_lat: "",
        destination_lon: "",
        rate: rate,
      };
      sessionStorage.setItem("rideFormData", JSON.stringify(formData));
      window.location.href = "/ride";
    };
  });
  highlightStars(stars, 0);

  // Share button
  // Put the coordinates in query params, not the #fragment: many messengers
  // strip the fragment when auto-linking a pasted URL, so a `/#lat,lon` link
  // arrives without coordinates. `?lat=&lon=` survives and navigate() reads it.
  const spotUrl = `${location.origin}/?lat=${data.lat}&lon=${data.lon}`;
  const shareText = `Hitchhiking spot at ${data.lat.toFixed(4)}, ${data.lon.toFixed(4)}`;
  const shareBtn = $$("#share-spot-btn");
  const shareMenu = $$("#share-spot-menu");

  if (navigator.share) {
    shareMenu.hidden = true;
    shareBtn.onclick = () => navigator.share({ title: shareText, url: spotUrl });
  } else {
    shareBtn.onclick = (e) => {
      e.stopPropagation();
      shareMenu.hidden = !shareMenu.hidden;
    };
    document.addEventListener('click', () => { shareMenu.hidden = true; }, { once: false });

    $$("#share-copy-link").onclick = (e) => {
      e.preventDefault();
      navigator.clipboard.writeText(spotUrl).then(() => {
        const orig = $$("#share-copy-link").textContent;
        $$("#share-copy-link").textContent = 'Copied!';
        setTimeout(() => { $$("#share-copy-link").textContent = orig; }, 1500);
      });
      shareMenu.hidden = true;
    };

    $$("#share-whatsapp").href = `https://wa.me/?text=${encodeURIComponent(shareText + ' ' + spotUrl)}`;
    $$("#share-telegram").href = `https://t.me/share/url?url=${encodeURIComponent(spotUrl)}&text=${encodeURIComponent(shareText)}`;
    $$("#share-signal").href = `sgnl://send?text=${encodeURIComponent(shareText + ' ' + spotUrl)}`;
  }
}

function bar(selector) {
  bars.forEach(function (el) {
    el.classList.remove("visible");
  });
  if (selector) $$(selector).classList.add("visible");
}

// Snap percentages mirror the CSS translateY values for .snap-{peek,half,full}
const SPOT_SHEET_SNAPS = { peek: 80, half: 60, full: 10 };
const MENU_SHEET_SNAPS = { half: 55, full: 0 };
const ROUTING_SHEET_SNAPS = { half: 55, full: 0 };

function setSheetSnap(sheet, name, snaps) {
  if (!sheet) return;
  for (const k in snaps) sheet.classList.remove("snap-" + k);
  sheet.classList.remove("dragging");
  sheet.classList.add("snap-" + name);
  sheet.style.transform = "";
}

// Backward-compat shim for the spot sheet — referenced by the rest of the file.
function setSpotSheetSnap(name) {
  setSheetSnap($$(".sidebar.show-spot"), name, SPOT_SHEET_SNAPS);
}

function setupBottomSheet({ sheet, handle, snaps, defaultSnap, onClose }) {
  if (!sheet || !handle) return;

  const orderedSnapNames = Object.keys(snaps).sort((a, b) => snaps[a] - snaps[b]); // top → bottom
  const FLING_THRESHOLD = 0.5; // px/ms

  let dragStartY = 0;
  let dragStartPct = snaps[defaultSnap];
  let currentPct = dragStartPct;
  let dragging = false;
  let pointerId = null;
  let samples = [];

  const recordSample = (y) => {
    const t = performance.now();
    samples.push({ y, t });
    // Only keep samples from the last 100ms to estimate end-of-gesture velocity
    while (samples.length > 1 && t - samples[0].t > 100) samples.shift();
  };

  // Returns px/ms, positive = moving down (closing direction)
  const computeVelocity = () => {
    if (samples.length < 2) return 0;
    const a = samples[0];
    const b = samples[samples.length - 1];
    const dt = b.t - a.t;
    if (dt <= 0) return 0;
    return (b.y - a.y) / dt;
  };

  const currentSnapName = () => {
    for (const name of orderedSnapNames) {
      if (sheet.classList.contains("snap-" + name)) return name;
    }
    return defaultSnap;
  };

  const close = () => {
    sheet.classList.remove("dragging");
    sheet.style.transform = "";
    if (onClose) onClose();
  };

  const onPointerDown = (e) => {
    dragging = true;
    pointerId = e.pointerId;
    handle.setPointerCapture(pointerId);
    sheet._sheetHeight = sheet.getBoundingClientRect().height;
    dragStartPct = snaps[currentSnapName()];
    currentPct = dragStartPct;
    dragStartY = e.clientY;
    sheet.classList.add("dragging");
    samples = [];
    recordSample(e.clientY);
  };

  const onPointerMove = (e) => {
    if (!dragging) return;
    const dy = e.clientY - dragStartY;
    const pct = dragStartPct + (dy / sheet._sheetHeight) * 100;
    currentPct = Math.max(0, Math.min(95, pct));
    sheet.style.transform = `translateY(${currentPct}%)`;
    recordSample(e.clientY);
  };

  const onPointerUp = () => {
    if (!dragging) return;
    dragging = false;
    if (pointerId !== null) {
      try { handle.releasePointerCapture(pointerId); } catch (_) {}
      pointerId = null;
    }

    const velocity = computeVelocity();
    const currentIdx = orderedSnapNames.indexOf(currentSnapName());
    const lastIdx = orderedSnapNames.length - 1;

    // Fling: jump one snap in the swipe direction; close on a hard down-fling
    // from the bottom-most snap (or if the user dragged it most of the way off).
    if (Math.abs(velocity) > FLING_THRESHOLD) {
      if (velocity > 0) {
        if (currentIdx === lastIdx || currentPct > 75) return close();
        setSheetSnap(sheet, orderedSnapNames[Math.min(lastIdx, currentIdx + 1)], snaps);
      } else {
        setSheetSnap(sheet, orderedSnapNames[Math.max(0, currentIdx - 1)], snaps);
      }
      return;
    }

    // Slow release: close if dragged near the bottom, otherwise snap to nearest.
    if (currentPct > 90) return close();
    let nearest = orderedSnapNames[0];
    let bestDist = Infinity;
    for (const name of orderedSnapNames) {
      const d = Math.abs(snaps[name] - currentPct);
      if (d < bestDist) { bestDist = d; nearest = name; }
    }
    setSheetSnap(sheet, nearest, snaps);
  };

  handle.addEventListener("pointerdown", onPointerDown);
  handle.addEventListener("pointermove", onPointerMove);
  handle.addEventListener("pointerup", onPointerUp);
  handle.addEventListener("pointercancel", onPointerUp);
}

// Bottom-sheet sheets sit above the bottom action pane via
// `bottom: var(--bottom-pane-h)`. The pane's height depends on web fonts and
// the iOS safe-area inset, so we measure it lazily and refresh on each open.
function updateBottomPaneVar() {
  const pane = $$("#bottom-action-pane");
  const h = pane ? pane.getBoundingClientRect().height : 0;
  if (h > 0) {
    document.documentElement.style.setProperty("--bottom-pane-h", h + "px");
  }
}

function setupSpotSheet() {
  const sheet = $$(".sidebar.show-spot");
  const closeBtn = $$("#spot-close");
  if (!sheet) return;
  if (closeBtn) closeBtn.onclick = navigateHome;

  updateBottomPaneVar();
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(updateBottomPaneVar);
  }
  window.addEventListener("resize", updateBottomPaneVar);
  window.addEventListener("orientationchange", updateBottomPaneVar);

  setupBottomSheet({
    sheet,
    handle: $$("#spot-sheet-handle"),
    snaps: SPOT_SHEET_SNAPS,
    defaultSnap: "half",
    onClose: navigateHome,
  });
}

function setupMenuSheet() {
  const closeMenu = () => { bar(); document.body.classList.remove("menu"); };
  const closeBtn = $$("#menu-close");
  if (closeBtn) closeBtn.onclick = closeMenu;
  setupBottomSheet({
    sheet: $$(".sidebar.menu"),
    handle: $$("#menu-sheet-handle"),
    snaps: MENU_SHEET_SNAPS,
    defaultSnap: "half",
    onClose: closeMenu,
  });
}

function setupRoutingSheet() {
  const closeBtn = $$("#routing-close");
  if (closeBtn) closeBtn.onclick = navigateHome;
  setupBottomSheet({
    sheet: $$(".sidebar.routing"),
    handle: $$("#routing-sheet-handle"),
    snaps: ROUTING_SHEET_SNAPS,
    defaultSnap: "half",
    onClose: navigateHome,
  });
}

function showSuccessOverlay() {
  const overlay = $$("#success-overlay");
  if (overlay) {
    overlay.style.display = "flex";
    
    // Add click handler for the close button
    const closeBtn = $$("#success-close-btn");
    if (closeBtn) {
      closeBtn.onclick = function() {
        overlay.style.display = "none";
      };
    }
    
    // Close overlay when clicking outside the content
    overlay.onclick = function(e) {
      if (e.target === overlay) {
        overlay.style.display = "none";
      }
    };
  }
}



function arrowLine(from, to, opts = {}) {
  return L.polylineDecorator([from, to], {
    patterns: [
      {
        repeat: 10,
        symbol: L.Symbol.arrowHead({
          pixelSize: 7,
          polygon: true,
          pathOptions: {
            stroke: false,
            fill: true,
            fillOpacity: 0.6,
            fillColor: "black",
            pane: "arrowlines",
          },
        }),
        offset: 16,
        endOffset: 0,
      },
    ],
  });
}

function renderPoints() {
  if (destLineGroup) destLineGroup.remove();

  destLineGroup = L.layerGroup();

  let opts = document.body.classList.contains("filtering")
    ? { pane: "filtering" }
    : {};

  for (let a of active) {
    let lats = a.options._data.dest_lats;
    let lons = a.options._data.dest_lons;
    if (lats && lats.length) {
      for (let i in lats) {
        arrowLine(a.getLatLng(), [lats[i], lons[i]], opts).addTo(destLineGroup);
      }
    }
  }

  destLineGroup.addTo(map);

  oldActive = active;
}

function navigateHome() {
  clearSpotUrl();
  navigate(); // clears rest
}

function clear() {
  bar();
  active = [];
  renderPoints();
  document.body.classList.remove("adding-spot", "reporting-duplicate", "menu");
}

function restoreView() {
  if (!storageAvailable("localStorage")) {
    return false;
  }
  var storage = window.localStorage;
  if (!this.__initRestore) {
    this.on(
      "moveend",
      function (e) {
        if (!this._loaded) return; // Never access map bounds if view is not set.

        var view = {
          lat: this.getCenter().lat,
          lng: this.getCenter().lng,
          zoom: this.getZoom(),
        };
        storage["mapView"] = JSON.stringify(view);
      },
      this
    );
    this.__initRestore = true;
  }

  var view = storage["mapView"];
  try {
    view = JSON.parse(view || "");
    this.setView(L.latLng(view.lat, view.lng), view.zoom, true);
    return true;
  } catch (err) {
    return false;
  }
}

function storageAvailable(type) {
  try {
    var storage = window[type],
      x = "__storage_test__";
    storage.setItem(x, x);
    storage.removeItem(x);
    return true;
  } catch (e) {
    console.warn("Your browser blocks access to " + type);
    return false;
  }
}

function exportAsGPX() {
  var script = document.createElement("script");
  script.src = "https://cdn.jsdelivr.net/npm/togpx@0.5.4/togpx.js";
  script.onload = function () {
    let features = allMarkers.map((m) => ({
      type: "Feature",
      properties: {
        text: summaryText(m.options._data) + "\n\n" + m.options._data.text,
        url: `https://maps.hitchwiki.org/${m.options._data.lat},${m.options._data.lon}`,
      },
      geometry: {
        coordinates: [m.options._data.lon, m.options._data.lat],
        type: "Point",
      },
    }));
    let geojson = {
      type: "FeatureCollection",
      features,
    };

    let div = document.createElement("div");
    function toPlainText(html) {
      div.innerHTML = html.replace(/\<(b|h)r\>/g, "\n");
      return div.textContent;
    }

    let gpxStr = togpx(geojson, {
      creator: "Hitchwiki Maps",
      featureDescription: (f) => toPlainText(f.text),
      featureLink: (f) => f.url,
    });

    function downloadGPX(data) {
      const blob = new Blob([data], { type: "application/gpx+xml" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "hitchhiking.gpx";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }

    downloadGPX(gpxStr);
  };
  document.body.appendChild(script);
}

const recentToggle = document.getElementById("recent-toggle");
const osmToggle = document.getElementById("osm-toggle");
const carPoolingToggle = document.getElementById("car-pooling-toggle");
const hitchwikiToggle = document.getElementById("hitchwiki-toggle");
const textFilter = document.getElementById("text-filter");
const userFilter = document.getElementById("user-filter");
const distanceFilter = document.getElementById("distance-filter");
const minRidesFilter = document.getElementById("min-rides-filter");
const vehicleFilter = document.getElementById("vehicle-filter");
const methodFilter = document.getElementById("method-filter");
const minDateFilter = document.getElementById("min-date-filter");
const maxDateFilter = document.getElementById("max-date-filter");
const clearFilters = document.getElementById("clear-filters");

function setQueryParameter(key, value) {
  const url = new URL(window.location.href); // Get the current URL

  // Set or update the query parameter
  if (value) {
    url.searchParams.set(key, value);
  } else {
    url.searchParams.delete(key);
  }

  // Update the URL without reloading
  window.history.replaceState({}, "", url.toString());
  navigate();
}

function getQueryParameter(key) {
  const url = new URL(window.location.href);
  return url.searchParams.get(key);
}

function clearParams() {
  const url = new URL(window.location.href);
  let newURL = url.origin + url.pathname + url.hash;
  window.history.replaceState({}, "", newURL.toString());
  navigate();
}

// Reflect the selected spot in the address bar as ?lat=&lon= rather than the
// #lat,lon fragment: the fragment gets stripped by some messengers when the URL
// is pasted, so a copied address-bar link arrived without coordinates. Other
// query params (filters) are preserved. Idempotent — navigate() re-runs on
// every filter change while a spot is open, so we must not push a duplicate
// history entry when the URL already points at this spot.
function setSpotUrl(lat, lon) {
  const url = new URL(window.location.href);
  const latStr = String(lat);
  const lonStr = String(lon);
  if (!url.hash && url.searchParams.get("lat") === latStr && url.searchParams.get("lon") === lonStr) {
    return;
  }
  url.hash = "";
  url.searchParams.set("lat", latStr);
  url.searchParams.set("lon", lonStr);
  window.history.pushState({}, "", url);
}

// Drop the selected-spot URL state (hash + ?lat=&lon=) without navigating.
// Filters and other query params are kept.
function clearSpotUrl() {
  const url = new URL(window.location.href);
  if (!url.hash && !url.searchParams.has("lat") && !url.searchParams.has("lon")) {
    return;
  }
  url.hash = "";
  url.searchParams.delete("lat");
  url.searchParams.delete("lon");
  window.history.pushState({}, "", url);
}

async function applyParams() {
  // Sync heatmap visibility with ?heatmap=true so links can deep-link into the heatmap view
  const heatmapWanted = getQueryParameter("heatmap") == "true";
  if (heatmapWanted !== heatmapActive) {
    await setHeatmapActive(heatmapWanted);
  }

  recentToggle.checked = getQueryParameter("recent") == "true";
  osmToggle.checked = getQueryParameter("osmonly") == "true";
  carPoolingToggle.checked = getQueryParameter("carpoolingonly") == "true";
  hitchwikiToggle.checked = getQueryParameter("hitchwikionly") == "true";
  textFilter.value = getQueryParameter("text");
  userFilter.value = getQueryParameter("user");
  distanceFilter.value = getQueryParameter("mindistance");
  minRidesFilter.value = getQueryParameter("minrides");
  vehicleFilter.value = getQueryParameter("vehicle") || "";
  methodFilter.value = getQueryParameter("method") || "";
  minDateFilter.value = getQueryParameter("mindate") || "";
  maxDateFilter.value = getQueryParameter("maxdate") || "";

  if (
    recentToggle.checked ||
    osmToggle.checked ||
    carPoolingToggle.checked ||
    hitchwikiToggle.checked ||
    textFilter.value ||
    userFilter.value ||
    distanceFilter.value ||
    minRidesFilter.value ||
    vehicleFilter.value ||
    methodFilter.value ||
    minDateFilter.value ||
    maxDateFilter.value
  ) {
    if (filterMarkerGroup) filterMarkerGroup.remove();
    if (filterDestLineGroup) filterDestLineGroup.remove();

    let filterMarkers = distanceFilter.value
        ? destinationMarkers
        : allMarkers;
    // display filtering state and show filter pane
    document.body.classList.add("filtering");
    var fp = document.getElementById('filter-pane');
    if (fp) fp.classList.add('visible');

    // Ride-attribute filters (user, vehicle, ride date range) must AND together
    // at the *ride* level: a spot only matches if a single ride at that spot
    // satisfies ALL active ride-attribute filters. Combining them per-filter
    // and intersecting spot IDs would falsely match a spot when one ride
    // satisfies one filter and a *different* ride at the same spot satisfies
    // another.
    const hasRideAttrFilter =
      userFilter.value || vehicleFilter.value || methodFilter.value || minDateFilter.value || maxDateFilter.value || textFilter.value;
    if (hasRideAttrFilter) {
      const rides = await loadRidesIndex();
      // MediaWiki-style match: only the first letter is case-insensitive, rest matches as-is
      const normalizeFirstLetter = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
      const username = userFilter.value ? normalizeFirstLetter(userFilter.value) : null;
      const wantedKind = vehicleFilter.value || null;
      const wantedMethod = methodFilter.value || null;
      const minMs = minDateFilter.value ? Date.parse(minDateFilter.value + "T00:00:00Z") : null;
      // The max bound covers the end of its day so a user-entered max date is inclusive.
      const maxMs = maxDateFilter.value ? Date.parse(maxDateFilter.value + "T23:59:59.999Z") : null;
      // Comment search runs against the truncated excerpt (`c`) in rides_index.json,
      // so matches deep in long comments may be missed.
      const commentNeedle = textFilter.value ? textFilter.value.toLowerCase() : null;

      const matchingSpotIds = new Set(
        rides
          .filter(ride => {
            if (username && !(ride.u && normalizeFirstLetter(ride.u).includes(username))) return false;
            // Treat rides with unspecified vehicle as cars, since most rides are cars.
            if (wantedKind && ride.v !== wantedKind && !(wantedKind === "car" && ride.v == null)) return false;
            // Method filter: keep rides whose method list contains the selected method.
            if (wantedMethod && !(Array.isArray(ride.m) && ride.m.includes(wantedMethod))) return false;
            if (minMs != null || maxMs != null) {
              if (ride.rd == null) return false;
              if (minMs != null && ride.rd < minMs) return false;
              if (maxMs != null && ride.rd > maxMs) return false;
            }
            if (commentNeedle && !(ride.c && ride.c.toLowerCase().includes(commentNeedle))) return false;
            return true;
          })
          .map(ride => ride.sid)
      );
      filterMarkers = filterMarkers.filter(marker =>
        matchingSpotIds.has(marker.options.spotId)
      );
    }
    if (distanceFilter.value) {
      filterMarkers = filterMarkers.filter((x) => {
        let from = x.getLatLng();
        let lats = x.options._data.dest_lats;
        let lons = x.options._data.dest_lons;

        for (let i in lats) {
          // Road distance is on average 25% longer than straight distance
          if (
            (from.distanceTo([lats[i], lons[i]]) * 1.25) / 1000 >
            distanceFilter.value
          )
            return true;
        }
        return false;
      });
    }
    if (minRidesFilter.value) {
      const minRides = parseInt(minRidesFilter.value, 10);
      filterMarkers = filterMarkers.filter(
        (x) => (x.options._data.review_count || 0) >= minRides
      );
    }
    if (recentToggle.checked) {
      const cutoffMs = Date.now() - 24 * 60 * 60 * 1000;
      filterMarkers = filterMarkers.filter((x) => {
        return x.options._data.latest_ms && x.options._data.latest_ms >= cutoffMs;
      });
    }
    // osm/cp/wiki are presence flags in spots.json (omitted when false); the
    // actual ids/links live in the lazy per-spot detail files.
    if (osmToggle.checked) {
      filterMarkers = filterMarkers.filter((x) => !!x.options._data.osm);
    }
    if (carPoolingToggle.checked) {
      filterMarkers = filterMarkers.filter((x) => !!x.options._data.cp);
    }
    if (hitchwikiToggle.checked) {
      filterMarkers = filterMarkers.filter((x) => !!x.options._data.wiki);
    }
    // duplicate all markers to the filtering pane
    filterMarkers = filterMarkers.map((spot) => {
      let loc = spot.getLatLng();
      let marker = new L.circleMarker(
        loc,
        Object.assign({}, spot.options, { pane: "filtering" })
      );
      marker.on("click", (e) => spot.fire("click", e));
      return marker;
    });

    filterMarkerGroup = L.layerGroup(filterMarkers, {
      pane: "filtering",
    }).addTo(map);
  } else {
    document.body.classList.remove("filtering");
  }
}

async function navigate() {
  await applyParams();

  let args = window.location.hash.slice(1).split("/");
  let mainArgs = args[0].split(",");

  // Shareable spot links carry coordinates as ?lat=&lon= (the #fragment gets
  // stripped by some messengers). When the hash has no coordinates of its own,
  // fall back to these params so the link opens the spot like #lat,lon would.
  const latParam = getQueryParameter("lat");
  const lonParam = getQueryParameter("lon");
  if (
    !mainArgs[0] &&
    latParam != null && lonParam != null &&
    !isNaN(latParam) && !isNaN(lonParam)
  ) {
    mainArgs = [latParam, lonParam];
  }

  // #insights swaps the map for the insights view. Filter pane stays visible
  // so users can keep narrowing the selection and see the histograms update.
  if (mainArgs[0] === "insights") {
    await showInsightsView();
    return;
  } else {
    hideInsightsView();
  }

  if (mainArgs[0] == "location") {
    clear();
    map.setView([+mainArgs[1], +mainArgs[2]], mainArgs[3]);
  } else if (mainArgs[0] == "filters") {
    // Show filter pane below search bar
    var fp = document.getElementById('filter-pane');
    if (fp) fp.classList.add('visible');
    history.replaceState(null, null, " ");
  } else if (mainArgs[0] == "routing") {
    clear();
    bar(".sidebar.routing");
    updateBottomPaneVar();
    setSheetSnap($$(".sidebar.routing"), "full", ROUTING_SHEET_SNAPS);
  } else if (mainArgs[0] == "select-pickup" || mainArgs[0] == "select-destination") {
    clear();
    setupLocationSelection(mainArgs[0], args[1]);
  } else if (mainArgs[0] == "success") {
    history.replaceState(null, null, " ");
    showSuccessOverlay();
  } else if (mainArgs[0] == "success-duplicate") {
    history.replaceState(null, null, " ");
    bar(".sidebar.success-duplicate");
  } else if (mainArgs[0] == "failed") {
    history.replaceState(null, null, " ");
    bar(".sidebar.failed");
  } else if (mainArgs[0] == "registered") {
    history.replaceState(null, null, " ");
    bar(".sidebar.registered");
  } else if (mainArgs.length >= 2 && !isNaN(mainArgs[0]) && !isNaN(mainArgs[1])) {
    clear();
    let lat = +mainArgs[0],
      lon = +mainArgs[1],
      zoom = mainArgs[2] ? +mainArgs[2] : null;
    // Spot coordinates in spots.json are rounded to 5 decimals (~1 m), but
    // older shared links / #lat,lon hashes carry full-precision values, so an
    // exact float comparison would miss. Match the nearest marker within the
    // rounding error instead.
    const EPS = 1.1e-5;
    let nearest = null,
      nearestDist = Infinity;
    for (let m of allMarkers) {
      const d = Math.abs(m._latlng.lat - lat) + Math.abs(m._latlng.lng - lon);
      if (d < nearestDist) {
        nearestDist = d;
        nearest = m;
      }
    }
    if (nearest && nearestDist < EPS) {
      await handleMarkerClick(nearest, nearest.getLatLng(), null);
      if (map.getZoom() < 3) map.setView(nearest.getLatLng(), zoom || 16);
      return;
    }
    // No exact marker match — pan to the coordinates
    map.setView([lat, lon], zoom || 14);
  } else {
    clear();
  }
}

// =====================
// Insights view (#insights)
// =====================
// Renders histograms of waiting time + distance plus summary stats for the
// rides currently selected by the filter pane. The filter pane stays mounted
// above the insights pane, so filter changes re-trigger navigate() →
// showInsightsView() and the charts refresh in place.

const INSIGHTS_BAR_COLOR = "#1a73e8";
const INSIGHTS_BAR_COLOR_TOP = "#4a9bff";
// Hide bars whose value is more than this many stdevs from the mean so a few
// extreme outliers don't squash the rest of the distribution into one bin.
const INSIGHTS_OUTLIER_STDEVS = 3;

function applyRideFilters(rides) {
  const normalizeFirstLetter = (s) =>
    s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
  const username = userFilter.value ? normalizeFirstLetter(userFilter.value) : null;
  const wantedKind = vehicleFilter.value || null;
  const wantedMethod = methodFilter.value || null;
  const minMs = minDateFilter.value
    ? Date.parse(minDateFilter.value + "T00:00:00Z")
    : null;
  const maxMs = maxDateFilter.value
    ? Date.parse(maxDateFilter.value + "T23:59:59.999Z")
    : null;
  const commentNeedle = textFilter.value ? textFilter.value.toLowerCase() : null;
  const minDistanceKm = distanceFilter.value ? parseFloat(distanceFilter.value) : null;
  const minRides = minRidesFilter.value ? parseInt(minRidesFilter.value, 10) : null;
  const recentCutoffMs = recentToggle.checked
    ? Date.now() - 24 * 60 * 60 * 1000
    : null;
  const osmOnly = osmToggle.checked;
  const wikiOnly = hitchwikiToggle.checked;
  const cpOnly = carPoolingToggle.checked;

  let filtered = rides.filter((ride) => {
    if (username && !(ride.u && normalizeFirstLetter(ride.u).includes(username)))
      return false;
    // Match the map's vehicle filter: rides with no vehicle counted as cars.
    if (wantedKind && ride.v !== wantedKind && !(wantedKind === "car" && ride.v == null))
      return false;
    // Method filter: keep rides whose method list contains the selected method.
    if (wantedMethod && !(Array.isArray(ride.m) && ride.m.includes(wantedMethod)))
      return false;
    if (minMs != null || maxMs != null) {
      if (ride.rd == null) return false;
      if (minMs != null && ride.rd < minMs) return false;
      if (maxMs != null && ride.rd > maxMs) return false;
    }
    if (commentNeedle && !(ride.c && ride.c.toLowerCase().includes(commentNeedle)))
      return false;
    if (minDistanceKm != null && !(ride.km != null && ride.km >= minDistanceKm))
      return false;
    if (recentCutoffMs != null && !(ride.t != null && ride.t >= recentCutoffMs))
      return false;
    if (osmOnly && !ride.osm) return false;
    if (wikiOnly && !ride.wiki) return false;
    if (cpOnly && !ride.cp) return false;
    return true;
  });

  if (minRides != null) {
    const ridesPerSpot = new Map();
    for (const r of filtered) {
      ridesPerSpot.set(r.sid, (ridesPerSpot.get(r.sid) || 0) + 1);
    }
    filtered = filtered.filter((r) => (ridesPerSpot.get(r.sid) || 0) >= minRides);
  }

  return filtered;
}

function anyFilterActive() {
  return Boolean(
    userFilter.value ||
      textFilter.value ||
      distanceFilter.value ||
      minRidesFilter.value ||
      vehicleFilter.value ||
      methodFilter.value ||
      minDateFilter.value ||
      maxDateFilter.value ||
      recentToggle.checked ||
      osmToggle.checked ||
      carPoolingToggle.checked ||
      hitchwikiToggle.checked
  );
}

function computeStats(values) {
  if (!values.length) return null;
  const sorted = values.slice().sort((a, b) => a - b);
  const n = sorted.length;
  const sum = sorted.reduce((a, b) => a + b, 0);
  const mean = sum / n;
  const median =
    n % 2 ? sorted[(n - 1) / 2] : (sorted[n / 2 - 1] + sorted[n / 2]) / 2;
  const variance =
    n > 1 ? sorted.reduce((acc, v) => acc + (v - mean) ** 2, 0) / (n - 1) : 0;
  const stdev = Math.sqrt(variance);
  return {
    n,
    mean,
    median,
    stdev,
    min: sorted[0],
    max: sorted[n - 1],
  };
}

// Freedman–Diaconis bin width with a Sturges fallback; clamped to [8, 40] bins
// so very small or very wide datasets still render readably.
function chooseBins(sortedValues) {
  const n = sortedValues.length;
  if (n < 2) return 1;
  const q1 = sortedValues[Math.floor((n - 1) * 0.25)];
  const q3 = sortedValues[Math.floor((n - 1) * 0.75)];
  const iqr = q3 - q1;
  const range = sortedValues[n - 1] - sortedValues[0];
  if (range === 0) return 1;
  let bins;
  if (iqr > 0) {
    const width = (2 * iqr) / Math.cbrt(n);
    bins = Math.ceil(range / width);
  } else {
    bins = Math.ceil(Math.log2(n) + 1);
  }
  return Math.max(8, Math.min(40, bins));
}

// Pick a "nice" axis tick step (1, 2, 2.5, 5 × 10^k).
function niceStep(rawStep) {
  if (rawStep <= 0) return 1;
  const exp = Math.floor(Math.log10(rawStep));
  const frac = rawStep / Math.pow(10, exp);
  let nice;
  if (frac < 1.5) nice = 1;
  else if (frac < 3) nice = 2;
  else if (frac < 4) nice = 2.5;
  else if (frac < 7) nice = 5;
  else nice = 10;
  return nice * Math.pow(10, exp);
}

function formatTick(v, decimals) {
  if (decimals === 0) return Math.round(v).toString();
  return v.toFixed(decimals);
}

// Returns { values, hidden } where `values` is the clipped sample (within
// mean ± INSIGHTS_OUTLIER_STDEVS · stdev) and `hidden` is how many were
// dropped. The original sample is preserved for the stats line above the chart.
function clipForHistogram(values) {
  if (!values || values.length < 2) return { values: values || [], hidden: 0 };
  const stats = computeStats(values);
  if (!stats || !(stats.stdev > 0)) return { values, hidden: 0 };
  const lo = stats.mean - INSIGHTS_OUTLIER_STDEVS * stats.stdev;
  const hi = stats.mean + INSIGHTS_OUTLIER_STDEVS * stats.stdev;
  const kept = values.filter((v) => v >= lo && v <= hi);
  return { values: kept, hidden: values.length - kept.length };
}

function drawHistogram(canvas, values, opts) {
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || 400;
  const cssH = canvas.clientHeight || 220;
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  if (!values || values.length === 0) return;

  const sorted = values.slice().sort((a, b) => a - b);
  const min = sorted[0];
  const max = sorted[sorted.length - 1];
  let bins = chooseBins(sorted);

  let binWidth = (max - min) / bins;
  let lo = min;
  let hi = max;
  if (binWidth === 0) {
    binWidth = 1;
    lo = min - 0.5;
    hi = max + 0.5;
    bins = 1;
  } else {
    binWidth = niceStep(binWidth);
    lo = Math.floor(min / binWidth) * binWidth;
    hi = Math.ceil(max / binWidth) * binWidth;
    if (hi === lo) hi = lo + binWidth;
    bins = Math.round((hi - lo) / binWidth);
  }

  const counts = new Array(bins).fill(0);
  for (const v of sorted) {
    let idx = Math.floor((v - lo) / binWidth);
    if (idx >= bins) idx = bins - 1;
    if (idx < 0) idx = 0;
    counts[idx]++;
  }
  const maxCount = Math.max(...counts);

  // Layout
  const padL = 44;
  const padR = 16;
  const padT = 14;
  const padB = 36;
  const plotW = cssW - padL - padR;
  const plotH = cssH - padT - padB;

  // Y axis ticks
  const yStep = niceStep(maxCount / 4 || 1);
  const yMax = Math.ceil(maxCount / yStep) * yStep || yStep;

  // Grid + Y labels
  ctx.font = "11px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  ctx.fillStyle = "#888";
  ctx.strokeStyle = "#eee";
  ctx.lineWidth = 1;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let y = 0; y <= yMax; y += yStep) {
    const py = padT + plotH - (y / yMax) * plotH;
    ctx.beginPath();
    ctx.moveTo(padL, py);
    ctx.lineTo(padL + plotW, py);
    ctx.stroke();
    ctx.fillText(String(Math.round(y)), padL - 6, py);
  }

  // Bars (with a slight top→bottom gradient for a cleaner look)
  const barGap = bins > 20 ? 1 : 2;
  for (let i = 0; i < bins; i++) {
    if (counts[i] === 0) continue;
    const bx = padL + (i / bins) * plotW + barGap / 2;
    const bw = plotW / bins - barGap;
    const bh = (counts[i] / yMax) * plotH;
    const by = padT + plotH - bh;
    const grad = ctx.createLinearGradient(0, by, 0, by + bh);
    grad.addColorStop(0, INSIGHTS_BAR_COLOR_TOP);
    grad.addColorStop(1, INSIGHTS_BAR_COLOR);
    ctx.fillStyle = grad;
    // Rounded top corners — falls back to a plain rect when unsupported
    const r = Math.min(3, bw / 2, bh);
    ctx.beginPath();
    if (typeof ctx.roundRect === "function") {
      ctx.roundRect(bx, by, bw, bh, [r, r, 0, 0]);
    } else {
      ctx.rect(bx, by, bw, bh);
    }
    ctx.fill();
  }

  // X axis line
  ctx.strokeStyle = "#bbb";
  ctx.beginPath();
  ctx.moveTo(padL, padT + plotH);
  ctx.lineTo(padL + plotW, padT + plotH);
  ctx.stroke();
  // Y axis line
  ctx.beginPath();
  ctx.moveTo(padL, padT);
  ctx.lineTo(padL, padT + plotH);
  ctx.stroke();

  // X axis ticks (target ~6 labels, snap to bin edges)
  const xTickStep = niceStep((hi - lo) / 6);
  const decimals = xTickStep < 1 ? Math.min(2, Math.ceil(-Math.log10(xTickStep))) : 0;
  ctx.fillStyle = "#666";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const xStart = Math.ceil(lo / xTickStep) * xTickStep;
  for (let xv = xStart; xv <= hi + 1e-9; xv += xTickStep) {
    const px = padL + ((xv - lo) / (hi - lo)) * plotW;
    ctx.strokeStyle = "#bbb";
    ctx.beginPath();
    ctx.moveTo(px, padT + plotH);
    ctx.lineTo(px, padT + plotH + 4);
    ctx.stroke();
    ctx.fillText(formatTick(xv, decimals), px, padT + plotH + 7);
  }

  // Axis title
  if (opts && opts.xLabel) {
    ctx.fillStyle = "#555";
    ctx.font = "11px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "bottom";
    ctx.fillText(opts.xLabel, padL + plotW, cssH - 4);
  }
}

function fmtNum(v, unit, decimals) {
  if (v == null || Number.isNaN(v)) return "–";
  const d = decimals == null ? (Math.abs(v) >= 100 ? 0 : 1) : decimals;
  return `${v.toFixed(d)}${unit ? " " + unit : ""}`;
}

function renderSelectionCard(containerId, statsSet) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const rows = [
    ["Rides", statsSet.totalCount.toLocaleString()],
    ["Spots", statsSet.spotCount.toLocaleString()],
  ];
  el.innerHTML = `
    <div class="insights-stat-card">
      <div class="insights-stat-title">Selection</div>
      ${rows
        .map(
          ([k, v]) =>
            `<div class="insights-stat-row"><span class="insights-stat-key">${k}</span><span class="insights-stat-val">${v}</span></div>`
        )
        .join("")}
    </div>`;
}

// Stats line that sits directly above a histogram — n, mean, median, std dev,
// and the (uncropped) range. Rendered as a row of stat chips.
function renderChartSummary(containerId, stats, unit) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!stats) {
    el.innerHTML = "";
    return;
  }
  const items = [
    ["n", stats.n.toLocaleString()],
    ["mean", fmtNum(stats.mean, unit)],
    ["median", fmtNum(stats.median, unit)],
    ["std dev", fmtNum(stats.stdev, unit)],
    ["range", `${fmtNum(stats.min, "")} – ${fmtNum(stats.max, unit)}`],
  ];
  el.innerHTML = items
    .map(
      ([k, v]) =>
        `<div class="insights-summary-item"><span class="insights-summary-key">${k}</span><span class="insights-summary-val">${v}</span></div>`
    )
    .join("");
}

function renderChartNote(containerId, hidden, total, unit) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!hidden) {
    el.textContent = "";
    return;
  }
  el.textContent = `Hiding ${hidden.toLocaleString()} of ${total.toLocaleString()} ${unit} values beyond ±${INSIGHTS_OUTLIER_STDEVS} std dev from the mean.`;
}

function setInsightsSubtitle(text) {
  const el = document.getElementById("insights-subtitle");
  if (el) el.textContent = text;
}

let insightsResizeBound = false;
// Snapshot of the values to draw; the chart bars are clipped (mean ± 3 stdev)
// while the stats above each chart are computed from the full sample.
let insightsLastDraw = null; // { wait: {full, clipped}, distance: {full, clipped} }
// Original DOM location of the filter pane, so we can put it back when leaving
// the insights view. The same node is moved (not cloned) so all event
// listeners and state remain attached.
let filterPaneOriginalParent = null;
let filterPaneOriginalNext = null;

function moveFilterPaneIntoInsights() {
  const pane = document.getElementById("filter-pane");
  const slot = document.getElementById("insights-filter-slot");
  if (!pane || !slot) return;
  if (pane.parentNode === slot) return;
  filterPaneOriginalParent = pane.parentNode;
  filterPaneOriginalNext = pane.nextSibling;
  slot.appendChild(pane);
}

function restoreFilterPaneFromInsights() {
  const pane = document.getElementById("filter-pane");
  if (!pane || !filterPaneOriginalParent) return;
  if (pane.parentNode === filterPaneOriginalParent) return;
  if (filterPaneOriginalNext && filterPaneOriginalNext.parentNode === filterPaneOriginalParent) {
    filterPaneOriginalParent.insertBefore(pane, filterPaneOriginalNext);
  } else {
    filterPaneOriginalParent.appendChild(pane);
  }
}

function redrawInsightsCharts() {
  if (!insightsLastDraw) return;
  const waitCanvas = document.getElementById("insights-wait-chart");
  const distCanvas = document.getElementById("insights-distance-chart");
  drawHistogram(waitCanvas, insightsLastDraw.wait.clipped, { xLabel: "minutes" });
  drawHistogram(distCanvas, insightsLastDraw.distance.clipped, { xLabel: "kilometres" });
}

async function showInsightsView() {
  const pane = document.getElementById("insights-pane");
  if (!pane) return;

  pane.style.display = "block";
  document.body.classList.add("showing-insights");
  moveFilterPaneIntoInsights();

  // Hide any open sidebars / sheets so the insights view has the screen.
  bar();
  document.body.classList.remove("menu", "adding-spot", "reporting-duplicate");

  // Load rides index (cached after first call).
  const rides = await loadRidesIndex();
  const filtered = anyFilterActive() ? applyRideFilters(rides) : rides;

  const waitValues = filtered
    .map((r) => r.w)
    .filter((v) => v != null && !Number.isNaN(v) && v >= 0);
  const distValues = filtered
    .map((r) => r.km)
    .filter((v) => v != null && !Number.isNaN(v) && v >= 0);

  const waitStats = computeStats(waitValues);
  const distStats = computeStats(distValues);
  const waitClip = clipForHistogram(waitValues);
  const distClip = clipForHistogram(distValues);

  const stats = {
    totalCount: filtered.length,
    spotCount: new Set(filtered.map((r) => r.sid)).size,
  };

  renderSelectionCard("insights-stats", stats);
  renderChartSummary("insights-wait-summary", waitStats, "min");
  renderChartSummary("insights-distance-summary", distStats, "km");
  renderChartNote("insights-wait-note", waitClip.hidden, waitValues.length, "waiting-time");
  renderChartNote("insights-distance-note", distClip.hidden, distValues.length, "distance");
  setInsightsSubtitle(
    anyFilterActive()
      ? `Showing ${stats.totalCount.toLocaleString()} rides matching your active filters.`
      : `Showing all ${stats.totalCount.toLocaleString()} rides. Use the filters above to narrow the selection.`
  );

  const waitEmpty = document.getElementById("insights-wait-empty");
  const distEmpty = document.getElementById("insights-distance-empty");
  if (waitEmpty) waitEmpty.hidden = waitClip.values.length > 0;
  if (distEmpty) distEmpty.hidden = distClip.values.length > 0;

  insightsLastDraw = {
    wait: { full: waitValues, clipped: waitClip.values },
    distance: { full: distValues, clipped: distClip.values },
  };
  // Wait one frame so the pane has its final size before measuring canvases.
  requestAnimationFrame(redrawInsightsCharts);

  if (!insightsResizeBound) {
    window.addEventListener("resize", () => {
      if (document.body.classList.contains("showing-insights")) {
        redrawInsightsCharts();
      }
    });
    const backLink = document.getElementById("insights-back-link");
    if (backLink) {
      backLink.addEventListener("click", (e) => {
        e.preventDefault();
        navigateHome();
      });
    }
    insightsResizeBound = true;
  }
}

function hideInsightsView() {
  const pane = document.getElementById("insights-pane");
  if (!pane) return;
  if (pane.style.display !== "none") {
    pane.style.display = "none";
  }
  document.body.classList.remove("showing-insights");
  restoreFilterPaneFromInsights();
}

// Map Controls
var AddSpotButton = L.Control.extend({
  options: {
    position: "topleft",
  },
  onAdd: function (map) {
    var controlDiv = L.DomUtil.create(
      "div",
      "leaflet-bar horizontal-button add-spot"
    );
    var container = L.DomUtil.create("a", "", controlDiv);
    container.href = "javascript:void(0);";
    container.innerText = "🚗💨 Add your ride";

    container.onclick = function (e) {      
      // Redirect directly to ride form instead of crosshair selection
      window.location.href = "/ride";

      L.DomEvent.stopPropagation(e);
    };

    return controlDiv;
  },
});

var MenuButton = L.Control.extend({
  options: {
    position: "topleft",
  },
  onAdd: function (map) {
    var controlDiv = L.DomUtil.create(
      "div",
      "leaflet-bar horizontal-button menu"
    );
    var container = L.DomUtil.create("a", "", controlDiv);
    container.href = "javascript:void(0);";
    container.innerHTML = "☰";

    container.onclick = function (e) {
      if (document.body.classList.contains("menu")) {
        bar();
        document.body.classList.remove("menu");
      } else {
        clearSpotUrl();
        bar(".sidebar.menu");
        document.body.classList.add("menu");
      }
      L.DomEvent.stopPropagation(e);
    };

    return controlDiv;
  },
});

var AccountButton = L.Control.extend({
  options: {
    position: "topleft",
  },
  onAdd: function (map) {
    var controlDiv = L.DomUtil.create(
      "div",
      "leaflet-bar horizontal-button your-account"
    );
    var container = L.DomUtil.create("a", "", controlDiv);
    container.href = "/me";
    container.innerHTML = "👤 Your account";

    return controlDiv;
  },
});

var RoutingButton = L.Control.extend({
  options: {
    position: "topleft",
  },
  onAdd: function (map) {
    var controlDiv = L.DomUtil.create(
      "div",
      "leaflet-bar horizontal-button routing-button"
    );
    var container = L.DomUtil.create("a", "", controlDiv);
    container.href = "#routing";
    container.innerHTML = "🗺️ Route";
    return controlDiv;
  },
});

var HeatmapInfoButton = L.Control.extend({
  options: {
    position: "topleft",
  },
  onAdd: function (map) {
    var controlDiv = L.DomUtil.create(
      "div",
      "leaflet-bar horizontal-button heatmap-info"
    );
    var container = L.DomUtil.create("a", "", controlDiv);
    container.href = "javascript:void(0);";
    container.innerHTML = "\u2139 What can I see here?";

    container.onclick = function (e) {
      navigateHome();
      if (document.body.classList.contains("heatmap-info")) {
        bar();
      } else {
        bar(".sidebar.heatmap-info");
      }
      document.body.classList.toggle("heatmap-info");
      L.DomEvent.stopPropagation(e);
    };

    return controlDiv;
  },
});


function confirmClaimReview(url) {
    if (confirm("Are you sure you want to claim this review as yours? Did you create this review previously?")) {
        window.location.href = url;
    }
};

// Location selection functionality for ride form
let locationSelectionMarker = null;
let locationSelectionType = null;

function setupLocationSelection(selectionType, initialCoords) {
    locationSelectionType = selectionType;
    
    // Parse initial coordinates if provided
    if (initialCoords) {
        const coords = initialCoords.split(',');
        if (coords.length >= 3) {
            const lat = parseFloat(coords[0]);
            const lon = parseFloat(coords[1]);
            const zoom = parseInt(coords[2]);
            map.setView([lat, lon], zoom);
        }
    }
    
    // Add a draggable marker for location selection
    const center = map.getCenter();
    locationSelectionMarker = L.marker(center, {
        draggable: true,
        icon: L.icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            popupAnchor: [1, -34],
            shadowSize: [41, 41]
        })
    }).addTo(map);
    
    // Update marker position when map is clicked
    map.on('click', function(e) {
        locationSelectionMarker.setLatLng(e.latlng);
    });
    
    // Add custom UI for location selection
    const selectionUI = L.DomUtil.create('div', 'location-selection-ui');
    selectionUI.innerHTML = `
        <div style="position: fixed; top: 20px; left: 50%; transform: translateX(-50%); 
                    background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.3);
                    z-index: 1000; text-align: center; min-width: 300px;">
            <h4 style="margin: 0 0 10px 0;">Select ${selectionType === 'select-pickup' ? 'Pickup' : 'Destination'} Location</h4>
            <p style="margin: 0 0 15px 0; font-size: 14px; color: #666;">
                Click on the map or drag the marker to choose your ${selectionType === 'select-pickup' ? 'pickup' : 'destination'} location
            </p>
            <button onclick="confirmLocationSelection()" style="background: #007bff; color: white; border: none; 
                           padding: 8px 20px; border-radius: 4px; margin-right: 10px; cursor: pointer;">
                Confirm Location
            </button>
            <button onclick="cancelLocationSelection()" style="background: #6c757d; color: white; border: none; 
                           padding: 8px 20px; border-radius: 4px; cursor: pointer;">
                Cancel
            </button>
        </div>
    `;
    document.body.appendChild(selectionUI);
}

function confirmLocationSelection() {
    if (!locationSelectionMarker) return;
    
    const latlng = locationSelectionMarker.getLatLng();
    
    // Update the form data in sessionStorage with new coordinates
    const formData = JSON.parse(sessionStorage.getItem('rideFormData') || '{}');
    
    if (locationSelectionType === 'select-pickup') {
        formData.pickup_lat = latlng.lat;
        formData.pickup_lon = latlng.lng;
    } else if (locationSelectionType === 'select-destination') {
        formData.destination_lat = latlng.lat;
        formData.destination_lon = latlng.lng;
    }
    
    sessionStorage.setItem('rideFormData', JSON.stringify(formData));

    // Return to ride form, preserving edit mode if editing an existing ride
    const editDTag = formData.edit_d_tag;
    window.location.href = editDTag ? '/ride?edit=' + encodeURIComponent(editDTag) : '/ride';
}

function cancelLocationSelection() {
    // Clean up and return to ride form without changing coordinates
    cleanupLocationSelection();

    // Return to ride form, preserving edit mode if editing an existing ride
    const formData = JSON.parse(sessionStorage.getItem('rideFormData') || '{}');
    const editDTag = formData.edit_d_tag;
    window.location.href = editDTag ? '/ride?edit=' + encodeURIComponent(editDTag) : '/ride';
}

function cleanupLocationSelection() {
    // Remove marker and UI
    if (locationSelectionMarker) {
        map.removeLayer(locationSelectionMarker);
        locationSelectionMarker = null;
    }
    
    const ui = document.querySelector('.location-selection-ui');
    if (ui) {
        ui.remove();
    }
    
    // Remove event listener
    map.off('click');
    
    locationSelectionType = null;
}
