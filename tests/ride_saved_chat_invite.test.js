// #591: the post-ride overlay carries a tracked chat invite. Source-regex test.
const fs = require("fs");
const assert = require("assert");
const html = fs.readFileSync(__dirname + "/../hitch/templates/map.html", "utf8");
const overlay = html.slice(html.indexOf('id="success-overlay"'));
assert(overlay.includes('data-chat-place="ride_saved"'), "ride_saved chat link in success overlay");
console.log("ride_saved_chat_invite ok");
