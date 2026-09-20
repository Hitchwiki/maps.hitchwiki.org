// IDEAS #528 s2: a zero-match filter shows a note with a Clear button instead of a silent blank map.
const fs = require("fs");
const assert = require("assert");
const src = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
const html = fs.readFileSync(__dirname + "/../hitch/templates/map.html", "utf8");
assert(/id="filter-empty-note"[^>]*hidden/.test(html), "note starts hidden");
assert(html.includes('id="filter-empty-clear"'));
const fn = src.slice(src.indexOf("function updateFilterEmptyNote"), src.indexOf("function setFilteredMarkers"));
assert(fn.includes("markers.length === 0"), "only an empty array (not null = no filter) shows the note");
assert(fn.includes("setTimeout") && fn.includes('hmTrack("filters_zero_match_shown", {})'), "shown event is settled, not per keystroke");
const setter = src.slice(src.indexOf("function setFilteredMarkers"), src.indexOf("// --- Hitchwiki events"));
assert(setter.includes("updateFilterEmptyNote(markers)"), "every filter result goes through the note");
assert(/hmTrack\("filters_zero_match_cleared", \{\}\);\s*clearFilters\.onclick\(\)/.test(src), "clear tracks then reuses Clear");
console.log("filter_zero_match_note ok");
