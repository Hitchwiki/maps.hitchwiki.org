// #565: the empty-spot chat prompt is clicked but was never counted as shown. Source-regex test.
const fs = require("fs");
const assert = require("assert");
const map = fs.readFileSync(__dirname + "/../hitch/static/map.js", "utf8");
assert(map.includes('if (emptyChat && noInfo) hmTrack("spot_empty_chat_shown")'), "impression tracked only when visible");
assert(map.includes("if (emptyChat) emptyChat.hidden = !noInfo;"), "visibility logic unchanged");
assert(!/hmTrack\(["']spot_empty_chat_shown["'],/.test(map), "no properties (no spot id / coordinates)");
console.log("empty_chat_shown ok");
