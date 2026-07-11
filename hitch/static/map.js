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
  markerCluster = null,
  ridesIndex = null,
  // Map-mode switcher: "spots" (default), "heatmap", or "countries".
  mapMode = "spots",
  countryLayer = null,
  // Hitchwiki Category:Event markers (dist/events.json), drawn on their own layer.
  eventLayer = null,
  eventsData = null,
  mapModeButtons = {};

// Current-location button state. The marker/circle are created lazily on the
// first successful locate and re-used on subsequent taps so taps never stack
// markers. Geolocation is only ever requested from the button's click handler.
let locateButtonEl = null;
let locationMarker = null;
let locationAccuracyCircle = null;
let locationFadeTimer = null;

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
      // Module-scoped so findNearbySpotMarker() can ask whether a marker is
      // currently hidden inside a cluster (getVisibleParent) when snapping.
      markerCluster = L.markerClusterGroup({
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
          // it the same way generate_spot_id does in show.py (5 decimals, matching
          // the served coord precision) so it matches the rides/by-spot/<id>.json
          // filename.
          spotId: `${m.lat.toFixed(5)}_${m.lon.toFixed(5)}`,
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
    setTestBtnBelowLegend(false);
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
  setTestBtnBelowLegend(true);
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
  if (!legendPane || legendPane.style.display === 'none') return;
  // Filters moved out of a persistent top panel into an icon-launched modal, so anchor
  // the heatmap legend at a fixed top just below the search bar instead of relative to it.
  legendPane.style.top = '104px';
}

// Filters modal (opened by the search-bar filter icon). Remove `collapsed` so the body
// shows, then flag the body so the modal + scrim become visible (see style.css).
function openFiltersModal() {
  var pane = document.getElementById('filter-pane');
  if (pane) pane.classList.remove('collapsed');
  document.body.classList.add('filters-open');
}
function closeFiltersModal() {
  document.body.classList.remove('filters-open');
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
  // Added before the locate control so it stacks directly above the GPS button.
  setupMapModeControl();
  setupLocateControl();

  // Load markers asynchronously
  await loadMarkers(map);

  // Restore the test-mode indicator if it was left on. Called here (not inside
  // setupMapModeControl, which runs synchronously before the test-mode module vars
  // are initialized) to avoid a temporal-dead-zone ReferenceError that would abort
  // init before loadMarkers.
  renderTestModeIndicator();

  // Hitchwiki event markers — non-blocking, they're a small overlay.
  loadEventMarkers(map);

  // User-proposed spots (blue markers) — non-blocking overlay, like events.
  loadProposedSpotMarkers(map);

  setupEventListeners();

  // Nudge first-time users toward the features they'd otherwise miss; short delay
  // so the pointer doesn't fight the initial map load/animation.
  setTimeout(showNextFeatureHint, 1500);

  // Filters are now an icon-launched modal (opened from the search bar). The header
  // button — and a tap on the scrim — close it.
  var filterCollapseBtn = document.getElementById('filter-collapse-btn');
  var filterPaneEl = document.getElementById('filter-pane');
  if (filterCollapseBtn && filterPaneEl) {
    filterCollapseBtn.closest('.filter-pane-header').addEventListener('click', closeFiltersModal);
  }
  var filtersScrim = document.getElementById('filters-scrim');
  if (filtersScrim) filtersScrim.addEventListener('click', closeFiltersModal);

  // Set up heatmap legend collapse toggle
  var legendCollapseBtn = document.getElementById('legend-collapse-btn');
  var legendPaneEl = document.getElementById('heatmap-legend-pane');
  if (legendCollapseBtn && legendPaneEl) {
    legendCollapseBtn.closest('.filter-pane-header').addEventListener('click', function() {
      legendPaneEl.classList.toggle('collapsed');
    });
  }

  // Set up heatmap toggle — routed through the map-mode switcher so the two
  // controls never disagree about which mode is active.
  const heatmapBtn = $$('#heatmap-toggle-btn');
  if (heatmapBtn) {
    heatmapBtn.addEventListener('click', () =>
      setMapMode(mapMode === 'heatmap' ? 'spots' : 'heatmap'));
  }

  // Restore the requested map mode from the URL: ?mapmode=countries takes
  // precedence, otherwise the legacy ?heatmap=true selects heatmap mode.
  if (getQueryParameter('mapmode') === 'countries') {
    await setMapMode('countries');
  } else if (getQueryParameter('heatmap') === 'true') {
    await setMapMode('heatmap');
  }

  // These functions make the navigation work
  handleHashChange();
  // Keep #map=z/lat/lon in step with the map so the address bar is always a
  // link to what the user is looking at. Registered after handleHashChange so
  // the initial view is read from the URL before we start writing to it.
  map.on("moveend", updateMapHash);
  updateMapHash();
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

  // Google-Maps-style route button anchored at the right end of the search bar
  // (replaces the old bottom-pane "Route" action). Navigating to #routing opens
  // the routing bottom sheet via the hash handler in main().
  const routeBtn = L.DomUtil.create(
    "a",
    "geocoder-route-btn",
    geocoderController.getContainer()
  );
  routeBtn.href = "#routing";
  routeBtn.title = "Route planning";
  routeBtn.setAttribute("aria-label", "Route planning");
  routeBtn.innerHTML = '<i class="fa-solid fa-route"></i>';
  // Keep clicks on the button from reaching the map (pan/zoom on the control).
  L.DomEvent.disableClickPropagation(routeBtn);

  // Filter button, just left of the route button — opens the filters as a modal
  // (replaces the old persistent top filter panel). Keeps filters out of the way
  // until wanted, and one tap from the search bar.
  const filterBtn = L.DomUtil.create("a", "geocoder-filter-btn", geocoderController.getContainer());
  filterBtn.href = "#";
  filterBtn.title = "Filters";
  filterBtn.setAttribute("aria-label", "Filters");
  filterBtn.innerHTML = '<i class="fa-solid fa-sliders"></i>';
  L.DomEvent.disableClickPropagation(filterBtn);
  L.DomEvent.on(filterBtn, "click", function (ev) {
    L.DomEvent.preventDefault(ev);
    openFiltersModal();
  });


  geocoderController.on("markgeocode", function (e) {
    var zoom = geocoderOpts.zoom || map.getZoom();
    map.setView(e.geocode.center, zoom);
    geocoderInput.value = "";
  });
}

// Restart a CSS keyframes fade on an element: remove the class, force a reflow
// so the browser drops the running animation, then re-add it so it plays again
// from the start. Used so a repeat tap resets the blue->grey fade back to blue.
function restartFade(el, cls) {
  el.classList.remove(cls);
  // Reading offsetWidth forces a synchronous reflow, which is what lets the
  // re-added class start a fresh animation instead of continuing the old one.
  void el.offsetWidth;
  el.classList.add(cls);
}

// Single source of truth for the locate button's visual state.
//   idle   -> crosshairs, default colour
//   busy   -> spinner, while waiting for a fix
//   active -> crosshairs, blue, while a fix is shown on the map
// Clears the fade class so busy/idle are never mid-fade; showLocation restarts
// the fade after setting the active state.
function setLocateButtonState(state) {
  if (!locateButtonEl) return;
  locateButtonEl.classList.remove("locate-busy", "locate-active", "locate-fading");
  if (state === "busy") {
    locateButtonEl.classList.add("locate-busy");
    locateButtonEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i>';
  } else {
    if (state === "active") locateButtonEl.classList.add("locate-active");
    locateButtonEl.innerHTML = '<i class="fa-solid fa-location-crosshairs" aria-hidden="true"></i>';
  }
}

// The ONLY place geolocation is requested. Called from the button tap handler,
// never on load. setView pans/zooms the map to the fix.
function requestLocation() {
  setLocateButtonState("busy");
  map.locate({
    setView: true,
    maxZoom: 16,
    enableHighAccuracy: true,
    timeout: 10000,
  });
}

// locationfound handler. Re-uses a single marker + accuracy circle so repeated
// taps never stack markers on the map.
function showLocation(e) {
  const radius = e.accuracy; // metres

  // While selecting a location (notably the destination leg, which starts with
  // no pin), a GPS-button tap is the user asking to drop the endpoint on their
  // current position — so place/move the selection pin there too.
  if (locationSelectionType) {
    placeOrMoveSelectionMarker(e.latlng);
  }

  if (locationMarker) {
    locationMarker.setLatLng(e.latlng);
  } else {
    const icon = L.divIcon({
      className: "user-location-marker",
      html: '<div class="user-location-dot"></div>',
      iconSize: [18, 18],
      iconAnchor: [9, 9],
    });
    locationMarker = L.marker(e.latlng, {
      icon: icon,
      // The bubble is an entry point to the choose-action dialog; interactive:true
      // lets the click handler fire without itself setting pickup/destination.
      interactive: true,
      keyboard: false,
    }).addTo(map);
    locationMarker.on("click", function () {
      const p = map.latLngToContainerPoint(locationMarker.getLatLng());
      if (window.inrideOnEntryGesture) window.inrideOnEntryGesture(locationMarker.getLatLng(), p);
    });
  }

  // Restart the blue->grey freshness fade on every fix. The marker (and its dot
  // element) is re-used across taps, so restart the animation rather than relying
  // on a fresh element — otherwise a repeat tap would leave the dot stuck grey.
  const markerEl = locationMarker.getElement();
  const dotEl = markerEl ? markerEl.querySelector(".user-location-dot") : null;
  if (dotEl) restartFade(dotEl, "fading");

  if (locationAccuracyCircle) {
    locationAccuracyCircle.setLatLng(e.latlng).setRadius(radius);
  } else {
    locationAccuracyCircle = L.circle(e.latlng, {
      radius: radius,
      interactive: false,
      color: "#1e88e5",
      weight: 1,
      fillColor: "#1e88e5",
      fillOpacity: 0.12,
    }).addTo(map);
  }

  // Match the dot: circle starts blue, becomes grey after the 30s fade window.
  locationAccuracyCircle.setStyle({ color: "#1e88e5", fillColor: "#1e88e5" });
  if (locationFadeTimer) clearTimeout(locationFadeTimer);
  locationFadeTimer = setTimeout(function () {
    if (locationAccuracyCircle) {
      locationAccuracyCircle.setStyle({ color: "#9e9e9e", fillColor: "#9e9e9e" });
    }
  }, 30000);

  // Active state + restart the button's own blue->grey fade so the button goes
  // stale in sync with the dot, signalling the fix is a one-time snapshot.
  setLocateButtonState("active");
  if (locateButtonEl) restartFade(locateButtonEl, "locate-fading");
}

// locationerror handler: permission denied, position unavailable, or timeout.
function onLocationError(e) {
  setLocateButtonState(locationMarker ? "active" : "idle");
  alert("Could not get your location: " + e.message);
}

// OsmAnd-style "current location" button. Anchored bottom-right above the zoom
// control. Requirement: geolocation must NOT be requested on page load — the
// only call to map.locate()/navigator.geolocation happens in the tap handler
// (wired in Task 2). This task only renders the idle button.
// ---- Map mode switcher (Spots / Heatmap / Countries) -----------------------

// Score (1..5) -> choropleth colour, matching the country page badge colours.
const COUNTRY_RATING_COLORS = { 1: "#d73027", 2: "#fc8d59", 3: "#fee08b", 4: "#91cf60", 5: "#1a9850" };

// The choropleth is coloured by the continuous 0–5 hitchability score, so we
// interpolate between the five anchor colours above rather than bucketing to
// integers (most countries would otherwise all land on the same "4" shade).
const COUNTRY_COLOR_STOPS = [
  [1, [0xd7, 0x30, 0x27]],
  [2, [0xfc, 0x8d, 0x59]],
  [3, [0xfe, 0xe0, 0x8b]],
  [4, [0x91, 0xcf, 0x60]],
  [5, [0x1a, 0x98, 0x50]],
];

function hitchColor(score) {
  const s = Math.max(1, Math.min(5, score));
  for (let i = 1; i < COUNTRY_COLOR_STOPS.length; i++) {
    const [x0, c0] = COUNTRY_COLOR_STOPS[i - 1];
    const [x1, c1] = COUNTRY_COLOR_STOPS[i];
    if (s <= x1) {
      const t = (s - x0) / (x1 - x0);
      const ch = (k) => Math.round(c0[k] + (c1[k] - c0[k]) * t);
      return `rgb(${ch(0)}, ${ch(1)}, ${ch(2)})`;
    }
  }
  return "#1a9850";
}

// The value that drives a country's colour/label: hitchability when scored,
// falling back to the integer rating for countries without a score.
function countryScore(entry) {
  if (!entry) return null;
  return typeof entry.hitch === "number" ? entry.hitch : entry.rating;
}

function countryStyle(feature) {
  const cc = feature.properties.cc;
  const entry = countryRatings && countryRatings[cc];
  const score = countryScore(entry);
  const color = score != null ? hitchColor(score) : null;
  return {
    pane: "countries",
    color: "#ffffff",
    weight: 1,
    fillColor: color || "#000000",
    // Scored countries read as a solid choropleth; unscored ones stay faint.
    fillOpacity: color ? 0.65 : 0.05,
  };
}

let countryRatings = null;

// Build the country choropleth layer once (fetches boundaries + ratings).
async function loadCountryLayer() {
  if (countryLayer) return countryLayer;
  const [geo, ratings] = await Promise.all([
    fetch("/static/countries.geojson").then((r) => r.json()),
    fetch("/country_ratings.json").then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
  ]);
  countryRatings = ratings;
  countryLayer = L.geoJSON(geo, {
    // Force SVG so countries stay clickable over the canvas-preferring base map.
    renderer: L.svg({ pane: "countries" }),
    style: countryStyle,
    onEachFeature: (feature, layer) => {
      const { cc, name } = feature.properties;
      const entry = countryRatings[cc];
      const score = countryScore(entry);
      const label = entry
        ? `${name}: ${score != null ? score.toFixed(1) : "?"}/5 hitchability (${entry.count} rides)`
        : `${name}: no rides yet`;
      layer.bindTooltip(label, { sticky: true });
      // Tapping a country opens its info sheet, reflected in the address bar as
      // #country/<name> so it's deep-linkable and the back button closes it.
      // Stop propagation so the map's own click handler (handleMapClick) doesn't
      // also fire and open a nearby spot on top of the country sheet.
      layer.on("click", (e) => {
        // While the routing planner is open every tap places a start/destination
        // point. Let the click bubble to the map (routing.js onMapClick) instead
        // of opening the country sheet on top of the planner.
        if (window.RoutingUI && window.RoutingUI.active) return;
        L.DomEvent.stopPropagation(e);
        location.hash = "country/" + encodeURIComponent(name);
      });
      layer.on("mouseover", () => layer.setStyle({ weight: 2, color: "#333" }));
      layer.on("mouseout", () => countryLayer.resetStyle(layer));
    },
  });
  return countryLayer;
}

// ---- Country info sheet -----------------------------------------------------
// Renders a country's Hitchwiki lead section + rating badge into the #country
// bottom sheet when a country is tapped in the map's "Countries" mode.
// The lead section is fetched client-side because the Hitchwiki API sits behind
// Cloudflare's bot challenge, which blocks server-side requests from this host's
// datacenter IP but lets real end-user browsers through.

const COUNTRY_WIKI_BASE = "https://hitchwiki.org/en/";

// Some Natural Earth country names don't match the Hitchwiki page title.
const COUNTRY_WIKI_TITLE_ALIASES = {
  "United States of America": "United States",
  "People's Republic of China": "China",
  "Republic of Serbia": "Serbia",
  "United Republic of Tanzania": "Tanzania",
  Czechia: "Czech Republic",
};

// Turn a Hitchwiki page target into an absolute article URL.
function countryWikiLink(target) {
  const page = target.trim().replace(/ /g, "_");
  return COUNTRY_WIKI_BASE + encodeURI(page).replace(/"/g, "%22");
}

// Remove {{...}} templates, honouring nesting, from raw wikitext.
function stripWikiTemplates(text) {
  let out = "",
    depth = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "{" && text[i + 1] === "{") { depth++; i++; continue; }
    if (text[i] === "}" && text[i + 1] === "}" && depth > 0) { depth--; i++; continue; }
    if (depth === 0) out += text[i];
  }
  return out;
}

