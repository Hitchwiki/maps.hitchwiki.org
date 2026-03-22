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
  ridesData = null,
  routeLayer = null,
  routeMarkers = [];

// Initialize Map
async function initializeMap() {
  return new Promise((resolve, reject) => {
    map = L.map("map", {
      center: [0, 0],
      zoom: 1,
      preferCanvas: true,
    });

    map.whenReady(async () => {
      await loadMarkers(map).catch(reject);
      resolve(map);
    });

    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution:
        '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> | Data: <a href="/copyright">maps.hitchwiki.org</a> &amp; <a href="https://hitchmap.com/copyright.html">Hitchmap</a> (<a href="https://opendatacommons.org/licenses/odbl/">ODbL</a>)',
    }).addTo(map);
  });
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
    });
}

// Load rides data with lazy loading
async function loadRides() {
  if (ridesData) {
    return ridesData;
  }
  
  try {
    const response = await fetch('/rides.json');
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    ridesData = await response.json();
    console.log(`Loaded ${ridesData.length} rides`);
    return ridesData;
  } catch (error) {
    console.error("Error loading rides:", error);
    return [];
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

// Toggle heatmap layer
async function toggleHeatmap() {
  const btn = $$('#heatmap-toggle-btn');
  const text = $$('#heatmap-toggle-text');
  
  var legendPane = document.getElementById('heatmap-legend-pane');

  if (heatmapActive) {
    // Switch back to normal view
    if (heatmapLayer) {
      map.removeLayer(heatmapLayer);
    }
    if (legendPane) legendPane.style.display = 'none';
    positionLegendPane();
    btn.classList.remove('active');
    text.textContent = 'Heatmap';
    heatmapActive = false;
  } else {
    // Switch to heatmap view
    if (!heatmapData) {
      heatmapData = await loadHeatmapData();
      if (!heatmapData) {
        alert('Heatmap data is not available');
        return;
      }
    }

    // Create heatmap layer using pre-rendered PNG
    if (!heatmapLayer) {
      heatmapLayer = L.imageOverlay(
        heatmapData.image_url,
        heatmapData.bounds,
        { opacity: 0.7 }
      );
    }

    // Populate and show the legend pane
    populateHeatmapLegend(heatmapData.legend);
    if (legendPane) legendPane.style.display = 'block';
    positionLegendPane();

    heatmapLayer.addTo(map);
    btn.classList.add('active');
    text.textContent = 'Normal';
    heatmapActive = true;
  }
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
  map = await initializeMap();

  // Set up interactive elements
  setupGeocoder();
  addMapControls();
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

// Add custom controls to the map
function addMapControls() {
  // Controls are now in the bottom action pane (HTML) and top-right (account btn)
  // Only need to set up zoom position
  map.zoomControl.setPosition('bottomright');
}

// Set up various event listeners for the map and UI elements
function setupEventListeners() {
  $$("#sb-close").onclick = navigateHome;
  $$(".report-dup").onclick = () =>
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
  osmToggle.addEventListener("input", () =>
    setQueryParameter("osmonly", osmToggle.checked)
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
    
    // Load rides data to filter route spots
    const rides = await loadRides();
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

function summaryText(data) {
  const osmLink = data.osm_id ? `<br>🚏 <a href="https://www.openstreetmap.org/node/${data.osm_id}" target="_blank" rel="noopener noreferrer">Official hitchhiking spot</a>` : '';
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
    }${osmLink}${hitchwikiLink}${hitchwikiMapLink}`;
}

async function handleMarkerClick(marker, point, e) {
  if ($$(".topbar.visible") || $$(".sidebar.spot-form-container.visible"))
    return;

  reportDuplicate(marker);
  window.location.hash = `${point.lat},${point.lng}`;

  // Load rides for this spot
  const spotId = marker.options.spotId;
  const rides = await loadRides();
  const spotRides = rides.filter(ride => ride.spot_id === spotId);
  
  // Generate rides text (same format as before)
  const ridesText = spotRides.length > 0 
    ? spotRides.map(ride => ride.text).join('<hr>')
    : '';
  
  // Update marker data with rides text
  marker.options._data.text = ridesText;

  // Call the original marker click handler to show sidebar
  markerClick(marker);

  L.DomEvent.stopPropagation(e);
}

function markerClick(marker) {
  var data = marker.options._data;
  active = [marker];

  renderPoints();

  setTimeout(() => {
    bar(".sidebar.show-spot");
    $$("#spot-header a").href = window.ontouchstart
      ? `geo:${data.lat},${data.lon}`
      : ` https://www.google.com/maps/place/${data.lat},${data.lon}`;
    $$("#spot-header a").innerText = `${data.lat.toFixed(4)}, ${data.lon.toFixed(
      4
    )} ☍`;

    $$("#spot-summary").innerHTML = summaryText(data);

    $$("#spot-text").innerHTML = data.text;
    if (!data.text && (!data.distance || Number.isNaN(data.distance)))
      $$("#extra-text").innerHTML =
        "No comments/ride info.";
    else $$("#extra-text").innerHTML = "";
    
    // Set up click handler for "Review this spot" button
    const reviewBtn = $$("#review-spot-btn");
    if (reviewBtn) {
      reviewBtn.onclick = function() {
        // Store the spot coordinates in form data and navigate to ride form
        const formData = {
          pickup_lat: data.lat,
          pickup_lon: data.lon,
          destination_lat: '',
          destination_lon: ''
        };
        sessionStorage.setItem('rideFormData', JSON.stringify(formData));
        window.location.href = '/ride';
      };
    }
  }, 100);
}

function bar(selector) {
  bars.forEach(function (el) {
    el.classList.remove("visible");
  });
  if (selector) $$(selector).classList.add("visible");
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

const osmToggle = document.getElementById("osm-toggle");
const hitchwikiToggle = document.getElementById("hitchwiki-toggle");
const textFilter = document.getElementById("text-filter");
const userFilter = document.getElementById("user-filter");
const distanceFilter = document.getElementById("distance-filter");
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
  osmToggle.checked = getQueryParameter("osmonly") == "true";
  hitchwikiToggle.checked = getQueryParameter("hitchwikionly") == "true";
  textFilter.value = getQueryParameter("text");
  userFilter.value = getQueryParameter("user");
  distanceFilter.value = getQueryParameter("mindistance");

  if (
    osmToggle.checked ||
    hitchwikiToggle.checked ||
    textFilter.value ||
    userFilter.value ||
    distanceFilter.value
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

    if (userFilter.value) {
      // Load rides data for filtering
      const rides = await loadRides();
      const username = userFilter.value.toLowerCase();
      
      // Find all rides by this user
      const userRides = rides.filter(ride => 
        ride.hitchhiker_name && 
        ride.hitchhiker_name.toLowerCase().includes(username)
      );
      
      // Get unique spot IDs from user rides
      const userSpotIds = [...new Set(userRides.map(ride => ride.spot_id))];
      
      // Filter markers to only show spots where this user has rides
      filterMarkers = filterMarkers.filter(marker => 
        userSpotIds.includes(marker.options.spotId)
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
    if (osmToggle.checked) {
      filterMarkers = filterMarkers.filter((x) => {
        return x.options._data.osm_id !== null && x.options._data.osm_id !== undefined;
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
        markerClick(m);
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
    
    // Return to ride form
    window.location.href = '/ride';
}

function cancelLocationSelection() {
    // Clean up and return to ride form without changing coordinates
    cleanupLocationSelection();
    
    // Return to ride form
    window.location.href = '/ride';
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
