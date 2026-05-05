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
  ridesIndex = null,
  routeLayer = null,
  routeMarkers = [];

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
          weight: 1 + (m.review_users?.length > 2),
          fillOpacity: opacity,
          color: "black",
          fillColor: color,
          spotId: m.id, // Store spot ID for filtering and ride lookup
          _data: Object.assign({}, m, { rating: rating, text: "" })
        });

        marker.on("click", async (e) => await handleMarkerClick(marker, coords, e));
        if (m.review_users?.length >= 3)
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
  setupRoutingEventListeners();

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
        if (window.location.hash) window.history.pushState(null, null, " ");
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
  minDateFilter.addEventListener("change", () =>
    setQueryParameter("mindate", minDateFilter.value)
  );
  maxDateFilter.addEventListener("change", () =>
    setQueryParameter("maxdate", maxDateFilter.value)
  );
}

// Routing functionality
async function planRoute(startLat, startLon, endLat, endLon, startName, endName) {
  try {
    // Clear any existing route first
    clearRoute();
    
    // Add start and end markers
    const startMarker = L.marker([startLat, startLon], {
      icon: L.icon({
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-green.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41]
      })
    }).addTo(map).bindPopup("Start");
    
    const endMarker = L.marker([endLat, endLon], {
      icon: L.icon({
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41]
      })
    }).addTo(map).bindPopup("End");
    
    routeMarkers.push(startMarker, endMarker);
    
    // Fit the map to show both points
    const bounds = L.latLngBounds([[startLat, startLon], [endLat, endLon]]);
    map.fitBounds(bounds, { padding: [20, 20] });
    
    // Call the backend routing endpoint
    const response = await fetch('/route', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        start: [startLat, startLon],
        end: [endLat, endLon],
        start_name: startName || '',
        end_name: endName || ''
      })
    });
    
    if (response.ok) {
      const routeData = await response.json();
      await displayRoute(routeData);
    } else {
      const errorData = await response.json().catch(() => ({ error: response.statusText }));
      console.error('Routing failed:', errorData);
      alert(`Routing failed: ${errorData.error || response.statusText}
      
This might happen if:
- No ride data exists near your start/end points
- The coordinates are in an area without hitchhiking activity
- Try coordinates closer to major cities or highways`);
    }
  } catch (error) {
    console.error('Routing error:', error);
    alert(`Routing failed: ${error.message}
    
Please check your connection and try again.`);
  }
}

async function displayRoute(routeData) {
  if (routeData && routeData.route && routeData.route.length > 0) {
    // Create polyline for the route
    const routeCoords = routeData.route.map(coord => [coord[0], coord[1]]); // coords are [lat, lon]
    routeLayer = L.polyline(routeCoords, {
      color: 'blue',
      weight: 4,
      opacity: 0.7
    }).addTo(map);
    
    // Load rides index to filter route spots — only lat/lon are needed here.
    const rides = await loadRidesIndex();
    const tolerance = 0.001; // ~100m tolerance for coordinate matching
    
    // Add markers for intermediate stops and highlight those with actual rides
    routeData.route.slice(1, -1).forEach((coord, index) => {
      const lat = coord[0];
      const lon = coord[1];
      
      // Find rides that match this coordinate (within tolerance)
      const matchingRides = rides.filter(ride => 
        Math.abs(ride.lat - lat) <= tolerance && 
        Math.abs(ride.lon - lon) <= tolerance
      );
      
      const hasRides = matchingRides.length > 0;
      
      // Choose marker color based on whether there are actual rides
      const iconUrl = hasRides 
        ? 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-gold.png'
        : 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-blue.png';
      
      const popupContent = hasRides 
        ? `Stop ${index + 1} (${matchingRides.length} ride${matchingRides.length > 1 ? 's' : ''})`
        : `Stop ${index + 1} (no rides)`;
      
      const marker = L.marker([lat, lon], {
        icon: L.icon({
          iconUrl: iconUrl,
          shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
          iconSize: [25, 41],
          iconAnchor: [12, 41],
          popupAnchor: [1, -34],
          shadowSize: [41, 41]
        })
      }).addTo(map).bindPopup(popupContent);
      
      routeMarkers.push(marker);
    });
    
    // Show route info with ride statistics
    const totalStops = routeData.route.length - 2; // Exclude start and end points
    const ridesPromises = routeData.route.slice(1, -1).map(async (coord) => {
      const lat = coord[1];
      const lon = coord[0];
      const matchingRides = rides.filter(ride => 
        Math.abs(ride.lat - lat) <= tolerance && 
        Math.abs(ride.lon - lon) <= tolerance
      );
      return matchingRides.length > 0;
    });
    
    Promise.all(ridesPromises).then(rideResults => {
      const stopsWithRides = rideResults.filter(hasRides => hasRides).length;
      const timeInfo = routeData.total_time_formatted || `${Math.round(routeData.total_time_hours || 0)}h`;
      alert(`Route found! Total time: ${timeInfo}
${totalStops} intermediate stops
${stopsWithRides} stops with actual ride data
Gold markers = spots with rides, Blue markers = stops without rides

Time includes: riding (100 km/h avg) + walking (5 km/h) + waiting at spots`);
    });
  }
}

