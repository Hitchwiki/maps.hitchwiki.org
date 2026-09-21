// #566: click side for the spot sheet's Hitchwiki inserts. Source-regex test.
const fs = require("fs");
const assert = require("assert");
const map = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
assert(map.includes('class="spot-wiki-link" data-kind="article"'), "article link tagged");
assert(map.includes('class="spot-wiki-link" data-kind="map"'), "area link tagged");
assert(map.includes('hmTrack("spot_wiki_link_clicked", { kind: link.dataset.kind })'), "link click tracked with kind only");
assert(map.includes('e.target.closest(".spot-wiki-excerpt a")) hmTrack("spot_wiki_excerpt_clicked")'), "excerpt link click tracked");
assert(!/spot_wiki_excerpt_clicked["'],/.test(map), "no properties on excerpt click");
console.log("spot_wiki_clicks ok");
