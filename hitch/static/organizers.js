(() => {
  const report = JSON.parse(document.getElementById('organizer-data').textContent);
  const track = (event) => window.hmTrack?.(event);
  document.getElementById('print-report')?.addEventListener('click', () => { track('organizer_report_print'); window.print(); });
  document.querySelector('[data-organizer-action="csv"]')?.addEventListener('click', () => track('organizer_report_csv'));
  for (const id of ['report-link', 'website-link']) {
    document.getElementById(id)?.addEventListener('focus', (event) => event.target.select());
    document.getElementById(id)?.addEventListener('copy', () => track('organizer_report_link_copied'));
  }
  if (!window.L) return; // The bounds form and server-rendered report also work without tiles/JS.
  const map = L.map('area-map').setView([51, 10], 6);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }).addTo(map);
  if (report) {
    const [w, s, e, n] = report.bounds;
    map.fitBounds([[s, w], [n, e]], {animate: false});
    L.rectangle([[s, w], [n, e]], {color: '#145d45', fillOpacity: 0.03}).addTo(map);
    report.rows.forEach(row => {
      const label = document.createElement('a');
      label.href = row.map_url;
      label.textContent = `${row.name}: ${row.stats.count} dokumentierte Fahrten`;
      L.circleMarker([row.lat, row.lon], {radius: 6, color: '#145d45'}).addTo(map).bindPopup(label);
    });
    track('organizer_report_viewed');
    return;
  }
  const bbox = document.getElementById('bbox');
  const syncBounds = () => {
    const b = map.getBounds();
    bbox.value = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map(v => v.toFixed(5)).join(',');
    bbox.setCustomValidity(b.getEast() - b.getWest() > 5 || b.getNorth() - b.getSouth() > 5
      ? 'Bitte näher heranzoomen oder einen kleineren Ausschnitt eingeben (höchstens 5° je Richtung).' : '');
  };
  bbox.addEventListener('input', () => bbox.setCustomValidity(''));
  map.on('moveend', syncBounds);
  const params = new URLSearchParams(location.search);
  const lat = Number(params.get('lat')), lon = Number(params.get('lon'));
  if (params.has('lat') && params.has('lon') && Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
    map.setView([lat, lon], 12, {animate: false});
  }
  syncBounds();
  document.getElementById('area-form').addEventListener('submit', () => track('organizer_area_selected'));
  document.getElementById('place-search').addEventListener('submit', async event => {
    event.preventDefault();
    const status = document.getElementById('search-status');
    const results = document.getElementById('search-results');
    results.replaceChildren();
    status.textContent = 'Suche läuft …';
    try {
      const response = await fetch(`https://photon.komoot.io/api/?limit=5&lang=de&q=${encodeURIComponent(document.getElementById('place').value)}`);
      if (!response.ok) throw new Error('search');
      const data = await response.json();
      status.textContent = data.features.length ? 'Wählen Sie einen Treffer:' : 'Kein Treffer. Wählen Sie den Ausschnitt direkt auf der Karte.';
      for (const feature of data.features) {
        const button = document.createElement('button');
        button.type = 'button';
        const p = feature.properties;
        button.textContent = [p.name, p.city, p.state, p.country].filter(Boolean).join(', ');
        button.addEventListener('click', () => {
          const [lng, latitude] = feature.geometry.coordinates;
          map.setView([latitude, lng], 12, {animate: false});
          status.textContent = 'Prüfen Sie den Ausschnitt auf der Karte und öffnen Sie den Bericht.';
        });
        const li = document.createElement('li'); li.append(button); results.append(li);
      }
    } catch (_) { status.textContent = 'Die Ortssuche ist gerade nicht erreichbar. Wählen Sie den Ausschnitt auf der Karte.'; }
  });
})();
