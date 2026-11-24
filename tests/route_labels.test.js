// Till 2026-11-24: 👎 opens one-tap reasons; journeys from a planned route get one after-trip ask.
const fs = require("fs"), assert = require("assert");
const r = fs.readFileSync(__dirname + "/../hitch/static/routing.js", "utf8");
const i = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
assert(/vote === "down" && !moreCard\.querySelector\("\.rp-fb-reasons"\)/.test(r), "reasons on 👎");
assert(/aspect: "label", source: source, answer: answer/.test(r), "label beacon");
assert(/window\.addEventListener\("hm:trip-ask", maybeShowTripAsk\)/.test(r), "trip ask listener");
assert(/overlayOpen\(\) && tries\+\+ < 450/.test(r), "waits for overlays");
assert(/endedJourney\.plan !== "none"/.test(i), "only planned journeys");
assert(/const endedJourney = journeyStore\.get\(\);\n    journeyStore\.clear\(\);/.test(i), "read before clear");
assert(/getItem\("hmTripAsked"\) !== String\(r\.ts\)/.test(i), "once per plan");
console.log("route_labels ok");