function clearRoute() {
  // Remove route layer
  if (routeLayer) {
    map.removeLayer(routeLayer);
    routeLayer = null;
  }
  
  // Remove all route markers
  routeMarkers.forEach(marker => {
    map.removeLayer(marker);
  });
  routeMarkers = [];
}

// Global variables to store selected coordinates
let startCoords = null;
let endCoords = null;
let routingGeocodersInitialized = false;

function setupRoutingGeocoders() {
  // Prevent multiple initializations
  if (routingGeocodersInitialized) return;
  routingGeocodersInitialized = true;
  
  // Create geocoder options similar to setupGeocoder()
  const geocoderOpts = {
    collapsed: false,
    defaultMarkGeocode: false,
    provider: "photon",
    geocoder: L.Control.Geocoder.photon(),
  };
  
  // Setup start location geocoder
  const startGeocoderOpts = {
    ...geocoderOpts,
    placeholder: "e.g. Amsterdam, Netherlands"
  };
  
  const startGeocoderDiv = document.getElementById("start-geocoder");
  if (startGeocoderDiv) {
    const startGeocoder = L.Control.geocoder(startGeocoderOpts);
    const container = startGeocoder.onAdd(map);
    startGeocoderDiv.appendChild(container);
    
    startGeocoder.on("markgeocode", function(e) {
      startCoords = e.geocode.center;
      const input = startGeocoderDiv.querySelector('input');
      if (input) {
        input.value = e.geocode.name;
      }
    });
  }
  
  // Setup end location geocoder
  const endGeocoderOpts = {
    ...geocoderOpts,
    placeholder: "e.g. Berlin, Germany"
  };
  
  const endGeocoderDiv = document.getElementById("end-geocoder");
  if (endGeocoderDiv) {
    const endGeocoder = L.Control.geocoder(endGeocoderOpts);
    const container = endGeocoder.onAdd(map);
    endGeocoderDiv.appendChild(container);
    
    endGeocoder.on("markgeocode", function(e) {
      endCoords = e.geocode.center;
      const input = endGeocoderDiv.querySelector('input');
      if (input) {
        input.value = e.geocode.name;
      }
    });
  }
}

