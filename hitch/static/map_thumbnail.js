// Map thumbnail functionality
function initMapThumbnail(containerId, lat, lon, zoom = 15) {
    if (!lat || !lon || isNaN(lat) || isNaN(lon)) {
        return null;
    }
    
    const map = L.map(containerId, {
        center: [lat, lon],
        zoom: zoom,
        zoomControl: false,
        scrollWheelZoom: false,
        doubleClickZoom: false,
        dragging: false
    });
    
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap'
    }).addTo(map);
    
    L.marker([lat, lon]).addTo(map);
    
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