// Remove [[File:...]] / [[Image:...]] embeds, honouring nested [[ ]].
// A regex can't do this reliably: captions routinely contain single-bracket
// external links ([https://... label]) and nested [[wikilinks]], which throw
// off any bracket-counting pattern and let the whole embed leak through as
// prose. Scan instead — track [[ ]] depth and drop everything from an image's
// opening [[ to its matching ]], whatever brackets the caption holds.
function stripWikiImages(text) {
  let out = "";
  for (let i = 0; i < text.length; ) {
    if (text[i] === "[" && text[i + 1] === "[" && /^(?:File|Image):/i.test(text.slice(i + 2))) {
      let depth = 1;
      i += 2;
      while (i < text.length && depth > 0) {
        if (text[i] === "[" && text[i + 1] === "[") { depth++; i += 2; }
        else if (text[i] === "]" && text[i + 1] === "]") { depth--; i += 2; }
        else i++;
      }
      continue;
    }
    out += text[i];
    i++;
  }
  return out;
}

// Render lead-section wikitext as safe HTML (prose + links only).
function renderCountryWikitext(raw) {
  let t = raw;
  t = t.replace(/<!--[\s\S]*?-->/g, ""); // HTML comments
  t = t.replace(/<ref[^>]*\/>/gi, ""); // self-closing <ref/>
  t = t.replace(/<ref[^>]*>[\s\S]*?<\/ref>/gi, ""); // <ref>...</ref>
  // <gallery>…</gallery> blocks list images as bare "File:name.jpg|caption"
  // lines (no [[ ]]), so stripWikiImages below won't catch them — drop the
  // whole block, otherwise the filenames leak through as prose text.
  t = t.replace(/<gallery[^>]*>[\s\S]*?<\/gallery>/gi, "");
  t = stripWikiTemplates(t);
  t = t.replace(/__[A-Z]+__/g, ""); // magic words (__TOC__, __NOTOC__, …)
  t = stripWikiImages(t); // [[File:...]] / [[Image:...]] embeds
  t = t.replace(/^\s*[*#:;].*$/gm, ""); // list/indent lines (keep it prose-only)

  // Escape HTML-significant chars before we inject our own safe markup, but keep
  // apostrophes intact: escapeHtml() turns ' into &#39;, which would stop the
  // '''bold''' / ''italic'' passes below from ever matching their quote markers.
  t = t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  // Internal links: [[target|label]] and [[target]]
  t = t.replace(/\[\[([^\[\]|]+)\|([^\[\]]+)\]\]/g, (m, target, label) =>
    `<a href="${countryWikiLink(target)}" target="_blank" rel="noopener">${label}</a>`);
  t = t.replace(/\[\[([^\[\]]+)\]\]/g, (m, target) =>
    `<a href="${countryWikiLink(target)}" target="_blank" rel="noopener">${target}</a>`);
  // External links: [url label] and [url]
  t = t.replace(/\[(https?:\/\/[^\s\]]+)\s+([^\]]+)\]/g, (m, url, label) =>
    `<a href="${encodeURI(url)}" target="_blank" rel="noopener">${label}</a>`);
  t = t.replace(/\[(https?:\/\/[^\s\]]+)\]/g, (m, url) =>
    `<a href="${encodeURI(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a>`);
  // Bold / italic
  t = t.replace(/'''(.+?)'''/g, "<strong>$1</strong>");
  t = t.replace(/''(.+?)''/g, "<em>$1</em>");

  // Build blocks: heading lines (== .. ==) become <h4>, everything else is
  // gathered into paragraphs. A fetched section starts with its own heading,
  // and may contain === subsections ===, so headings aren't always blank-line
  // separated — split per line rather than only on blank lines.
  const out = [];
  for (const block of t.split(/\n{2,}/)) {
    let para = [];
    const flush = () => {
      const text = para.join(" ").trim();
      if (text) out.push(`<p>${text}</p>`);
      para = [];
    };
    for (const line of block.split("\n")) {
      const heading = line.trim().match(/^={2,6}\s*(.+?)\s*={2,6}$/);
      if (heading) {
        flush();
        const label = heading[1].trim();
        // Drop the redundant top-level "Hitchhiking" heading — the sheet is
        // already titled with the country name.
        if (label.toLowerCase() !== "hitchhiking") out.push(`<h4>${label}</h4>`);
      } else {
        para.push(line);
      }
    }
    flush();
  }
  return out.join("");
}

// Country name → ISO code map from countries.geojson (the code keys the ratings
// and insights files). Cached after the first lookup.
let countryCcByName = null;
async function getCountryCc(name) {
  try {
    if (!countryCcByName) {
      const geo = await fetch("/static/countries.geojson").then((r) => r.json());
      countryCcByName = {};
      for (const f of geo.features) countryCcByName[f.properties.name] = f.properties.cc;
    }
    return countryCcByName[name] || null;
  } catch (e) {
    return null;
  }
}

// Rating badge — sourced from the same file the map's Countries mode uses.
async function loadCountrySheetRating(cc) {
  const badge = $$("#country-sheet-rating");
  badge.style.display = "none";
  if (!cc) return;
  try {
    // Reuse the already-loaded Countries-mode data when available; otherwise
    // fetch it so deep links (#country/<name>) work without Countries mode on.
    const ratings = countryRatings || (await fetch("/country_ratings.json").then((r) => (r.ok ? r.json() : {})));
    const entry = ratings[cc];
    if (!entry) return;
    const score = countryScore(entry);
    badge.style.background = score != null ? hitchColor(score) : "#9e9e9e";
    badge.innerHTML =
      `<i class="fa-solid fa-thumbs-up"></i>${score != null ? score.toFixed(1) : "?"}` +
      `<span class="country-rating-count">· ${entry.count} rides</span>`;
    badge.style.display = "inline-flex";
  } catch (e) { /* rating is optional */ }
}

// Pre-computed per-country waiting-time / distance histograms (built by
// country_ratings.py). Fetched once and cached; the country sheet renders them
// with the same renderer as /insights, so no client-side binning is needed.
let countryInsightsData = null;
let countryInsightsLastDraw = null; // { wait, distance } histograms currently drawn
async function loadCountryInsights(cc) {
  const wrap = $$("#country-sheet-insights");
  countryInsightsLastDraw = null;
  wrap.hidden = true;
  if (!cc) return;
  try {
    if (!countryInsightsData) {
      countryInsightsData = await fetch("/country_insights.json").then((r) => (r.ok ? r.json() : {}));
    }
  } catch (e) {
    return;
  }
  const entry = countryInsightsData[cc];
  if (!entry || (!entry.wait && !entry.distance)) return;
  wrap.hidden = false;

  renderCountryMetric("wait", entry.wait, "min", "waiting-time");
  renderCountryMetric("distance", entry.distance, "km", "distance");

  countryInsightsLastDraw = {
    wait: entry.wait ? entry.wait.hist : null,
    distance: entry.distance ? entry.distance.hist : null,
  };
  // Draw after a frame so the sheet has its final width before we size canvases.
  requestAnimationFrame(redrawCountryInsightsCharts);
}

// Fill the summary line + note for one metric block and toggle its visibility.
function renderCountryMetric(key, metric, unit, noteLabel) {
  const block = $$("#country-" + key + "-block");
  if (!metric) {
    block.hidden = true;
    return;
  }
  block.hidden = false;
  renderChartSummary("country-" + key + "-summary", metric.stats, unit);
  renderChartNote("country-" + key + "-note", metric.hidden, metric.stats.n, noteLabel);
  const empty = $$("#country-" + key + "-empty");
  if (empty) empty.hidden = !!(metric.hist && metric.hist.counts && metric.hist.counts.length);
}

function redrawCountryInsightsCharts() {
  if (!countryInsightsLastDraw) return;
  if (countryInsightsLastDraw.wait)
    renderHistogram($$("#country-wait-chart"), countryInsightsLastDraw.wait, { xLabel: "minutes" });
  if (countryInsightsLastDraw.distance)
    renderHistogram($$("#country-distance-chart"), countryInsightsLastDraw.distance, { xLabel: "kilometres" });
}

function countryWikiApi(title, params) {
  return (
    COUNTRY_WIKI_BASE + "api.php?action=parse&redirects=1&format=json&origin=*" +
    params + "&page=" + encodeURIComponent(title)
  );
}

// Find the index of the top-level "== Hitchhiking ==" section, or null if the
// article has none. Country articles usually put the practical advice under this
// heading, which is more useful than the lead's generic intro.
async function findHitchhikingSection(title) {
  try {
    const data = await fetch(countryWikiApi(title, "&prop=sections")).then((r) => r.json());
    const sections = (data && data.parse && data.parse.sections) || [];
    const match = sections.find(
      (s) => s.toclevel === 1 && s.line && s.line.trim().toLowerCase() === "hitchhiking"
    );
    return match ? match.index : null;
  } catch (e) {
    return null;
  }
}

