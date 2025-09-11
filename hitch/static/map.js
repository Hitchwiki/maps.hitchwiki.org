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
  ridesData = null;

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
        '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>, <a href=https://hitchmap.com/copyright.html>Hitchmap</a>',
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

// Load heatmap data
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
  
  if (heatmapActive) {
    // Switch back to normal view
    if (heatmapLayer) {
      map.removeLayer(heatmapLayer);
    }
    if (heatmapLegend) {
      map.removeControl(heatmapLegend);
    }
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
    
    // Create heatmap layer
    if (!heatmapLayer) {
      const imageArray = heatmapData.image_data.map(row => 
        row.map(pixel => [
          Math.round(pixel[0] * 255),
          Math.round(pixel[1] * 255), 
          Math.round(pixel[2] * 255),
          Math.round(pixel[3] * 255)
        ])
      );
      
      // Convert to ImageData-like format for canvas
      heatmapLayer = L.imageOverlay(
        createImageDataURL(imageArray), 
        heatmapData.bounds,
        { opacity: 0.7 }
      );
    }
    
    // Create and add legend
    if (!heatmapLegend) {
      heatmapLegend = createHeatmapLegend(heatmapData.legend);
    }
    
    heatmapLayer.addTo(map);
    heatmapLegend.addTo(map);
    btn.classList.add('active');
    text.textContent = 'Normal';
    heatmapActive = true;
  }
}

// Helper function to create image data URL from array
function createImageDataURL(imageArray) {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  canvas.width = imageArray[0].length;
  canvas.height = imageArray.length;
  
  const imageData = ctx.createImageData(canvas.width, canvas.height);
  let dataIndex = 0;
  
  for (let y = 0; y < canvas.height; y++) {
    for (let x = 0; x < canvas.width; x++) {
      const pixel = imageArray[y][x];
      imageData.data[dataIndex] = pixel[0];     // Red
      imageData.data[dataIndex + 1] = pixel[1]; // Green  
      imageData.data[dataIndex + 2] = pixel[2]; // Blue
      imageData.data[dataIndex + 3] = pixel[3]; // Alpha
      dataIndex += 4;
    }
  }
  
  ctx.putImageData(imageData, 0, 0);
  return canvas.toDataURL();
}

// Create heatmap legend
function createHeatmapLegend(legendData) {
  const legend = L.control({ position: 'bottomright' });
  
  legend.onAdd = function(map) {
    const div = L.DomUtil.create('div', 'heatmap-legend');
    div.innerHTML = `
      <h4>${legendData.caption}</h4>
      <div class="legend-scale">
        <div class="legend-gradient"></div>
        <div class="legend-labels">
          <span>${legendData.vmin}</span>
          <span>${legendData.vmax}</span>
        </div>
      </div>
      <div class="uncertainty-indicator">
        <div class="uncertainty-title">Data certainty:</div>
        <div class="uncertainty-scale">
          <div class="uncertainty-bar">
            <div class="uncertainty-gradient"></div>
          </div>
          <div class="uncertainty-labels">
            <span>Less certain</span>
            <span>More certain</span>
          </div>
        </div>
      </div>
    `;
    
    // Create gradient background for wait time scale
    const gradient = div.querySelector('.legend-gradient');
    // BUCKETS contains color arrays like [r, g, b] with values 0-1, need to convert to CSS colors
    const colors = legendData.colors.map(color => {
      if (Array.isArray(color) && color.length >= 3) {
        return `rgb(${Math.round(color[0] * 255)}, ${Math.round(color[1] * 255)}, ${Math.round(color[2] * 255)})`;
      } else if (typeof color === 'string') {
        return color; // Already a CSS color string
      } else {
        console.warn('Unexpected color format:', color);
        return 'rgb(128, 128, 128)'; // Fallback gray
      }
    });
    gradient.style.background = `linear-gradient(to right, ${colors.join(', ')})`;
    
    // Create opacity gradient for uncertainty indicator
    const uncertaintyGradient = div.querySelector('.uncertainty-gradient');
    // Use a blue color for the uncertainty indicator
    uncertaintyGradient.style.background = `linear-gradient(to right, rgba(74, 144, 226, 0.3), rgba(74, 144, 226, 1.0))`;
    
    return div;
  };
  
  return legend;
}