function setupRoutingEventListeners() {
  const planRouteBtn = document.getElementById("plan-route-btn");
  const clearRouteBtn = document.getElementById("clear-route-btn");
  
  if (planRouteBtn) {
    planRouteBtn.onclick = () => {
      if (!startCoords || !endCoords) {
        alert('Please select both start location and destination from the suggestions.');
        return;
      }
      
      var startName = document.querySelector('#start-geocoder input')?.value || '';
      var endName = document.querySelector('#end-geocoder input')?.value || '';
      planRoute(startCoords.lat, startCoords.lng, endCoords.lat, endCoords.lng, startName, endName);
    };
  }
  
  if (clearRouteBtn) {
    clearRouteBtn.onclick = () => {
      clearRoute();
      // Reset coordinates
      startCoords = null;
      endCoords = null;
      // Clear input fields
      const startInput = document.querySelector('#start-geocoder input');
      const endInput = document.querySelector('#end-geocoder input');
      if (startInput) startInput.value = '';
      if (endInput) endInput.value = '';
    };
  }
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
  window.location.hash = `${point.lat},${point.lng}`;

  // Show the spot pane immediately with a loading spinner for rides
  markerClick(marker);

  // Load rides for this spot from the per-spot detail file.
  const spotId = marker.options.spotId;
  let spotRides = [];
  try {
    const resp = await fetch(`/rides/by-spot/${encodeURIComponent(spotId)}.json`);
    if (resp.ok) {
      spotRides = await resp.json();
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
  const spotUrl = `${location.origin}/#${data.lat},${data.lon}`;
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
  if (window.location.hash) {
    window.history.pushState(null, null, " ");
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
const hitchwikiToggle = document.getElementById("hitchwiki-toggle");
const textFilter = document.getElementById("text-filter");
const userFilter = document.getElementById("user-filter");
const distanceFilter = document.getElementById("distance-filter");
const minRidesFilter = document.getElementById("min-rides-filter");
const vehicleFilter = document.getElementById("vehicle-filter");
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
      userFilter.value || vehicleFilter.value || minDateFilter.value || maxDateFilter.value;
    if (hasRideAttrFilter) {
      const rides = await loadRidesIndex();
      // MediaWiki-style match: only the first letter is case-insensitive, rest matches as-is
      const normalizeFirstLetter = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
      const username = userFilter.value ? normalizeFirstLetter(userFilter.value) : null;
      const wantedKind = vehicleFilter.value || null;
      const minMs = minDateFilter.value ? Date.parse(minDateFilter.value + "T00:00:00Z") : null;
      // The max bound covers the end of its day so a user-entered max date is inclusive.
      const maxMs = maxDateFilter.value ? Date.parse(maxDateFilter.value + "T23:59:59.999Z") : null;

      const matchingSpotIds = new Set(
        rides
          .filter(ride => {
            if (username && !(ride.u && normalizeFirstLetter(ride.u).includes(username))) return false;
            // Treat rides with unspecified vehicle as cars, since most rides are cars.
            if (wantedKind && ride.v !== wantedKind && !(wantedKind === "car" && ride.v == null)) return false;
            if (minMs != null || maxMs != null) {
              if (ride.rd == null) return false;
              if (minMs != null && ride.rd < minMs) return false;
              if (maxMs != null && ride.rd > maxMs) return false;
            }
            return true;
          })
          .map(ride => ride.sid)
      );
      filterMarkers = filterMarkers.filter(marker =>
        matchingSpotIds.has(marker.options.spotId)
      );
    }
    if (textFilter.value) {
      filterMarkers = filterMarkers.filter((x) =>
        x.options._data.text.toLowerCase().includes(textFilter.value.toLowerCase())
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
        (x) => (x.options._data.ride_count || 0) >= minRides
      );
    }
    if (recentToggle.checked) {
      const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
      filterMarkers = filterMarkers.filter((x) => {
        return x.options._data.latest_submission && x.options._data.latest_submission >= cutoff;
      });
    }
    if (osmToggle.checked) {
      filterMarkers = filterMarkers.filter((x) => {
        return x.options._data.osm_id !== null && x.options._data.osm_id !== undefined;
      });
    }
    if (carPoolingToggle.checked) {
      filterMarkers = filterMarkers.filter((x) => {
        return x.options._data.car_pooling !== null && x.options._data.car_pooling !== undefined;
      });
    }
    if (hitchwikiToggle.checked) {
      filterMarkers = filterMarkers.filter((x) => {
        return x.options._data.hitchwiki_article !== null && x.options._data.hitchwiki_article !== undefined;
      });
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
  
  if (mainArgs[0] == "route") {
    clear();
    planRoute(+mainArgs[1], +mainArgs[2], +mainArgs[3], +mainArgs[4]);
  } else if (mainArgs[0] == "location") {
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
    // Initialize geocoders after sidebar is shown
    setTimeout(() => setupRoutingGeocoders(), 100);
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
    // Try to find an exact marker match first
    for (let m of allMarkers) {
      if (m._latlng.lat === lat && m._latlng.lng === lon) {
        await handleMarkerClick(m, m.getLatLng(), null);
        if (map.getZoom() < 3) map.setView(m.getLatLng(), zoom || 16);
        return;
      }
    }
    // No exact marker match — pan to the coordinates
    map.setView([lat, lon], zoom || 14);
  } else {
    clear();
  }
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
    container.innerText = "📍 Add spot";

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
        if (window.location.hash) {
          window.history.pushState(null, null, " ");
        }
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