// Fetch and render a country's Hitchwiki summary: the "== Hitchhiking ==" section
// when present, otherwise the lead section.
async function loadCountrySheetLead(name) {
  const title = COUNTRY_WIKI_TITLE_ALIASES[name] || name;
  const wikiUrl = COUNTRY_WIKI_BASE + encodeURIComponent(title.replace(/ /g, "_"));
  $$("#country-sheet-source").innerHTML =
    `Text from <a href="${wikiUrl}" target="_blank" rel="noopener">Hitchwiki: ${escapeHtml(title)}</a>, ` +
    `licensed <a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noopener">CC BY-SA</a>.`;

  const lead = $$("#country-sheet-lead");
  try {
    // Prefer the Hitchhiking section; fall back to the lead (section 0).
    const section = (await findHitchhikingSection(title)) || "0";
    const data = await fetch(countryWikiApi(title, "&prop=wikitext&section=" + section)).then((r) => r.json());
    const wikitext = data && data.parse && data.parse.wikitext && data.parse.wikitext["*"];
    if (!wikitext) {
      lead.innerHTML = `<p class="country-status">No Hitchwiki summary could be loaded for ${escapeHtml(name)}.</p>`;
      return;
    }
    const html = renderCountryWikitext(wikitext);
    lead.innerHTML = html || `<p class="country-status">No summary text available for ${escapeHtml(name)}.</p>`;
  } catch (e) {
    console.warn("Could not load Hitchwiki section:", e);
    lead.innerHTML = `<p class="country-status">No Hitchwiki summary could be loaded for ${escapeHtml(name)}.</p>`;
  }
}

// Open the country info sheet for `name` (invoked from navigate() via #country/<name>).
async function openCountrySheet(name) {
  clear();
  $$("#country-sheet-name").textContent = name;
  $$("#country-sheet-rating").style.display = "none";
  $$("#country-sheet-insights").hidden = true;
  $$("#country-sheet-lead").innerHTML = `<p class="country-status">Loading from Hitchwiki…</p>`;
  $$("#country-sheet-source").innerHTML = "";
  bar(".sidebar.country");
  updateBottomPaneVar();
  setSheetSnap($$(".sidebar.country"), "full", COUNTRY_SHEET_SNAPS);
  loadCountrySheetLead(name);
  // Rating + histograms are keyed by ISO code, resolved from the country name.
  const cc = await getCountryCc(name);
  loadCountrySheetRating(cc);
  loadCountryInsights(cc);
}

// Show or hide the hitchhiking-spot markers (hidden in Countries mode).
function setSpotsVisible(visible) {
  if (!markerCluster) return;
  if (visible) {
    if (!map.hasLayer(markerCluster)) markerCluster.addTo(map);
  } else if (map.hasLayer(markerCluster)) {
    map.removeLayer(markerCluster);
  }
}

// --- Hitchwiki events ---------------------------------------------------------
// Load dist/events.json (upcoming/ongoing Category:Event markers) and draw each as
// a distinct calendar-pin marker on its own layer, so events stand out from spots
// and can be shown/hidden independently of the spot markers.
async function loadEventMarkers(map) {
  try {
    const resp = await fetch("/events.json");
    if (!resp.ok) return; // no events file yet (e.g. sync hasn't run) — silently skip
    eventsData = await resp.json();
  } catch (error) {
    console.warn("Could not load events:", error);
    return;
  }
  if (!Array.isArray(eventsData) || eventsData.length === 0) return;

  eventLayer = L.layerGroup();
  eventsData.forEach((ev) => {
    if (typeof ev.lat !== "number" || typeof ev.lon !== "number") return;
    const icon = L.divIcon({
      className: "event-marker",
      html: '<div class="event-marker-pin">🎪</div>',
      iconSize: [30, 30],
      iconAnchor: [15, 15],
    });
    const marker = L.marker([ev.lat, ev.lon], { icon, title: ev.name });
    marker.on("click", (e) => {
      L.DomEvent.stopPropagation(e);
      openEventSheet(ev);
    });
    marker.addTo(eventLayer);
  });

  // Events follow the spot markers: visible in spots/heatmap modes, hidden in Countries.
  if (mapMode !== "countries") eventLayer.addTo(map);
  console.log(`Loaded ${eventsData.length} event(s)`);
}

function setEventsVisible(visible) {
  if (!eventLayer) return;
  if (visible) {
    if (!map.hasLayer(eventLayer)) eventLayer.addTo(map);
  } else if (map.hasLayer(eventLayer)) {
    map.removeLayer(eventLayer);
  }
}

// Render one proposed spot as a blue circle marker — same shape/size as the normal
// rating markers (so it reads as a spot), only blue to mark it as "proposed, no rides
// yet". Added to the SAME markerCluster as real spots so the two cluster together.
// Kept OUT of allMarkers: it has no ride data, so the ride filters and pin-snapping
// (which read _data ride fields / spotId) must not iterate over it. Returns the marker.
function addProposedSpotMarker(sp) {
  if (!markerCluster || typeof sp.lat !== "number" || typeof sp.lon !== "number") return null;
  const marker = L.circleMarker(new L.latLng(sp.lat, sp.lon), {
    radius: 5,
    weight: 1,
    fillOpacity: 0.85,
    color: "black",
    fillColor: "#1a73e8",
    _proposed: true,
  });
  const who = sp.user ? escapeHtml(sp.user) : "someone";
  const when = sp.created_at ? relativeAge(sp.created_at) : "";
  const comment = sp.comment ? `<p class="proposed-spot-comment">${escapeHtml(sp.comment)}</p>` : "";
  marker.bindPopup(
    `<div class="proposed-spot-popup">` +
      `<strong>Proposed spot</strong>` +
      comment +
      `<p class="proposed-spot-meta">Proposed by ${who}${when ? " · " + when : ""}. No rides logged here yet.</p>` +
      `</div>`
  );
  marker.addTo(markerCluster);
  return marker;
}

// Human-readable "3d ago" / "2h ago" from an ISO timestamp; "" if unparseable.
function relativeAge(iso) {
  const t = new Date(iso);
  if (isNaN(t)) return "";
  const s = Math.floor((Date.now() - t.getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  return Math.floor(s / 86400) + "d ago";
}

// Load /proposed_spots.json (served live from the DB) and add each as a blue circle
// marker into the shared spot cluster. Non-blocking overlay, like loadEventMarkers.
// Must run after loadMarkers (which creates markerCluster).
async function loadProposedSpotMarkers(map) {
  let data;
  try {
    const resp = await fetch("/proposed_spots.json");
    if (!resp.ok) return; // endpoint missing / errored — silently skip
    data = await resp.json();
  } catch (error) {
    console.warn("Could not load proposed spots:", error);
    return;
  }
  if (!Array.isArray(data)) return;
  data.forEach(addProposedSpotMarker);
  console.log(`Loaded ${data.length} proposed spot(s)`);
}

// Begin proposing a spot from a map gesture (long-press → "Propose a spot"): drop a
// draggable blue pin and show a card with a short-comment box. On submit, POST to
// /propose-spot and drop the persistent blue marker immediately (no reload needed).
function startProposeSpotFromGesture(latlng, containerPoint) {
  // One picker at a time — bail if a location selection or another propose card is up.
  if (locationSelectionType || locationSelectionMarker) return;
  if (document.querySelector(".propose-spot-ui")) return;

  const pin = L.marker(latlng, {
    draggable: true,
    icon: L.icon({
      iconUrl: "/static/markers/marker-icon-2x-grey.png",
      shadowUrl: "/static/markers/marker-shadow.png",
      iconSize: [25, 41],
      iconAnchor: [12, 41],
      popupAnchor: [1, -34],
      shadowSize: [41, 41],
    }),
  }).addTo(map);

  // Tapping the map repositions the pin (mirrors the add-spot / waiting-spot UX).
  const onMapClick = (e) => pin.setLatLng(e.latlng);
  map.on("click", onMapClick);

  const ui = L.DomUtil.create("div", "propose-spot-ui location-selection-ui");
  ui.innerHTML =
    "<h4>Propose a hitch spot</h4>" +
    "<p>Drag the pin to fine-tune, add a short note (optional), then propose.</p>" +
    '<textarea class="propose-spot-comment" maxlength="500" rows="2" ' +
    'placeholder="Why is this a good spot? (optional)"></textarea>' +
    '<div class="lsel-actions">' +
    '<button class="lsel-confirm">Propose spot</button>' +
    '<button class="lsel-cancel">Cancel</button>' +
    "</div>";
  document.body.appendChild(ui);
  document.body.classList.add("selecting-location");

  function cleanup() {
    map.off("click", onMapClick);
    if (pin) map.removeLayer(pin);
    if (ui.parentNode) ui.remove();
    document.body.classList.remove("selecting-location");
  }

  ui.querySelector(".lsel-cancel").addEventListener("click", () => {
    cleanup();
    history.replaceState(null, null, " ");
  });

  const confirmBtn = ui.querySelector(".lsel-confirm");
  confirmBtn.addEventListener("click", async () => {
    confirmBtn.disabled = true;
    const ll = pin.getLatLng();
    const comment = ui.querySelector(".propose-spot-comment").value.trim();
    const body = new URLSearchParams({ lat: ll.lat, lon: ll.lng, comment });
    try {
      const resp = await fetch("/propose-spot", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });
      const json = await resp.json().catch(() => ({}));
      if (!resp.ok || !json.ok) throw new Error(json.error || "request failed");
      // Show the new proposed spot right away — don't wait for a reload.
      const m = addProposedSpotMarker({
        id: json.id,
        lat: round5(ll.lat),
        lon: round5(ll.lng),
        comment,
        user: (typeof USERNAME !== "undefined" && USERNAME) || "",
        created_at: new Date().toISOString(),
      });
      cleanup();
      history.replaceState(null, null, " ");
      if (m) m.openPopup();
    } catch (err) {
      console.error("Could not propose spot:", err);
      confirmBtn.disabled = false;
      alert("Sorry, could not save your proposed spot. Please try again.");
    }
  });
}

// Round to the 5 decimals the server stores/serves for proposed spots, so the
// optimistically-added marker sits exactly where a reload would place it.
function round5(n) {
  return Math.round(n * 1e5) / 1e5;
}

// Format an event's date range for the sheet, e.g. "1 Jul – 30 Aug 2026".
function formatEventDates(ev) {
  const opts = { day: "numeric", month: "short", year: "numeric" };
  const end = ev.end ? new Date(ev.end) : null;
  const start = ev.start ? new Date(ev.start) : null;
  const fmt = (d) => (d && !isNaN(d) ? d.toLocaleDateString(undefined, opts) : null);
  const s = fmt(start);
  const e = fmt(end);
  if (s && e) return `${s} – ${e}`;
  return e || s || "";
}

function openEventSheet(ev) {
  clear();
  $$("#event-sheet-name").textContent = ev.name || "Event";
  $$("#event-sheet-dates").textContent = formatEventDates(ev);
  const wikiUrl = ev.url || COUNTRY_WIKI_BASE + encodeURIComponent((ev.title || ev.name || "").replace(/ /g, "_"));
  $$("#event-sheet-source").innerHTML = ev.title
    ? `Text from <a href="${escapeHtml(wikiUrl)}" target="_blank" rel="noopener">Hitchwiki: ${escapeHtml(ev.title)}</a>, ` +
      `licensed <a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noopener">CC BY-SA</a>.`
    : "";
  $$("#event-sheet-description").innerHTML = `<p class="sheet-status">Loading from Hitchwiki…</p>`;
  bar(".sidebar.event");
  updateBottomPaneVar();
  setSheetSnap($$(".sidebar.event"), "full", EVENT_SHEET_SNAPS);
  map.panTo([ev.lat, ev.lon]);
  loadEventSheetText(ev);
}

// Resolve the page-name magic words MediaWiki would normally expand server-side
// ({{FULLPAGENAME}}, {{PAGENAME}}, {{BASEPAGENAME}}, {{SUBPAGENAME}}). We render raw
// wikitext client-side, so these stay literal and — worse — get dropped by the
// template stripper, leaving gaps like a stray '''''' bold. Substitute them with the
// actual page title before rendering. The trailing "E" variants are URL-encoded forms.
function substituteWikiPageName(wikitext, title) {
  const base = title.includes("/") ? title.slice(0, title.lastIndexOf("/")) : title;
  const sub = title.includes("/") ? title.slice(title.lastIndexOf("/") + 1) : title;
  return wikitext
    .replace(/\{\{\s*(?:FULLPAGENAME|PAGENAME)E?\s*\}\}/gi, title)
    .replace(/\{\{\s*BASEPAGENAMEE?\s*\}\}/gi, base)
    .replace(/\{\{\s*SUBPAGENAMEE?\s*\}\}/gi, sub);
}

// Fetch the event's full Hitchwiki page and render it with the same MediaWiki
// reader used for country pages (renderCountryWikitext), so the sheet shows the
// complete page text with working links instead of a truncated server excerpt.
// Falls back to the server-extracted blurb in events.json if the live fetch fails.
async function loadEventSheetText(ev) {
  const body = $$("#event-sheet-description");
  try {
    // No section param → the whole page's wikitext.
    const data = await fetch(countryWikiApi(ev.title, "&prop=wikitext")).then((r) => r.json());
    let wikitext = data && data.parse && data.parse.wikitext && data.parse.wikitext["*"];
    if (wikitext) {
      wikitext = substituteWikiPageName(wikitext, ev.title || ev.name || "");
      // Category tags aren't prose; renderCountryWikitext would otherwise turn
      // [[Category:Events]] into a stray link at the end of the article.
      wikitext = wikitext.replace(/\[\[Category:[^\]]*\]\]/gi, "");
      const html = renderCountryWikitext(wikitext);
      if (html) {
        body.innerHTML = html;
        return;
      }
    }
  } catch (e) {
    console.warn("Could not load event page from Hitchwiki:", e);
  }
  const desc = (ev.description || "").trim();
  body.innerHTML = desc
    ? desc.split(/\n\n+/).map((p) => `<p>${escapeHtml(p).replace(/\n/g, "<br>")}</p>`).join("")
    : `<p class="sheet-status">No description available.</p>`;
}

