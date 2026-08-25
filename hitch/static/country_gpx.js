(function (root, factory) {
  "use strict";
  const api = factory(root);
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else {
    root.CountryGpx = api;
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", api.init);
    } else {
      api.init();
    }
  }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  const INDEX_URL = "/spots_by_country/index.json";

  function entries(index) {
    return Object.entries(index || {})
      .filter(([code, item]) => /^[A-Z]{2}$/.test(code) && item && item.name)
      .sort((a, b) => a[1].name.localeCompare(b[1].name));
  }

  function size(bytes) {
    const mb = Number(bytes) / (1024 * 1024);
    return mb < 0.1 ? `${Math.max(1, Math.round(Number(bytes) / 1024))} KB` : `${mb.toFixed(1)} MB`;
  }

  function href(code) {
    return /^[A-Z]{2}$/.test(code) ? `/spots_by_country/${code}.gpx` : null;
  }

  async function init() {
    const select = document.getElementById("country-gpx-select");
    const link = document.getElementById("country-gpx-download");
    const status = document.getElementById("country-gpx-status");
    if (!select || !link || !status) return;

    let index;
    try {
      const response = await fetch(INDEX_URL);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      index = await response.json();
    } catch (_) {
      select.disabled = true;
      status.textContent = "Country downloads are temporarily unavailable.";
      return;
    }

    entries(index).forEach(([code, item]) => {
      const option = document.createElement("option");
      option.value = code;
      option.textContent = `${item.name} (${Number(item.spot_count).toLocaleString()} spots)`;
      select.appendChild(option);
    });

    select.addEventListener("change", function () {
      const code = select.value;
      const item = index[code];
      const url = href(code);
      if (!item || !url) {
        link.hidden = true;
        status.textContent = "";
        return;
      }
      link.href = url;
      link.textContent = `Download ${item.name} GPX (${size(item.size_bytes)})`;
      link.hidden = false;
      status.textContent = "";
    });

    link.addEventListener("click", function () {
      if (typeof root.hmTrack === "function") root.hmTrack("country_gpx_downloaded");
    });
  }

  return { entries, size, href, init };
});
