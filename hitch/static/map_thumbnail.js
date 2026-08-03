// Map thumbnails for ride cards (_ride_card.html) and the ride detail page.
//
// A ride that recorded a destination is drawn with both ends marked: a thumb where the
// hitchhiker was picked up and a checkered flag where the ride ended, the same two
// symbols the route planner puts on the ends of a hitchhiking leg (routing.js
// carStopIcon). Deliberately no line between them — the roads the driver actually took
// are unknown, and a straight line across the thumbnail would draw a route nobody drove.
//
// The glyphs are inline SVG rather than Font Awesome classes: the profile / activities /
// leaderboard pages don't load Font Awesome, and a card that quietly renders two empty
// squares is worse than one extra kilobyte of markup.
const THUMB_ICON_SVG =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3z"/>' +
    '<path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>';

const FLAG_ICON_SVG =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M4 22V3"/><path d="M4 5h16v10H4z"/>' +
    '<path fill="currentColor" stroke="none" d="M4 5h4v3.33H4zM12 5h4v3.33h-4zM8 8.33h4v3.34H8zM16 8.33h4v3.34h-4zM4 11.67h4V15H4zM12 11.67h4V15h-4z"/></svg>';

function rideStopIcon(kind) {
    return L.divIcon({
        className: 'ride-stop-marker ride-stop-marker--' + kind,
        html: '<div>' + (kind === 'start' ? THUMB_ICON_SVG : FLAG_ICON_SVG) + '</div>',
        iconSize: [24, 24],
        iconAnchor: [12, 12],
    });
}

// `opts.destLat`/`opts.destLon`: where the ride ended, when it recorded one. With a
// destination the view is fitted to both ends instead of using `zoom`, so the thumbnail
// shows how far the ride actually got.
//
// `opts.kind`: which symbol the single marker gets when there is no destination on this
// map. Defaults to the thumb; the ride page's separate destination map passes 'dest' so
// its one marker is the checkered flag it should be.
function initMapThumbnail(containerId, lat, lon, zoom = 7, opts = {}) {
    if (!lat || !lon || isNaN(lat) || isNaN(lon)) {
        return null;
    }

    const map = L.map(containerId, {
        center: [lat, lon],
        zoom: zoom,
        zoomControl: false,
        attributionControl: false,
        scrollWheelZoom: false,
        doubleClickZoom: false,
        dragging: false
    });

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

    const destLat = opts.destLat, destLon = opts.destLon;
    const hasDest = destLat != null && destLon != null && !isNaN(destLat) && !isNaN(destLon);

    L.marker([lat, lon], { icon: rideStopIcon(opts.kind === 'dest' ? 'dest' : 'start'), interactive: false }).addTo(map);
    if (hasDest) {
        L.marker([destLat, destLon], { icon: rideStopIcon('dest'), interactive: false }).addTo(map);
        // maxZoom so a 2 km ride doesn't zoom to street level, where the two markers
        // overlap into one blob; padding keeps both icons clear of the rounded corners.
        map.fitBounds(L.latLngBounds([[lat, lon], [destLat, destLon]]), {
            padding: [26, 26],
            maxZoom: 11,
        });
    }

    // "View on map" overlay link — opens the main map centered on the pickup point.
    // Uses zoom 13 for the main map so the user lands close to the location
    // even when the thumbnail itself is zoomed out for surrounding context.
    const container = document.getElementById(containerId);
    if (container) {
        const overlay = document.createElement('a');
        overlay.className = 'map-thumbnail-view-link';
        overlay.href = `/#${lat},${lon},13`;
        overlay.innerHTML = '<i class="fa fa-up-right-from-square"></i> View on map';
        container.appendChild(overlay);
    }

    return map;
}

// Build every thumbnail the shared ride-card macro rendered inside `root` (default: the
// whole document) and return the maps, so a caller that revealed a hidden container can
// invalidateSize() them — Leaflet cannot size a map inside a display:none parent, which
// is why the leaderboard's tabs defer their panes' thumbnails until first shown.
// Already-built thumbnails are skipped, so calling this twice is harmless.
function initThumbnailsIn(root) {
    const maps = [];
    (root || document).querySelectorAll('.map-thumbnail[data-thumb-lat]').forEach((el) => {
        if (el.dataset.thumbReady) return;
        el.dataset.thumbReady = '1';
        const map = initMapThumbnail(el.id, parseFloat(el.dataset.thumbLat), parseFloat(el.dataset.thumbLon), 7, {
            destLat: el.dataset.thumbDestLat !== undefined ? parseFloat(el.dataset.thumbDestLat) : null,
            destLon: el.dataset.thumbDestLon !== undefined ? parseFloat(el.dataset.thumbDestLon) : null,
        });
        if (map) maps.push(map);
    });
    return maps;
}

// Initialize thumbnails for a list of rides
function initRideThumbnails(rides) {
    rides.forEach((ride, index) => {
        if (ride.pickup_lat && ride.pickup_lon) {
            initMapThumbnail(`ride-thumbnail-${index}`, ride.pickup_lat, ride.pickup_lon);
        }
    });
}