// Single source of truth for which map mode is active.
async function setMapMode(mode) {
  mapMode = mode;

  // Countries mode replaces spots with the choropleth; the other modes show spots.
  if (mode === "countries") {
    await setHeatmapActive(false);
    setSpotsVisible(false);
    setEventsVisible(false);
    const layer = await loadCountryLayer();
    if (!map.hasLayer(layer)) layer.addTo(map);
  } else {
    if (countryLayer && map.hasLayer(countryLayer)) map.removeLayer(countryLayer);
    setSpotsVisible(true);
    setEventsVisible(true);
    await setHeatmapActive(mode === "heatmap");
  }

  updateMapModeButtons();
  // Keep the state shareable. Heatmap keeps using the legacy ?heatmap param so
  // existing deep-links stay valid; Countries mode uses ?mapmode=countries.
  setQueryParameter("heatmap", mode === "heatmap");
  setQueryParameter("mapmode", mode === "countries" ? "countries" : false);
}

function updateMapModeButtons() {
  Object.entries(mapModeButtons).forEach(([mode, btn]) => {
    btn.classList.toggle("active", mode === mapMode);
    btn.setAttribute("aria-pressed", mode === mapMode ? "true" : "false");
  });
  // Keep the legacy bottom-pane heatmap button in sync with the switcher.
  const legacyBtn = $$("#heatmap-toggle-btn");
  const legacyText = $$("#heatmap-toggle-text");
  if (legacyBtn) legacyBtn.classList.toggle("active", mapMode === "heatmap");
  if (legacyText) legacyText.textContent = mapMode === "heatmap" ? "Normal" : "Heatmap";
}

// ── Test-mode easter egg ────────────────────────────────────────────────────
// Tap the heatmap mode button 9× to toggle a client-side "test mode": in-ride
// submissions are short-circuited (inride.js submitBody) so nothing reaches the
// real DB/Nostr while testing on-device. A countdown shows from the 4th tap; a
// yellow bar under the search bar marks it active — tap the bar to exit.
const TEST_MODE_KEY = "inride.testMode";
const TEST_MODE_TAPS = 9;
const TEST_MODE_COUNTDOWN_FROM = 4; // start showing "N more taps" at this tap
const TEST_BTN_POS_KEY = "inride.testBtnPos"; // remembered drag position of the indicator

function isTestMode() {
  try { return localStorage.getItem(TEST_MODE_KEY) === "1"; } catch (e) { return false; }
}

function setTestMode(on) {
  try {
    if (on) localStorage.setItem(TEST_MODE_KEY, "1");
    else localStorage.removeItem(TEST_MODE_KEY);
  } catch (e) {}
  renderTestModeIndicator();
}

function isLegendVisible() {
  const lp = document.getElementById("heatmap-legend-pane");
  return !!(lp && lp.style.display === "block");
}

// Drop the test-mode button + callout below the heatmap legend bar while it shows.
function setTestBtnBelowLegend(below) {
  const btn = document.getElementById("test-mode-btn");
  const callout = document.getElementById("test-mode-callout");
  if (btn) btn.classList.toggle("below-legend", below);
  if (callout) callout.classList.toggle("below-legend", below);
}

// Round amber warning button (same size as the account avatar), under the search
// bar. Tapping it opens a callout explaining test mode + an exit action.
function renderTestModeIndicator() {
  let btn = document.getElementById("test-mode-btn");
  if (isTestMode()) {
    if (!btn) {
      btn = document.createElement("button");
      btn.id = "test-mode-btn";
      btn.type = "button";
      btn.className = "test-mode-btn";
      btn.setAttribute("aria-label", "Test mode is on — what does this mean?");
      btn.innerHTML = '<i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>';
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        toggleTestModeCallout();
      });
      makeTestBtnDraggable(btn);
      document.body.appendChild(btn);
      restoreTestBtnPos(btn); // after append so offsetWidth/Height are known
    }
    // Auto-drop below the heatmap legend only while the user hasn't hand-placed it.
    if (!hasTestBtnPos()) btn.classList.toggle("below-legend", isLegendVisible());
  } else {
    if (btn) btn.remove();
    closeTestModeCallout();
  }
}

function hasTestBtnPos() {
  try { return !!localStorage.getItem(TEST_BTN_POS_KEY); } catch (e) { return false; }
}

// Apply a previously dragged position (clamped to the current viewport).
function restoreTestBtnPos(btn) {
  let pos = null;
  try { pos = JSON.parse(localStorage.getItem(TEST_BTN_POS_KEY) || "null"); } catch (e) {}
  if (!pos) return;
  btn.style.left = Math.max(4, Math.min(window.innerWidth - btn.offsetWidth - 4, pos.left)) + "px";
  btn.style.top = Math.max(4, Math.min(window.innerHeight - btn.offsetHeight - 4, pos.top)) + "px";
  btn.style.bottom = "auto";
  btn.classList.remove("below-legend");
}

// Make the indicator draggable so it can be moved out of the way. A press-and-
// release still counts as a tap (opens the callout); movement past a small
// threshold is a drag, and the resting position is remembered across reloads.
function makeTestBtnDraggable(btn) {
  let dragging = false, moved = false, sx = 0, sy = 0, ox = 0, oy = 0, pid = null;
  const THRESH = 6;
  btn.style.touchAction = "none";
  btn.addEventListener("pointerdown", function (e) {
    pid = e.pointerId;
    const r = btn.getBoundingClientRect();
    sx = e.clientX; sy = e.clientY; ox = r.left; oy = r.top;
    moved = false; dragging = true;
    try { btn.setPointerCapture(pid); } catch (e2) {}
  });
  btn.addEventListener("pointermove", function (e) {
    if (!dragging) return;
    const dx = e.clientX - sx, dy = e.clientY - sy;
    if (!moved && Math.hypot(dx, dy) < THRESH) return;
    moved = true;
    closeTestModeCallout(); // don't leave a stray callout mid-drag
    btn.style.left = Math.max(4, Math.min(window.innerWidth - btn.offsetWidth - 4, ox + dx)) + "px";
    btn.style.top = Math.max(4, Math.min(window.innerHeight - btn.offsetHeight - 4, oy + dy)) + "px";
    btn.style.bottom = "auto";
    btn.classList.remove("below-legend"); // hand-placed now — stop auto-positioning
  });
  function end() {
    if (!dragging) return;
    dragging = false;
    try { btn.releasePointerCapture(pid); } catch (e2) {}
    if (moved) {
      try {
        localStorage.setItem(TEST_BTN_POS_KEY, JSON.stringify({
          left: parseInt(btn.style.left, 10),
          top: parseInt(btn.style.top, 10),
        }));
      } catch (e2) {}
    }
  }
  btn.addEventListener("pointerup", end);
  btn.addEventListener("pointercancel", end);
  // Swallow the click that follows a drag so it doesn't also toggle the callout.
  btn.addEventListener("click", function (e) {
    if (moved) { e.stopImmediatePropagation(); e.preventDefault(); moved = false; }
  }, true);
}

let _testCalloutOutside = null;
function closeTestModeCallout() {
  const c = document.getElementById("test-mode-callout");
  if (c) c.remove();
  if (_testCalloutOutside) {
    document.removeEventListener("click", _testCalloutOutside, true);
    _testCalloutOutside = null;
  }
}

function toggleTestModeCallout() {
  if (document.getElementById("test-mode-callout")) { closeTestModeCallout(); return; }
  const c = document.createElement("div");
  c.id = "test-mode-callout";
  c.className = "test-mode-callout";
  c.innerHTML =
    '<div class="test-mode-callout__title">🧪 Test mode is on</div>' +
    '<p class="test-mode-callout__body">Rides you finish or give up are <strong>not saved</strong> — ' +
    "nothing is published to the map, the database, or Nostr. Use it to try the flow without " +
    "adding real data. Turn it back on any time by tapping the heatmap button 9 times.</p>";
  const exit = document.createElement("button");
  exit.type = "button";
  exit.className = "test-mode-callout__exit";
  exit.textContent = "Exit test mode";
  exit.addEventListener("click", function () {
    setTestMode(false); // removes the button + closes this callout via renderTestModeIndicator
    showTestToast("Test mode off");
  });
  c.appendChild(exit);
  document.body.appendChild(c);
  // Anchor the callout just below the button, wherever it currently sits (it's
  // draggable), and point the arrow at the button's centre.
  const anchor = document.getElementById("test-mode-btn");
  if (anchor) {
    const r = anchor.getBoundingClientRect();
    const cl = Math.max(8, Math.min(window.innerWidth - c.offsetWidth - 8, r.left));
    c.style.left = cl + "px";
    c.style.top = (r.bottom + 8) + "px";
    c.style.bottom = "auto";
    c.style.setProperty("--arrow-x", Math.max(10, Math.min(c.offsetWidth - 20, r.left + r.width / 2 - cl - 7)) + "px");
  }
  // Dismiss on any outside click (capture phase so it beats other handlers). The
  // button's own click is stopPropagation'd, so it won't immediately re-close.
  _testCalloutOutside = function (e) {
    if (!c.contains(e.target) && !e.target.closest("#test-mode-btn")) closeTestModeCallout();
  };
  setTimeout(function () { document.addEventListener("click", _testCalloutOutside, true); }, 0);
}

