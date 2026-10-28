// IDEAS #1182: cohortProps (end/cancel events) carries the company count.
const fs = require("fs"), assert = require("assert");
const s = fs.readFileSync(__dirname + "/../hitch/static/inride.js", "utf8");
assert(/co_hitchhikers: j && j\.coHitchhikers \? j\.coHitchhikers\.length : 0/.test(s));
console.log("cohort_props_company ok");
