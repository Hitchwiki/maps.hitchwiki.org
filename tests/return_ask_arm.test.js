// IDEAS #1290: the return-ask arm is stored on the journey, logged once, and tagged on outcome events.
const fs = require("fs"), assert = require("assert");
const s = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
assert(/ra: j && j\.returnAskArm \? j\.returnAskArm : "na"/.test(s));
assert(/if \(raEligible && !j\.returnAskArm\)/.test(s));
assert(/hmTrack\("journey_return_ask_assigned", \{ arm: j\.returnAskArm \}\)/.test(s));
assert(/const returnAsk = raEligible && j\.returnAskArm === "ask"/.test(s));
console.log("return_ask_arm ok");
