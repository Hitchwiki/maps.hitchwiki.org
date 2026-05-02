// Map thumbnail functionality
function initMapThumbnail(containerId, lat, lon, zoom = 7) {
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
    
    L.marker([lat, lon]).addTo(map);

    // "View on map" overlay link — opens the main map centered on this point.
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

// Initialize thumbnails for a list of rides
function initRideThumbnails(rides) {
    rides.forEach((ride, index) => {
        if (ride.pickup_lat && ride.pickup_lon) {
            initMapThumbnail(`ride-thumbnail-${index}`, ride.pickup_lat, ride.pickup_lon);
        }
    });
}