let _testToastTimer = null;
function showTestToast(msg) {
  let t = document.getElementById("test-mode-toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "test-mode-toast";
    t.className = "test-mode-toast";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  if (_testToastTimer) clearTimeout(_testToastTimer);
  _testToastTimer = setTimeout(function () { if (t && t.parentNode) t.remove(); }, 1500);
}

let _heatTapCount = 0;
let _heatTapResetTimer = null;
// Called on every tap of the heatmap mode button (in addition to its normal toggle).
function registerHeatmapTap() {
  if (isTestMode()) return; // already active — taps just toggle the heatmap normally
  _heatTapCount++;
  // Reset the streak if taps stop for a moment so stray clicks don't accumulate.
  if (_heatTapResetTimer) clearTimeout(_heatTapResetTimer);
  _heatTapResetTimer = setTimeout(function () { _heatTapCount = 0; }, 2000);

  if (_heatTapCount >= TEST_MODE_TAPS) {
    _heatTapCount = 0;
    clearTimeout(_heatTapResetTimer);
    setTestMode(true);
    showTestToast("🧪 Test mode on — rides won't be saved");
    return;
  }
  if (_heatTapCount >= TEST_MODE_COUNTDOWN_FROM) {
    const remaining = TEST_MODE_TAPS - _heatTapCount;
    showTestToast(remaining + (remaining === 1 ? " more tap" : " more taps") + " to test mode…");
  }
}

// Vertical Spots/Heatmap/Countries switcher, sitting just above the locate button.
function setupMapModeControl() {
  const modes = [
    { mode: "spots", icon: "fa-solid fa-thumbs-up", title: "Spots" },
    { mode: "heatmap", icon: "fa fa-fire", title: "Waiting-time heatmap" },
    { mode: "countries", icon: "fa-solid fa-earth-europe", title: "Country hitchability" },
  ];
  const ModeControl = L.Control.extend({
    options: { position: "bottomright" },
    onAdd: function () {
      const container = L.DomUtil.create("div", "leaflet-bar mapmode-control");
      modes.forEach(({ mode, icon, title }) => {
        const btn = L.DomUtil.create("a", "mapmode-btn", container);
        btn.href = "#";
        btn.title = title;
        btn.setAttribute("role", "button");
        btn.setAttribute("aria-label", title);
        btn.innerHTML = `<i class="${icon}" aria-hidden="true"></i>`;
        L.DomEvent.on(btn, "click", function (e) {
          L.DomEvent.preventDefault(e);
          // Easter egg: 9 taps on the heatmap button toggles test mode.
          if (mode === "heatmap") registerHeatmapTap();
          setMapMode(mode);
        });
        mapModeButtons[mode] = btn;
      });
      L.DomEvent.disableClickPropagation(container);
      return container;
    },
  });
  new ModeControl().addTo(map);
  updateMapModeButtons();
}

// ---- One-time feature pointers -------------------------------------------
// Ordered queue: each entry drops a red pointer next to a feature's button, shown
// ONCE per user (a boolean flag in localStorage — no reappear window). At most ONE
// pointer is shown per page load: the first not-yet-seen hint whose button is
// visible. Clicking that button dismisses it for good, and the next hint waits for
// the next page load rather than appearing immediately — several of these buttons
// are neighbours (filter sits 38px from route), so chaining them in place reads as
// an arrow that refused to go away rather than as a new hint.
//
// `el` is resolved lazily because the search-bar buttons are created by Leaflet
// controls after this module is evaluated. `placement` picks which side of the
// button the arrow sits on: the mode switcher is docked bottom-right (arrow to
// its left), the search bar sits at the top (arrow below it), and the action
// pane at the bottom (arrow above it).
const FEATURE_HINTS = [
  { key: "hintSeen.heatmap", el: () => mapModeButtons.heatmap, placement: "left" },
  { key: "hintSeen.countries", el: () => mapModeButtons.countries, placement: "left" },
  { key: "hintSeen.routes", el: () => $$(".geocoder-route-btn"), placement: "below" },
  { key: "hintSeen.filters", el: () => $$(".geocoder-filter-btn"), placement: "below" },
  { key: "hintSeen.activities", el: () => $$("#action-activities"), placement: "above" },
];

const HINT_ARROW_ICON = { left: "fa-arrow-right", below: "fa-arrow-up", above: "fa-arrow-down" };

function hintSeen(key) {
  // If storage is blocked, treat as seen so we never nag users we can't remember.
  try { return localStorage.getItem(key) === "1"; } catch (e) { return true; }
}
function markHintSeen(key) {
  try { localStorage.setItem(key, "1"); } catch (e) {}
}

function showNextFeatureHint() {
  // A button can be absent on pages that hide it (e.g. embeds). Skip past those
  // without marking the hint seen, so it can still be shown on a full map page.
  let hint, btn;
  for (const h of FEATURE_HINTS) {
    if (hintSeen(h.key)) continue;
    const el = h.el();
    if (el && el.offsetParent !== null) { hint = h; btn = el; break; }
  }
  if (!hint) return; // all features already tried, or none of their buttons exist here

  const pointer = document.createElement("div");
  pointer.className = `mode-hint-pointer mode-hint-pointer--${hint.placement}`;
  pointer.innerHTML = `<i class="fa-solid ${HINT_ARROW_ICON[hint.placement]}" aria-hidden="true"></i>`;
  document.body.appendChild(pointer);

  // The pointer is a fixed-position child of <body>, so it does not inherit its
  // target's visibility: opening the routing sheet hides the whole search bar and
  // would otherwise leave the arrow stranded over nothing. Re-check on every
  // reposition and hide alongside the button.
  function position() {
    if (btn.offsetParent === null) {
      pointer.style.display = "none";
      return;
    }
    pointer.style.display = "";
    const r = btn.getBoundingClientRect();
    if (hint.placement === "left") {
      pointer.style.top = `${r.top + r.height / 2}px`;
      pointer.style.right = `${window.innerWidth - r.left + 8}px`;
    } else {
      pointer.style.left = `${r.left + r.width / 2}px`;
      if (hint.placement === "below") pointer.style.top = `${r.bottom + 8}px`;
      else pointer.style.bottom = `${window.innerHeight - r.top + 8}px`;
    }
  }
  position();
  window.addEventListener("resize", position);
  // Sheets that hide the arrow's target are opened by hash navigation (#routing,
  // #menu, …) and closed by either a hash change or the back button, which fires
  // popstate instead. Re-run the visibility check on both.
  window.addEventListener("hashchange", position);
  window.addEventListener("popstate", position);
  // Some chrome shifts come from a body-class toggle, not a resize/hash/popstate —
  // notably `body.inride-active`, which lifts the whole bottom-right control stack
  // ~150px so it clears the ride dock. That moves a "left" hint's target (heatmap /
  // countries) without any of the events above, stranding the arrow over empty space.
  // Observe body's class so position() re-runs on every such toggle.
  const bodyClassObserver = new MutationObserver(position);
  bodyClassObserver.observe(document.body, { attributes: true, attributeFilter: ["class"] });

  function dismiss(ev) {
    if (ev && !btn.contains(ev.target)) return;
    markHintSeen(hint.key);
    pointer.remove();
    window.removeEventListener("resize", position);
    window.removeEventListener("hashchange", position);
    window.removeEventListener("popstate", position);
    bodyClassObserver.disconnect();
    document.removeEventListener("pointerdown", dismiss, true);
    document.removeEventListener("click", dismiss, true);
  }
  // Dismissal is using the feature itself — no banner, no close button. Both hint
  // buttons live inside Leaflet controls that stop event propagation, and the route
  // button is an <a href="#routing"> that opens a sheet the moment it is pressed —
  // so a plain bubble-phase "click" on the button is not reliably delivered. Listen
  // on the document in the capture phase (nothing can swallow it first) and accept
  // pointerdown too, so a tap counts even when no click follows it.
  document.addEventListener("pointerdown", dismiss, true);
  document.addEventListener("click", dismiss, true);
}

function setupLocateControl() {
  const LocateControl = L.Control.extend({
    options: { position: "bottomright" },
    onAdd: function () {
      const container = L.DomUtil.create("div", "leaflet-bar locate-control");
      const btn = L.DomUtil.create("a", "locate-control-btn", container);
      btn.href = "#";
      btn.title = "Show my location";
      btn.setAttribute("role", "button");
      btn.setAttribute("aria-label", "Show my location");
      btn.innerHTML = '<i class="fa-solid fa-location-crosshairs" aria-hidden="true"></i>';
      // Keep taps on the button from reaching the map (pan/zoom/add-point).
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.on(btn, "click", function (e) {
        L.DomEvent.preventDefault(e);
        requestLocation();
      });
      locateButtonEl = btn;
      return container;
    },
  });
  new LocateControl().addTo(map);
  map.on("locationfound", showLocation);
  map.on("locationerror", onLocationError);
}

// Set up various event listeners for the map and UI elements
function setupEventListeners() {
  $$("#sb-close").onclick = navigateHome;
  setupSpotSheet();
  setupMenuSheet();
  setupRoutingSheet();
  setupCountrySheet();
  setupEventSheet();
  const reportDup = $$(".report-dup");
  if (reportDup) reportDup.onclick = () =>
    document.body.classList.add("reporting-duplicate");
  $$(".topbar.duplicate button").onclick = () =>
    document.body.classList.remove("reporting-duplicate");


  map.on("click", handleMapClick);
  map.on("zoom", () =>
    document.body.classList.toggle("zoomed-out", map.getZoom() < 9)
  );

  // Long-press (touch) / right-click (desktop) drops a pin to add a hitch site.
  setupAddSpotGesture();

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
      // Reflect the menu in the address bar as #menu (like #routing) so it's
      // deep-linkable and the back button closes it. navigate() does the actual
      // pane work via the hashchange handler.
      if (document.body.classList.contains("menu")) {
        navigateHome();
      } else {
        location.hash = "menu";
      }
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

  // Country-choropleth pane. Sits above the default overlay pane (z 400) so its
  // SVG paths receive clicks — the map uses preferCanvas, and an empty overlay
  // canvas would otherwise swallow clicks meant for the choropleth — but stays
  // below the marker pane (z 600). The layer is rendered as SVG (not canvas) so
  // clicks land on filled countries while ocean gaps pass through.
  let countryPane = map.createPane("countries");
  countryPane.style.zIndex = 450;
}

// Handle map click events
function handleMapClick(e) {
  // A tap on a Leaflet control (GPS button, zoom, search, mode switcher) is not
  // a map tap. disableClickPropagation suppresses the map click on desktop, but a
  // touch-simulated click still reaches this handler — and the tap-to-nearest-spot
  // shortcut below fires the closest marker by *coordinates*, so a spot sitting
  // under the control would open. Ignore clicks originating on a control.
  const oe = e.originalEvent;
  if (oe && oe.target && oe.target.closest && oe.target.closest(".leaflet-control")) return;

  // While selecting a location, every tap is meant to place/move the endpoint
  // pin (handled by locationSelectionClickHandler). Bail out before the
  // tap-to-nearest-spot shortcut below, which would otherwise fire a nearby
  // spot's click — opening its popup or navigating away and tearing down the
  // selection, which is exactly what forced the user to tap several times.
  if (locationSelectionType) return;

  // While the routing planner is open, map clicks set the start/destination
  // (handled by routing.js onMapClick) — don't also drop a spot pin here.
  if (window.RoutingUI && window.RoutingUI.active) return;

  var added = false;
  // Countries mode hides the spot markers (but keeps them in `allMarkers`), so
  // skip the tap-to-nearest-spot shortcut — otherwise tapping a country would
  // open an underlying spot instead of the country sheet.
  if (window.innerWidth < 780 && mapMode !== "countries") {
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
  fuelToggle.addEventListener("input", () =>
    setQueryParameter("fuelonly", fuelToggle.checked)
  );
  fuelIconToggle.addEventListener("click", () => fuelToggle.click());
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
  minRatingFilter.addEventListener("input", () =>
    setQueryParameter("minrating", minRatingFilter.value)
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
  // Initial viewport, most specific statement of intent first: an explicit
  // #map= from a shared link, else the spot the path names, else the view this
  // browser last left the map at, else the world.
  const hashView = parseMapHash(window.location.hash);
  const spot = spotFromUrl();
  if (hashView) {
    map.setView([hashView.lat, hashView.lon], hashView.zoom);
  } else if (spot) {
    // A bare /spot/<id> link should frame the spot, not whatever view
    // localStorage happens to remember from this browser's last visit.
    map.setView([spot.lat, spot.lon], 16);
  } else if (!window.location.hash.includes(",")) {
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

  // Clamp an over-zoomed restored view, but never a zoom the URL asked for
  // explicitly — silently rewriting a shared #map=18/… link to 17 would mean
  // the recipient doesn't see what the sender saw.
  if (!hashView && map.getZoom() > 17 && window.location.hash != "#success-duplicate")
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

// A spot needs at least this many rides carrying a value before its distribution is
// worth drawing — below that the bars say nothing the average doesn't already say.
const SPOT_HIST_MIN_SAMPLES = 10;
// Histograms currently drawn in the spot pane, kept so a resize can repaint them
// (a canvas loses its contents whenever its backing store is resized).
let spotHistograms = { wait: null, distance: null };

// Bin one field of the open spot's rides. Returns null when there are too few
// values, so callers omit the chart entirely.
function spotHistogram(rides, field) {
  if (!rides) return null;
  const values = rides
    .map((r) => r[field])
    .filter((v) => typeof v === "number" && !Number.isNaN(v));
  if (values.length < SPOT_HIST_MIN_SAMPLES) return null;
  // Same mean ± 3σ clipping as the insights and country charts: a single 900-minute
  // wait must not squash every other bar into the first bin.
  return computeHistogram(clipForHistogram(values).values);
}

function formatHistBound(v) {
  return Math.abs(v) < 10 && !Number.isInteger(v) ? v.toFixed(1) : Math.round(v).toString();
}

// Markup for one compact distribution strip. The canvas is painted afterwards
// (drawSpotHistograms) because it has no size until it is in the document.
function spotHistogramMarkup(hist, id, unit) {
  if (!hist) return "";
  return `<div class="spot-hist">
      <canvas id="${id}" class="spot-hist-chart" aria-label="Distribution of ${unit === "min" ? "waiting time" : "ride distance"}"></canvas>
      <div class="spot-hist-axis"><span>${formatHistBound(hist.lo)}</span><span>${formatHistBound(hist.hi)} ${unit}</span></div>
    </div>`;
}

// Deliberately axis-less and short: the spot pane's job is the ride list, so the
// distribution is a shape hint under the average, not a full chart.
function renderMiniHistogram(canvas, hist) {
  if (!canvas || !hist) return;
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || 260;
  const cssH = canvas.clientHeight || 34;
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  const counts = hist.counts;
  const bins = counts.length;
  const maxCount = Math.max(...counts);
  if (!maxCount) return;

  const baseline = cssH - 1;
  const gap = bins > 20 ? 1 : 2;
  for (let i = 0; i < bins; i++) {
    if (!counts[i]) continue;
    const bw = cssW / bins - gap;
    const bx = (i / bins) * cssW + gap / 2;
    // Floor the height at 1px so a bin holding a single ride stays visible next to a tall one.
    const bh = Math.max(1, (counts[i] / maxCount) * (baseline - 1));
    const by = baseline - bh;
    const grad = ctx.createLinearGradient(0, by, 0, baseline);
    grad.addColorStop(0, INSIGHTS_BAR_COLOR_TOP);
    grad.addColorStop(1, INSIGHTS_BAR_COLOR);
    ctx.fillStyle = grad;
    const r = Math.min(2, bw / 2, bh);
    ctx.beginPath();
    if (typeof ctx.roundRect === "function") ctx.roundRect(bx, by, bw, bh, [r, r, 0, 0]);
    else ctx.rect(bx, by, bw, bh);
    ctx.fill();
  }

  ctx.strokeStyle = "#e2e6ee";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, baseline + 0.5);
  ctx.lineTo(cssW, baseline + 0.5);
  ctx.stroke();
}

function drawSpotHistograms() {
  renderMiniHistogram($$("#spot-wait-hist"), spotHistograms.wait);
  renderMiniHistogram($$("#spot-distance-hist"), spotHistograms.distance);
}

// Repaint on resize: the canvas is cleared when its backing store is re-sized to
// match the new CSS width.
window.addEventListener("resize", () => {
  const pane = $$(".sidebar.show-spot");
  if (pane && pane.classList.contains("visible")) drawSpotHistograms();
});

// Single entry point for the spot pane's summary: writes the markup and paints the
// canvases, which the summaryText string alone cannot do.
function renderSpotSummary(data) {
  spotHistograms = {
    wait: spotHistogram(data.rides, "wait"),
    distance: spotHistogram(data.rides, "distance"),
  };
  $$("#spot-summary").innerHTML = summaryText(data, spotHistograms);
  drawSpotHistograms();
}

// `hists` is omitted by the GPX export, which wants the plain summary lines only.
function summaryText(data, hists = { wait: null, distance: null }) {
  const osmLink = data.osm_id ? `<div>🚏 <a href="https://www.openstreetmap.org/node/${data.osm_id}" target="_blank" rel="noopener noreferrer">Official hitchhiking spot</a></div>` : '';
  const carPoolingLink = data.car_pooling
    ? `<div>🚗 <a href="https://www.openstreetmap.org/${data.car_pooling.osm_type}/${data.car_pooling.id}" target="_blank" rel="noopener noreferrer">Car pooling spot</a></div>`
    : '';
  const fuelLink = data.fuel
    ? `<div>⛽ <a href="https://www.openstreetmap.org/${data.fuel.osm_type}/${data.fuel.id}" target="_blank" rel="noopener noreferrer">Gas station</a></div>`
    : '';
  const hitchwikiLink = data.hitchwiki_article
    ? `<div>📄 <a href="${data.hitchwiki_article}" target="_blank" rel="noopener noreferrer">Mentioned on Hitchwiki</a></div>`
    : '';
  const hitchwikiMapLink = data.hitchwiki_map
    ? `<div>🗺️ <a href="${data.hitchwiki_map}" target="_blank" rel="noopener noreferrer">On Hitchwiki</a></div>`
    : '';

  const wait = !data.wait || Number.isNaN(data.wait) ? "-" : data.wait.toFixed(0) + " min";
  const distance = !data.distance || Number.isNaN(data.distance) ? "-" : data.distance.toFixed(0) + " km";

  // Lines are <div>s rather than <br>-separated text: each histogram is a block
  // element, and a <br> after one would open an empty line under the chart.
  return `<div>Rating: ${data.rating && data.rating.toFixed(0)}/5</div>
    <div>Waiting time: ${wait}</div>
    ${spotHistogramMarkup(hists.wait, "spot-wait-hist", "min")}
    <div>Ride distance: ${distance}</div>
    ${spotHistogramMarkup(hists.distance, "spot-distance-hist", "km")}
    ${osmLink}${carPoolingLink}${fuelLink}${hitchwikiLink}${hitchwikiMapLink}`;
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

  // Re-render the summary now that the fetched spot details and rides are merged in
  // (the first render in markerClick only had the slim spots.json fields, so it could
  // show the averages but not the distributions).
  renderSpotSummary(marker.options._data);

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
  // Street View helps judge a spot before going there (shoulder, sight lines, place to pull over).
  // map_action=pano snaps to the nearest panorama, so it still works when the spot itself is off-road.
  $$("#spot-streetview-link").href =
    `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${data.lat},${data.lon}`;
  $$("#spot-osm-link").href =
    `https://www.openstreetmap.org/?mlat=${data.lat}&mlon=${data.lon}#map=18/${data.lat}/${data.lon}`;

  renderSpotSummary(data);

  // "Hitch here" — start a tracked ride from THIS spot's canonical coordinates via the
  // in-ride flow (same entry as the long-press "Start Hitching", incl. the soft login
  // prompt). Seeding from the existing anchor keeps repeat rides on one spot rather than
  // spawning near-duplicates. Hidden while a journey is already active (one at a time).
  const hitchBtn = $$("#spot-hitch-here");
  if (hitchBtn) {
    const journeyActive = window.inride && window.inride.journeyStore && window.inride.journeyStore.get();
    hitchBtn.style.display = window.inride && !journeyActive ? "" : "none";
    hitchBtn.onclick = function () {
      if (!window.inride || !window.L) return;
      clear(); // close the spot sheet before the waiting UI takes over
      window.inride.journeyFlow.startFromChoose(L.latLng(data.lat, data.lon));
    };
  }

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
  // The spot id goes in the path, not the #fragment: many messengers strip the
  // fragment when auto-linking a pasted URL, so a `/#lat,lon` link arrived
  // without coordinates. The #map= viewport is appended for recipients whose
  // client keeps it, and is safely ignorable when it's stripped.
  const spotPath = `/spot/${data.lat.toFixed(5)}_${data.lon.toFixed(5)}`;
  const spotUrl = `${location.origin}${spotPath}#map=17/${data.lat.toFixed(5)}/${data.lon.toFixed(5)}`;
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
// peek shows only the handle + "Routes" title (see the routing-specific CSS
// override), so most of the map stays visible; full/half reveal the options.
const ROUTING_SHEET_SNAPS = { peek: 88, half: 55, full: 0 };
const COUNTRY_SHEET_SNAPS = { half: 55, full: 0 };
const EVENT_SHEET_SNAPS = { half: 55, full: 0 };

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

function setupBottomSheet({ sheet, handle, snaps, defaultSnap, onClose, dismissable = true }) {
  if (!sheet || !handle) return;

  const orderedSnapNames = Object.keys(snaps).sort((a, b) => snaps[a] - snaps[b]); // top → bottom
  const FLING_THRESHOLD = 0.5; // px/ms
  // Non-dismissable sheets (e.g. routing results) can't be swiped away — a
  // down-drag bottoms out at the lowest snap instead of closing; only the X
  // (its own onclick) closes them.
  const bottomSnap = orderedSnapNames[orderedSnapNames.length - 1];
  const dismiss = () => (dismissable ? close() : setSheetSnap(sheet, bottomSnap, snaps));

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
        if (currentIdx === lastIdx || currentPct > 75) return dismiss();
        setSheetSnap(sheet, orderedSnapNames[Math.min(lastIdx, currentIdx + 1)], snaps);
      } else {
        setSheetSnap(sheet, orderedSnapNames[Math.max(0, currentIdx - 1)], snaps);
      }
      return;
    }

    // Slow release: close if dragged near the bottom, otherwise snap to nearest.
    if (currentPct > 90) return dismiss();
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
  // Close via navigateHome so the #menu hash is cleared (keeps URL and pane in sync).
  const closeBtn = $$("#menu-close");
  if (closeBtn) closeBtn.onclick = navigateHome;
  setupBottomSheet({
    sheet: $$(".sidebar.menu"),
    handle: $$("#menu-sheet-handle"),
    snaps: MENU_SHEET_SNAPS,
    defaultSnap: "half",
    onClose: navigateHome,
  });
}

// The route pane's X must fully exit the planner (drop the routes, the pins and the
// search panel). It cannot be navigateHome: while routing is active navigateHome
// *returns to* the route view (that is what closing a spot pane opened from a route
// should do), so wiring the X to it would reopen the pane it just closed.
function closeRoutingPane() {
  if (window.RoutingUI && window.RoutingUI.active) window.RoutingUI.close();
  else navigateHome();
}

function setupRoutingSheet() {
  const closeBtn = $$("#routing-close");
  if (closeBtn) closeBtn.onclick = closeRoutingPane;
  setupBottomSheet({
    sheet: $$(".sidebar.routing"),
    handle: $$("#routing-sheet-handle"),
    snaps: ROUTING_SHEET_SNAPS,
    defaultSnap: "half",
    onClose: closeRoutingPane,
    // Only the X closes the route pane; dragging down bottoms out at "peek".
    dismissable: false,
  });
}

function setupCountrySheet() {
  const closeBtn = $$("#country-close");
  if (closeBtn) closeBtn.onclick = navigateHome;
  setupBottomSheet({
    sheet: $$(".sidebar.country"),
    handle: $$("#country-sheet-handle"),
    snaps: COUNTRY_SHEET_SNAPS,
    defaultSnap: "half",
    onClose: navigateHome,
  });
  // Re-fit the histograms when the viewport width changes while the sheet is open.
  window.addEventListener("resize", () => {
    if ($$(".sidebar.country").classList.contains("visible")) redrawCountryInsightsCharts();
  });
}

function setupEventSheet() {
  const closeBtn = $$("#event-close");
  if (closeBtn) closeBtn.onclick = navigateHome;
  setupBottomSheet({
    sheet: $$(".sidebar.event"),
    handle: $$("#event-sheet-handle"),
    snaps: EVENT_SHEET_SNAPS,
    defaultSnap: "full",
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
      // Dismissing the overlay returns to the map the user submitted from — no
      // navigation, so the restored viewport stays exactly where they left it.
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
  // A spot opened from a route (clicking a route marker) shows the spot pane over
  // the route. Closing that pane should return to the route view — keep the drawn
  // route and reopen the options pane — instead of exiting the planner entirely.
  // (The route pane's own X calls RoutingUI.close() directly, so this only fires
  // for the spot pane while routing is active.)
  if (window.RoutingUI && window.RoutingUI.active) {
    // Deselect the spot first: its destination arrows are drawn from `active`
    // and would otherwise linger over the route after the pane closes.
    active = [];
    renderPoints();
    window.RoutingUI.showAgain();
    return;
  }
  // Panes opened via a navigation hash (#country/<name>, #event, #menu, …) leave that
  // hash in the URL; clearSpotUrl only resets /spot/ paths, so navigate() below would
  // otherwise re-read the hash and reopen the pane — the close X would appear to
  // "reload" the wiki sheet rather than close it. Drop it, keeping a #map= viewport.
  if (window.location.hash && !parseMapHash(window.location.hash)) {
    const url = new URL(window.location.href);
    url.hash = "";
    window.history.pushState({}, "", url);
  }
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
const fuelToggle = document.getElementById("fuel-toggle");
const fuelIconToggle = document.getElementById("fuel-icon-toggle");
const hitchwikiToggle = document.getElementById("hitchwiki-toggle");

// The gas-station filter is a click-to-toggle icon, not a checkbox. Clicking it
// flips the hidden #fuel-toggle checkbox (firing its "input" listener, which updates
// the URL param and re-filters), keeping all the shared filter logic uniform.
function syncFuelIcon() {
  const on = fuelToggle.checked;
  fuelIconToggle.classList.toggle("active", on);
  fuelIconToggle.setAttribute("aria-pressed", on ? "true" : "false");
}
const textFilter = document.getElementById("text-filter");
const userFilter = document.getElementById("user-filter");
const distanceFilter = document.getElementById("distance-filter");
const minRidesFilter = document.getElementById("min-rides-filter");
const minRatingFilter = document.getElementById("min-rating-filter");
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

// ---------------------------------------------------------------------------
// URL scheme (mirrors OpenStreetMap's /node/<id>#map=<zoom>/<lat>/<lon>)
//
//   /spot/<lat>_<lon>   which spot is selected — identity, in the path
//   #map=<zoom>/<lat>/<lon>   where the camera is — viewport, in the fragment
//
// Identity lives in the path because messengers strip the #fragment when
// auto-linking a pasted URL; the viewport is the part that's harmless to lose.
// Legacy ?lat=&lon= query params and #lat,lon hashes are still accepted as
// input so old shared links keep resolving to the same spot.
// ---------------------------------------------------------------------------

const MAP_HASH_RE = /^#?map=(\d+(?:\.\d+)?)\/(-?\d+(?:\.\d+)?)\/(-?\d+(?:\.\d+)?)$/;
const SPOT_PATH_RE = /^\/spot\/(-?\d+\.\d+)_(-?\d+\.\d+)\/?$/;
// Shared route permalink, written by routing.js (updateShareUrl) and served by
// Flask's render_directions so the link can carry its own OpenGraph preview.
const DIR_PATH_RE = /^\/dir\/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)\/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)\/?$/;

// The path the map was served under (/, /light, /hitchhiking.html …). Closing a
// spot must return here, not unconditionally to "/", or the map variations and
// their template tweaks would be lost on the way back. A /spot/ or /dir/ path is
// selection state, not a variation — both close back to "/".
const BASE_PATH =
  SPOT_PATH_RE.test(window.location.pathname) || DIR_PATH_RE.test(window.location.pathname)
    ? "/"
    : window.location.pathname;

// Decimals such that one digit of the coordinate is worth about one screen
// pixel at this zoom — OSM's zoomPrecision. Keeps shared links short at world
// zoom without throwing away precision when zoomed into a spot.
function zoomPrecision(zoom) {
  return Math.max(0, Math.ceil(Math.log(zoom) / Math.LN2));
}

function formatMapHash(center, zoom) {
  const p = zoomPrecision(zoom);
  return `#map=${zoom}/${center.lat.toFixed(p)}/${center.lng.toFixed(p)}`;
}

function parseMapHash(hash) {
  const m = MAP_HASH_RE.exec(hash || "");
  return m ? { zoom: +m[1], lat: +m[2], lon: +m[3] } : null;
}

// The spot the current URL names, from the canonical path or a legacy link.
function spotFromUrl() {
  const m = SPOT_PATH_RE.exec(window.location.pathname);
  if (m) return { lat: +m[1], lon: +m[2] };
  const lat = getQueryParameter("lat"),
    lon = getQueryParameter("lon");
  if (lat != null && lon != null && !isNaN(lat) && !isNaN(lon))
    return { lat: +lat, lon: +lon };
  return null;
}

// Keep the address bar pointing at wherever the map currently is, so the URL is
// always ready to copy. replaceState, not pushState: a pan is not a navigation,
// and pushing would bury the back button under every mouse drag.
function updateMapHash() {
  if (!map._loaded) return;
  const url = new URL(window.location.href);
  // Only own the hash while it describes a viewport (or is empty). #menu,
  // #routing, #country/… are navigation state that a pan must not clobber.
  if (url.hash && !parseMapHash(url.hash)) return;
  const next = formatMapHash(map.getCenter(), map.getZoom());
  if (url.hash === next) return;
  url.hash = next;
  window.history.replaceState(window.history.state, "", url);
}

// Move the map to the viewport named by #map=. No-op when the hash already
// describes where the map is — navigate() re-runs on every filter change, and
// re-issuing setView there would fight the user's pan. Returns whether the hash
// was a viewport hash at all (vs. #menu, #routing, …).
function applyMapHash() {
  const v = parseMapHash(window.location.hash);
  if (!v) return false;
  const c = map.getCenter(),
    p = zoomPrecision(v.zoom);
  const settled =
    map.getZoom() === v.zoom &&
    +c.lat.toFixed(p) === v.lat &&
    +c.lng.toFixed(p) === v.lon;
  if (!settled) map.setView([v.lat, v.lon], v.zoom);
  return true;
}

// Reflect the selected spot in the address bar as /spot/<lat>_<lon>. The id
// matches generate_spot_id() in show.py (5 decimals) and so also the
// rides/by-spot/<id>.json filename. Idempotent — navigate() re-runs on every
// filter change while a spot is open, so we must not push a duplicate history
// entry when the URL already points at this spot. Filters and the viewport hash
// are preserved; legacy ?lat=&lon= is dropped so only the canonical form spreads.
// Does the URL already name this spot, in any form it may arrive in — canonical
// path, legacy ?lat=&lon=, legacy #lat,lon? Rewriting such a URL to the
// canonical path is a canonicalisation, not a navigation, so it must replace
// rather than push: otherwise the back button lands on the pre-rewrite URL,
// which resolves to this same spot and reopens it.
function urlNamesSpot(lat, lon) {
  const id = `${lat.toFixed(5)}_${lon.toFixed(5)}`;
  const sameAs = (p) => `${p.lat.toFixed(5)}_${p.lon.toFixed(5)}` === id;
  const fromPathOrQuery = spotFromUrl();
  if (fromPathOrQuery) return sameAs(fromPathOrQuery);
  const h = window.location.hash.slice(1).split("/")[0].split(",");
  if (h.length < 2 || isNaN(h[0]) || isNaN(h[1])) return false;
  return sameAs({ lat: +h[0], lon: +h[1] });
}

function setSpotUrl(lat, lon) {
  const url = new URL(window.location.href);
  const path = `/spot/${lat.toFixed(5)}_${lon.toFixed(5)}`;
  const samePath = url.pathname === path;
  const canonicalising = urlNamesSpot(lat, lon);
  const legacyParams = url.searchParams.has("lat") || url.searchParams.has("lon");
  // Keep a #map= viewport, drop any other hash (#lat,lon, #dir/…): it described
  // the navigation that opened this spot and must not outlive it — a stale hash
  // would also stop updateMapHash() from ever tracking the map again.
  const staleHash = !!url.hash && !parseMapHash(url.hash);
  if (samePath && !legacyParams && !staleHash) return;
  url.pathname = path;
  url.searchParams.delete("lat");
  url.searchParams.delete("lon");
  if (staleHash) url.hash = "";
  window.history[canonicalising ? "replaceState" : "pushState"]({}, "", url);
}

// Drop the selected-spot URL state without navigating. Filters, the viewport
// hash, and the map variation we were served under are all kept.
function clearSpotUrl() {
  const url = new URL(window.location.href);
  if (!SPOT_PATH_RE.test(url.pathname) && !url.searchParams.has("lat") && !url.searchParams.has("lon")) {
    return;
  }
  url.pathname = BASE_PATH;
  url.searchParams.delete("lat");
  url.searchParams.delete("lon");
  if (url.hash && !parseMapHash(url.hash)) url.hash = "";
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
  fuelToggle.checked = getQueryParameter("fuelonly") == "true";
  syncFuelIcon();
  hitchwikiToggle.checked = getQueryParameter("hitchwikionly") == "true";
  textFilter.value = getQueryParameter("text");
  userFilter.value = getQueryParameter("user");
  distanceFilter.value = getQueryParameter("mindistance");
  minRidesFilter.value = getQueryParameter("minrides");
  minRatingFilter.value = getQueryParameter("minrating");
  vehicleFilter.value = getQueryParameter("vehicle") || "";
  methodFilter.value = getQueryParameter("method") || "";
  minDateFilter.value = getQueryParameter("mindate") || "";
  maxDateFilter.value = getQueryParameter("maxdate") || "";

  if (
    recentToggle.checked ||
    osmToggle.checked ||
    carPoolingToggle.checked ||
    fuelToggle.checked ||
    hitchwikiToggle.checked ||
    textFilter.value ||
    userFilter.value ||
    distanceFilter.value ||
    minRidesFilter.value ||
    minRatingFilter.value ||
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
    if (minRatingFilter.value) {
      // spots.json carries the spot's mean rating, so this needs no ride index.
      const minRating = parseFloat(minRatingFilter.value);
      filterMarkers = filterMarkers.filter(
        (x) => x.options._data.rating != null && x.options._data.rating >= minRating
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
    if (fuelToggle.checked) {
      filterMarkers = filterMarkers.filter((x) => !!x.options._data.fuel);
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

  // #map=z/lat/lon is viewport state, not navigation state: apply it, then let
  // the rest of navigate() pick the pane from the path/query as if there were
  // no hash at all.
  const isMapHash = applyMapHash();

  let args = isMapHash ? [""] : window.location.hash.slice(1).split("/");
  let mainArgs = args[0].split(",");

  // The selected spot is named by the path (/spot/<lat>_<lon>), or by legacy
  // ?lat=&lon= params on older shared links. Either way it wins over the hash,
  // which now only describes where the camera is.
  const spot = !mainArgs[0] || isMapHash ? spotFromUrl() : null;
  if (spot) {
    mainArgs = [spot.lat, spot.lon];
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
  } else if (mainArgs[0] == "menu") {
    clear();
    bar(".sidebar.menu");
    // clear() drops the "menu" body class; re-add it so menu-specific chrome shows.
    document.body.classList.add("menu");
    updateBottomPaneVar();
    setSheetSnap($$(".sidebar.menu"), "full", MENU_SHEET_SNAPS);
  } else if (mainArgs[0] == "country" && args[1]) {
    // #country/<name> opens the Hitchwiki country info sheet.
    openCountrySheet(decodeURIComponent(args[1]));
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
  } else if (mainArgs[0] == "dir" || DIR_PATH_RE.test(window.location.pathname)) {
    // Shareable route link (/dir/from/to, or the legacy #dir/from/to) — routing.js
    // (openFromUrl) opens the planner and computes; don't clear() it out from under it.
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
  const minRating = minRatingFilter.value ? parseFloat(minRatingFilter.value) : null;
  const recentCutoffMs = recentToggle.checked
    ? Date.now() - 24 * 60 * 60 * 1000
    : null;
  const osmOnly = osmToggle.checked;
  const wikiOnly = hitchwikiToggle.checked;
  const cpOnly = carPoolingToggle.checked;
  const fuelOnly = fuelToggle.checked;

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
    if (fuelOnly && !ride.fuel) return false;
    return true;
  });

  if (minRides != null) {
    const ridesPerSpot = new Map();
    for (const r of filtered) {
      ridesPerSpot.set(r.sid, (ridesPerSpot.get(r.sid) || 0) + 1);
    }
    filtered = filtered.filter((r) => (ridesPerSpot.get(r.sid) || 0) >= minRides);
  }

  if (minRating != null) {
    // Like the min-rides filter above, the spot average is taken over the rides that
    // survived the ride-level filters, so the two spot filters describe the same set.
    // Rides without a rating don't contribute to the mean.
    const ratingSums = new Map();
    for (const r of filtered) {
      if (r.r == null) continue;
      const acc = ratingSums.get(r.sid) || { sum: 0, n: 0 };
      acc.sum += r.r;
      acc.n += 1;
      ratingSums.set(r.sid, acc);
    }
    filtered = filtered.filter((r) => {
      const acc = ratingSums.get(r.sid);
      return acc && acc.sum / acc.n >= minRating;
    });
  }

  return filtered;
}

function anyFilterActive() {
  return Boolean(
    userFilter.value ||
      textFilter.value ||
      distanceFilter.value ||
      minRidesFilter.value ||
      minRatingFilter.value ||
      vehicleFilter.value ||
      methodFilter.value ||
      minDateFilter.value ||
      maxDateFilter.value ||
      recentToggle.checked ||
      osmToggle.checked ||
      carPoolingToggle.checked ||
      fuelToggle.checked ||
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

// Bin raw values into { lo, hi, binWidth, counts }. Kept separate from the
// renderer so histograms can also be precomputed server-side (the country sheet
// ships these bins directly — see country_ratings.py compute_histogram).
function computeHistogram(values) {
  if (!values || values.length === 0) return null;
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
  return { lo, hi, binWidth, counts };
}

function drawHistogram(canvas, values, opts) {
  renderHistogram(canvas, computeHistogram(values), opts);
}

// Render a { lo, hi, binWidth, counts } histogram (from computeHistogram or a
// precomputed server-side equivalent) onto a canvas.
function renderHistogram(canvas, hist, opts) {
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || 400;
  const cssH = canvas.clientHeight || 220;
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  if (!hist || !hist.counts || hist.counts.length === 0) return;

  const { lo, hi, binWidth, counts } = hist;
  const bins = counts.length;
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
  // The pane is about to be reparented inline; leaving the modal flag set would strand
  // the scrim over the insights view.
  closeFiltersModal();
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
      // Menu open/close state lives in the #menu hash (see navigate()).
      if (document.body.classList.contains("menu")) {
        navigateHome();
      } else {
        location.hash = "menu";
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
// True when selection was started from a map gesture (add a new hitch site) rather
// than from the ride form's "pick location" flow — controls cancel behavior and copy.
let locationSelectionIsNewSpot = false;
// Stored so cleanup removes only this handler (map.off('click') with no function
// would strip handleMapClick too, breaking the map when we stay on it after cancel).
let locationSelectionClickHandler = null;

// If a tap/press lands within snapping range of a visible spot marker, treat
// it as choosing THAT spot (merge the endpoint onto the spot's exact coords)
// rather than creating a near-duplicate anchor next to it — the user is plausibly
// aiming for that spot as their drop-off. Falls back to the raw latlng when the
// press is nowhere near a spot, or when no screen point is available (e.g. GPS).
function snapSelectionLatLng(latlng, containerPoint) {
    const snapped = containerPoint ? findNearbySpotMarker(containerPoint) : null;
    return snapped ? snapped.getLatLng() : latlng;
}

// Create the draggable selection pin on first placement, or move it if it
// already exists. Shared by every way of placing the endpoint — single tap
// (Leaflet click), long-press gesture, and the GPS button — so all three
// behave identically and never stack a second marker.
function placeOrMoveSelectionMarker(latlng) {
    if (locationSelectionMarker) {
        locationSelectionMarker.setLatLng(latlng);
        return;
    }
    locationSelectionMarker = L.marker(latlng, {
        draggable: true,
        icon: L.icon({
            iconUrl: '/static/markers/marker-icon-2x-red.png',
            shadowUrl: '/static/markers/marker-shadow.png',
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            popupAnchor: [1, -34],
            shadowSize: [41, 41]
        })
    }).addTo(map);
    // A pin now exists (tap / long-press / GPS) — enable the confirm button, which
    // starts disabled on the pinless destination leg.
    const confirmBtn = document.querySelector('.location-selection-ui .lsel-confirm');
    if (confirmBtn) confirmBtn.disabled = false;
}

function setupLocationSelection(selectionType, initialCoords, opts = {}) {
    locationSelectionType = selectionType;
    locationSelectionIsNewSpot = !!opts.isNewSpot;

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

    // The destination leg starts with NO pin: the map centers on the pickup for
    // context, but auto-dropping a marker there would silently set the endpoint
    // to the origin. The user must place it themselves (single/long tap) or via
    // the GPS button. Pickup picks and gesture-initiated adds keep a pre-placed
    // pin (at the seed location, or the current map center).
    if (selectionType !== 'select-destination') {
        placeOrMoveSelectionMarker(opts.initialLatLng || map.getCenter());
    }

    // A single tap (Leaflet click) places or moves the pin. Long-press is routed
    // to the same helper via the add-spot gesture path (see startAddSpotFromGesture)
    // so both a quick tap and a long press set/move the endpoint. Kept in a named
    // handler so cleanup can detach only this one — see locationSelectionClickHandler.
    locationSelectionClickHandler = function(e) {
        placeOrMoveSelectionMarker(snapSelectionLatLng(e.latlng, e.containerPoint));
    };
    map.on('click', locationSelectionClickHandler);

    // Panel copy: gesture-initiated adds get add-a-site wording (and a distinct
    // variant when snapped onto an existing spot); the form-initiated pick keeps
    // the original "Select Pickup/Destination Location" copy.
    let heading, instruction, confirmLabel;
    if (opts.isNewSpot && opts.existingSpot) {
        heading = 'Add a ride to this spot';
        instruction = 'This matches an existing hitch spot. Confirm to add your ride here.';
        confirmLabel = 'Add ride';
    } else if (opts.isNewSpot) {
        heading = 'Add a hitch spot here?';
        instruction = 'Drag the pin to fine-tune, then confirm.';
        confirmLabel = 'Add spot';
    } else {
        const what = selectionType === 'select-pickup' ? 'Pickup' : 'Destination';
        heading = `Select ${what} Location`;
        instruction = `Click on the map or drag the marker to choose your ${what.toLowerCase()} location`;
        confirmLabel = 'Confirm Location';
    }

    // Add custom UI for location selection — a compact card pinned to the bottom
    // (styled in style.css under .location-selection-ui) so it never covers the
    // top search bar. The body class hides the bottom action pane while selecting.
    const selectionUI = L.DomUtil.create('div', 'location-selection-ui');
    selectionUI.innerHTML = `
        <h4>${heading}</h4>
        <p>${instruction}</p>
        <div class="lsel-actions">
            <button class="lsel-confirm"${locationSelectionMarker ? "" : " disabled"} onclick="confirmLocationSelection()">${confirmLabel}</button>
            <button class="lsel-cancel" onclick="cancelLocationSelection()">Cancel</button>
        </div>
    `;
    document.body.appendChild(selectionUI);
    document.body.classList.add('selecting-location');
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
    const wasNewSpot = locationSelectionIsNewSpot;

    // Clean up without changing coordinates
    cleanupLocationSelection();

    // Gesture-initiated add: the user never left the map, so just stay here.
    if (wasNewSpot) {
        history.replaceState(null, null, " ");
        return;
    }

    // Form-initiated pick: return to ride form, preserving edit mode if editing.
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
    document.body.classList.remove('selecting-location');

    // Remove only our reposition handler — a bare map.off('click') would also
    // detach handleMapClick, which matters when we stay on the map after cancel.
    if (locationSelectionClickHandler) {
        map.off('click', locationSelectionClickHandler);
        locationSelectionClickHandler = null;
    }

    locationSelectionType = null;
    locationSelectionIsNewSpot = false;
}

// Wire up the "drop a pin to add a hitch site" gesture: touch long-press on
// mobile, right-click on desktop. Called once from setupEventListeners.
function setupAddSpotGesture() {
    // Desktop: right-click drops a pin (and suppress the browser context menu).
    map.on('contextmenu', function(e) {
        const oe = e.originalEvent;
        // Ignore right-clicks landing on a Leaflet control (search box, the
        // leaflet-bar buttons): the user is operating the control, not the map.
        // Those controls only stopPropagation on click, not on contextmenu.
        if (oe && oe.target.closest && oe.target.closest('.leaflet-control')) return;
        if (oe) oe.preventDefault();
        // The in-ride tracker owns the "what do you want to do here?" decision now.
        // If it handles the gesture (shows its choose-action dialog), stop here.
        if (window.inrideOnEntryGesture && window.inrideOnEntryGesture(e.latlng, e.containerPoint)) return;
        startAddSpotFromGesture(e.latlng, e.containerPoint);
    });

    // Touch: long-press drops a pin. Cancel on move (panning), lift, or a second
    // finger (pinch-zoom) so only a deliberate stationary press triggers it.
    const LONG_PRESS_MS = 500;
    const MOVE_CANCEL_PX = 10;
    const container = map.getContainer();
    let timer = null, startX = 0, startY = 0;

    const clearTimer = () => { if (timer) { clearTimeout(timer); timer = null; } };

    container.addEventListener('touchstart', function(e) {
        // Don't start a long-press over a Leaflet control (search box, the
        // leaflet-bar buttons): the press is meant to operate the control, not
        // drop a pin on top of it. Those controls only stopPropagation on click,
        // so their native touchstart still bubbles up to this container listener.
        if (e.target.closest && e.target.closest('.leaflet-control')) { clearTimer(); return; }
        // Any non-single-touch (e.g. pinch) cancels a pending press.
        if (e.touches.length !== 1) { clearTimer(); return; }
        const t = e.touches[0];
        startX = t.clientX;
        startY = t.clientY;
        clearTimer();
        timer = setTimeout(function() {
            timer = null;
            const rect = container.getBoundingClientRect();
            const cp = L.point(startX - rect.left, startY - rect.top);
            const latlng = map.containerPointToLatLng(cp);
            // The in-ride tracker owns the "what do you want to do here?" decision now.
            // If it handles the gesture (shows its choose-action dialog), stop here.
            if (window.inrideOnEntryGesture && window.inrideOnEntryGesture(latlng, cp)) return;
            startAddSpotFromGesture(latlng, cp);
        }, LONG_PRESS_MS);
    }, { passive: true });

    container.addEventListener('touchmove', function(e) {
        if (!timer) return;
        const t = e.touches[0];
        if (Math.abs(t.clientX - startX) > MOVE_CANCEL_PX ||
            Math.abs(t.clientY - startY) > MOVE_CANCEL_PX) {
            clearTimer();
        }
    }, { passive: true });

    container.addEventListener('touchend', clearTimer, { passive: true });
    container.addEventListener('touchcancel', clearTimer, { passive: true });
}

// Return the nearest visible spot marker to a screen point within thresholdPx,
// or null. Markers hidden inside a cluster are skipped so we only ever snap to a
// pin the user can actually see.
function findNearbySpotMarker(containerPoint, thresholdPx = 22) {
    // Only snap to spots that are actually shown. Countries mode removes the cluster
    // from the map (but leaves markerCluster non-null), so guard on layer visibility —
    // otherwise a tap could snap to an invisible spot.
    if (!markerCluster || !map.hasLayer(markerCluster)) return null;
    let best = null, bestDist = thresholdPx;
    for (const marker of allMarkers) {
        if (markerCluster && markerCluster.getVisibleParent(marker) !== marker) continue;
        const d = map.latLngToContainerPoint(marker.getLatLng()).distanceTo(containerPoint);
        if (d <= bestDist) {
            bestDist = d;
            best = marker;
        }
    }
    return best;
}

// Begin adding a hitch site from a map gesture: seed a draggable pin (snapping
// onto an existing spot when the press lands on one) and show the confirm panel.
function startAddSpotFromGesture(latlng, containerPoint) {
    // A location selection is already active (e.g. picking a destination): a
    // long-press means "place/move the endpoint here", not "start a new add".
    // This is what makes a long tap set the pin — the destination leg has no
    // marker yet, so we can't rely on the `if (marker) return` guard below.
    if (locationSelectionType) {
        placeOrMoveSelectionMarker(snapSelectionLatLng(latlng, containerPoint));
        return;
    }

    // Ignore if a selection is already in progress.
    if (locationSelectionMarker) return;

    // Fresh ride — drop any leftover form state (edit mode, stale fields).
    sessionStorage.removeItem('rideFormData');

    // Snap onto a nearby existing spot so the new ride merges into it rather than
    // creating a near-duplicate anchor (spot id derives from lat/lon at 5 decimals).
    const snapped = containerPoint ? findNearbySpotMarker(containerPoint) : null;
    const seedLatLng = snapped ? snapped.getLatLng() : latlng;

    setupLocationSelection('select-pickup', null, {
        initialLatLng: seedLatLng,
        isNewSpot: true,
        existingSpot: !!snapped,
    });
}

// Expose the pieces the in-ride tracker composes with (it loads after map.js).
window.map = map; // intentional: exposes the Leaflet instance for inride.js (marker placement, layer removal)
window.getLocationMarker = () => locationMarker;
window.setMapMode = setMapMode;
window.toggleHeatmap = toggleHeatmap;
window.startAddSpotFromGesture = startAddSpotFromGesture;
window.startProposeSpotFromGesture = startProposeSpotFromGesture;
window.setupLocationSelection = setupLocationSelection;
window.findNearbySpotMarker = findNearbySpotMarker;
// Used by the in-ride cover-flow to trigger locate and read the current mode.
window.requestLocationRaw = requestLocation;
window.getMapMode = () => mapMode;
