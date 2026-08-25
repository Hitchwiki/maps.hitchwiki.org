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

// A thumbnail is built only once it is near the viewport, never on page load.
//
// A ride list is long — the busiest profile here renders 120 cards — and building every
// map up front meant 120 Leaflet instances and several hundred tile requests before the
// visitor had scrolled past the first three. It is the single biggest cost of these
// pages, and it is bulk traffic aimed at OSM's tile servers for maps nobody looks at.
// Rendering the cards themselves stays eager: the list must remain complete markup, so
// in-page search, deep links and "save page" keep working.
//
// LAZY_MARGIN is generous on purpose — the map should already be drawn by the time the
// card reaches the screen, so lazy loading is invisible rather than a flash of grey.
const LAZY_MARGIN = '600px 0px';
let thumbObserver = null;

function buildThumbnail(el) {
    if (el.dataset.thumbReady) return null;
    el.dataset.thumbReady = '1';
    if (thumbObserver) thumbObserver.unobserve(el);
    return initMapThumbnail(el.id, parseFloat(el.dataset.thumbLat), parseFloat(el.dataset.thumbLon), 7, {
        destLat: el.dataset.thumbDestLat !== undefined ? parseFloat(el.dataset.thumbDestLat) : null,
        destLon: el.dataset.thumbDestLon !== undefined ? parseFloat(el.dataset.thumbDestLon) : null,
    });
}

function pendingThumbnails(root) {
    return Array.from((root || document).querySelectorAll('.map-thumbnail[data-thumb-lat]'))
        .filter((el) => !el.dataset.thumbReady);
}

// Register every thumbnail the ride-card macro rendered inside `root` (default: the whole
// document) for lazy building. Idempotent: already-built ones are skipped and re-observing
// an element is a no-op, so a page may call this again after adding cards.
function initThumbnailsIn(root) {
    const pending = pendingThumbnails(root);
    // Without IntersectionObserver, build everything at once — the old behaviour, and
    // still correct, just not lazy.
    if (typeof IntersectionObserver === 'undefined') {
        pending.forEach(buildThumbnail);
        return;
    }
    if (!thumbObserver) {
        thumbObserver = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) buildThumbnail(entry.target);
            });
        }, { rootMargin: LAZY_MARGIN });
    }
    pending.forEach((el) => thumbObserver.observe(el));
    // The observer's first callback is asynchronous, so paint the thumbnails that are
    // already on screen synchronously instead of leaving them blank for a frame.
    buildVisibleThumbnails(root);
}

// Build the thumbnails inside `root` that are on (or just off) the screen right now.
//
// The leaderboard's tabs need this explicitly: their panes are display:none until
// selected, and an element in one has no box for the observer to intersect. Rather than
// trust the observer to re-evaluate the moment `display` changes, the tab handler calls
// this on the pane it just revealed, which is deterministic.
function buildVisibleThumbnails(root) {
    const height = (typeof window !== 'undefined' && window.innerHeight) || 0;
    const margin = parseInt(LAZY_MARGIN, 10) || 0;
    pendingThumbnails(root).forEach((el) => {
        const box = el.getBoundingClientRect();
        // Zero-sized means it is still inside a hidden container: leave it to the observer.
        if (!box.height && !box.width) return;
        if (box.top < height + margin && box.bottom > -margin) buildThumbnail(el);
    });
}

// Initialize thumbnails for a list of rides
function initRideThumbnails(rides) {
    rides.forEach((ride, index) => {
        if (ride.pickup_lat && ride.pickup_lon) {
            initMapThumbnail(`ride-thumbnail-${index}`, ride.pickup_lat, ride.pickup_lon);
        }
    });
}
