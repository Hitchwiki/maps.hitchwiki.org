// #1337: driver first-pickup one-tap on the ride form; event-only, English-only, not in the ride payload.
const fs = require("fs"), assert = require("assert");
const t = fs.readFileSync(__dirname + "/../hitch/templates/ride_form.html", "utf8");
assert(/id="first-pickup-chips"/.test(t));
assert((t.match(/data-ans="(yes|no|unknown)"/g) || []).length === 3);
assert(/hmTrack\('driver_first_pickup', \{ ans: on\.dataset\.ans, surface: 'form' \}\)/.test(t));
assert(/t\("First time they picked/.test(t));
console.log("driver_first_pickup ok");
