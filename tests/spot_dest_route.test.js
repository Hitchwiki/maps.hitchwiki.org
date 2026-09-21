// The spot pane's ride cards get a "Route" button that appears once a ride's destination
// is pinned and opens the planner from the spot to that destination. Source-regex test,
// same style as the other map.js tests.
const fs = require("fs");
const assert = require("assert");
const map = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
const routing = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
const css = fs.readFileSync(__dirname + "/../hitch/static/ride_card.css", "utf8");

// Rendered only for rides with a destination, right after the destination button (the
// CSS sibling selector depends on that order).
const destBtn = map.indexOf('class="ride-dest-btn"');
const routeBtn = map.indexOf('class="ride-route-btn"');
assert(destBtn > 0 && routeBtn > destBtn, "route button follows the destination button");
assert(map.slice(destBtn - 200, routeBtn + 200).includes("r.dest_lat != null") || map.slice(destBtn - 400, destBtn).includes("r.dest_lat != null"), "gated on a recorded destination");

// Hidden until the destination button is pinned.
assert(/\.ride-route-btn\s*\{[^}]*display:\s*none/.test(css), "hidden by default");
assert(/\.ride-dest-btn\.active\s*\+\s*\.ride-route-btn\s*\{[^}]*display:\s*inline-block/.test(css), "shown when pinned");

// Click handler: telemetry (no coordinates), then planner opened between spot and destination.
const h = map.indexOf('e.target.closest(".ride-route-btn")');
assert(h > 0, "click handler present");
const body = map.slice(h, h + 900);
assert(body.includes('hmTrack("spot_dest_route_clicked")'), "tracked");
assert(!/hmTrack\("spot_dest_route_clicked",/.test(body), "no properties (privacy: no coordinates)");
assert(body.includes("RoutingUI.openBetween("), "hands off to the planner");
assert(body.indexOf("active = []") < body.indexOf("openBetween("), "spot deselected before the planner opens");

// Planner side: fills both ends like a shared link does.
const ob = routing.indexOf("function openBetween(");
assert(ob > 0 && routing.includes("RJ.openBetween = openBetween"), "exposed");
const obBody = routing.slice(ob, ob + 400);
assert(obBody.includes('setPoint("start"') && obBody.includes('setPoint("dest"'), "sets both ends");
console.log("spot_dest_route ok");