// Initialize the map and set up event listeners
(async () => {
  map = await initializeMap();

  // Set up interactive elements
  setupGeocoder();
  addMapControls();
  setupEventListeners();
  
  // Set up heatmap toggle
  const heatmapBtn = $$('#heatmap-toggle-btn');
  if (heatmapBtn) {
    heatmapBtn.addEventListener('click', toggleHeatmap);
  }

  // These functions make the navigation work
  handleHashChange();
  window.onhashchange = navigate;
  navigate();
})();

// Set up the geocoder for location search
function setupGeocoder() {
  var geocoderOpts = {
    collapsed: false,
    defaultMarkGeocode: false,
    position: "topleft",
    provider: "photon",
    placeholder: "Jump to city, search comments",
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
  map.addControl(new MenuButton());
  map.addControl(new AddSpotButton());
  map.addControl(new AccountButton());
  map.addControl(new FilterButton());

  var zoom = $$(".leaflet-control-zoom");
  zoom.parentNode.appendChild(zoom);
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

  setupKnobEventListeners();
  setupFilterEventListeners();

  let filterPane = map.createPane("filtering");
  filterPane.style.zIndex = 450;

  map.createPane("arrowlines");
  filterPane.style.zIndex = 1450;
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

// Set up event listeners for the knob control
function setupKnobEventListeners() {
  knob.addEventListener("mousedown", (e) => {
    isDragging = true;
    updateRotation(e);
    updateDirectionQueryParameter();
  });

  window.addEventListener("mousemove", (e) => {
    if (isDragging) {
      updateRotation(e);
      updateDirectionQueryParameter();
    }
  });

  window.addEventListener("mouseup", () => {
    isDragging = false;
  });
}

// Set up event listeners for filter controls
function setupFilterEventListeners() {
  spreadInput.addEventListener("input", updateConeSpread);
  knobToggle.addEventListener("input", () =>
    setQueryParameter("mydirection", knobToggle.checked)
  );
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

// Update the direction query parameter based on knob rotation
function updateDirectionQueryParameter() {
  const angle = Math.round(radAngle * (180 / Math.PI) + 90) % 360;
  const normalizedAngle = (angle + 360) % 360; // Normalize angle
  setQueryParameter("direction", normalizedAngle);
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
    map.addControl(new HeatmapInfoButton());
    $$(".filter-button").remove();
    $$(".add-spot").remove();
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
  const osmLink = data.osm_id ? `\n    <a href="https://www.openstreetmap.org/node/${data.osm_id}" target="_blank" rel="noopener noreferrer">Official hitchhiking spot</a>` : '';
  
  return `Rating: ${data.rating && data.rating.toFixed(0)}/5
    Waiting time: ${
      !data.wait || Number.isNaN(data.wait) ? "-" : data.wait.toFixed(0) + " min"
    }
    Ride distance: ${
      !data.distance || Number.isNaN(data.distance) ? "-" : data.distance.toFixed(0) + " km"
    }${osmLink}`;
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
        url: `https://hitchmap.com/${m.options._data.lat},${m.options._data.lon}`,
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
      creator: "Hitchmap",
      featureDescription: (f) => toPlainText(f.text),
      featureLink: (f) => f.url,
    });

    function downloadGPX(data) {
      const blob = new Blob([data], { type: "application/gpx+xml" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "hitchmap.gpx";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }

    downloadGPX(gpxStr);
  };
  document.body.appendChild(script);
}

const knob = document.getElementById("knob");
const knobLine = document.getElementById("knobLine");
const knobCone = document.getElementById("knobCone");
const rotationValue = document.getElementById("rotationValue");
const spreadInput = document.getElementById("spreadInput");
spreadInput.value = 70;
const knobToggle = document.getElementById("knob-toggle");
const osmToggle = document.getElementById("osm-toggle");
const hitchwikiToggle = document.getElementById("hitchwiki-toggle");
const textFilter = document.getElementById("text-filter");
const userFilter = document.getElementById("user-filter");
const distanceFilter = document.getElementById("distance-filter");
const clearFilters = document.getElementById("clear-filters");

let isDragging = false,
  radAngle = 0;

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

function updateRotation(event) {
  const rect = knob.getBoundingClientRect();
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;

  const dx = event.clientX - centerX;
  const dy = event.clientY - centerY;

  radAngle = Math.atan2(dy, dx);
}

function updateConeSpread() {
  // Clamp spread between 1 and 89
  const spread = Math.min(89, parseInt(spreadInput.value, 10) || 0);

  if (spread > 0) setQueryParameter("spread", spread);
}

async function applyParams() {
  const normalizedAngle = parseFloat(getQueryParameter("direction"));
  const spread = parseFloat(getQueryParameter("spread")) || 70;

  if (!isNaN(normalizedAngle)) {
    knobLine.style.transform = `translateX(-50%) rotate(${normalizedAngle}deg)`;
    knobCone.style.transform = `rotate(${normalizedAngle}deg)`;
    rotationValue.textContent = `${Math.round(normalizedAngle)}°`;
    radAngle = (normalizedAngle - 90) * (Math.PI / 180); // Update radAngle for consistency
  }

  spreadInput.value = spread;
  const radiansSpread = spread * (Math.PI / 180); // Convert spread angle to radians

  const multiplier = 100; // Factor to increase the cone's distance

  // Calculate cone boundaries using trigonometry and multiply by the multiplier
  const leftX = 50 - Math.sin(radiansSpread) * 50 * multiplier; // 50 is the radius
  const rightX = 50 + Math.sin(radiansSpread) * 50 * multiplier;
  const topY = 50 - Math.cos(radiansSpread) * 50 * multiplier; // Top vertex

  knobCone.style.clipPath = `polygon(50% 50%, ${leftX}% ${topY}%, ${rightX}% ${topY}%)`;

  knobToggle.checked = getQueryParameter("mydirection") == "true";
  osmToggle.checked = getQueryParameter("osmonly") == "true";
  hitchwikiToggle.checked = getQueryParameter("hitchwikionly") == "true";
  textFilter.value = getQueryParameter("text");
  userFilter.value = getQueryParameter("user");
  distanceFilter.value = getQueryParameter("mindistance");

  if (
    knobToggle.checked ||
    osmToggle.checked ||
    hitchwikiToggle.checked ||
    textFilter.value ||
    userFilter.value ||
    distanceFilter.value
  ) {
    if (filterMarkerGroup) filterMarkerGroup.remove();
    if (filterDestLineGroup) filterDestLineGroup.remove();

    let filterMarkers =
      knobToggle.checked || distanceFilter.value
        ? destinationMarkers
        : allMarkers;
    // display filters pane
    document.body.classList.add("filtering");

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
    if (knobToggle.checked) {
      filterMarkers = filterMarkers.filter((x) => {
        let from = x.getLatLng();
        let lats = x.options._data.dest_lats;
        let lons = x.options._data.dest_lons;

        for (let i in lats) {
          let travelAngle = Math.atan2(from.lat - lats[i], lons[i] - from.lng);
          // difference between the travel direction and the cone line
          let coneLineDiff = Math.abs(travelAngle - radAngle);
          let wrappedDiff = Math.min(coneLineDiff, 2 * Math.PI - coneLineDiff);
          // if the direction falls within the knob's cone
          if (wrappedDiff < radiansSpread) return true;
        }
        return false;
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
    clear();
    bar(".sidebar.filters");
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
  } else if (mainArgs.length == 2 && !isNaN(mainArgs[0])) {
    clear();
    let lat = +mainArgs[0],
      lon = +mainArgs[1];
    for (let m of allMarkers) {
      if (m._latlng.lat === lat && m._latlng.lng === lon) {
        markerClick(m);
        if (map.getZoom() < 3) map.setView(m.getLatLng(), 16);
        return;
      }
    }
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
      navigateHome();

      if (document.body.classList.contains("menu")) {
        bar();
      } else {
        bar(".sidebar.menu");
      }

      document.body.classList.toggle("menu");
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

var FilterButton = L.Control.extend({
  options: {
    position: "topleft",
  },
  onAdd: function (map) {
    var controlDiv = L.DomUtil.create(
      "div",
      "leaflet-bar horizontal-button filter-button"
    );
    var container = L.DomUtil.create("a", "", controlDiv);
    container.href = "#filters";
    container.innerHTML = "🧮 Filters";

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
