// #559: the car-pooling filter and spot-sheet link were live with no telemetry. Source-regex
// test, same style as the other map.js tests.
const fs = require("fs");
const assert = require("assert");
const map = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");

const f = map.indexOf('carPoolingToggle.addEventListener("input"');
assert(f > 0);
const fb = map.slice(f, f + 420);
assert(fb.includes('if (carPoolingToggle.checked) hmTrack("carpool_filter_enabled")'), "only switch-on is counted");
assert(fb.includes('setQueryParameter("carpoolingonly"'), "filter behaviour unchanged");

assert(map.includes('class="spot-carpool-link"'), "link is tagged");
assert(map.includes('e.target.closest(".spot-carpool-link")) hmTrack("spot_carpool_link_clicked")'), "click tracked");
assert(map.includes("if ((payload.spot || {}).car_pooling) hmTrack('carpool_spot_shown')"), "shown tracked");
for (const ev of ["carpool_filter_enabled", "spot_carpool_link_clicked", "carpool_spot_shown"]) {
  assert(!new RegExp(`hmTrack\\(["']${ev}["'],`).test(map), ev + " carries no properties");
}
console.log("carpool_telemetry ok");
