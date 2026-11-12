const fs=require("fs"),assert=require("assert");
const s=fs.readFileSync(__dirname+"/../hitch/static/routing.js","utf8");
assert(/hmVariant\("myloc-start-v1"/.test(s));
assert(/getCurrentPosition/.test(s) && !/getCurrentPosition[\s\S]{0,40}\bopen\(\)/.test(s));
assert(/start_src: RJ\._startSrc/.test(s));
assert(/planner_myloc_denied/.test(s));
console.log("ok myloc_start");
