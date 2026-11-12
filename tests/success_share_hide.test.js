const fs=require("fs"),assert=require("assert");
const s=fs.readFileSync(__dirname+"/../hitch/static/map.js","utf8");
const c=fs.readFileSync(__dirname+"/../hitch/static/style.css","utf8");
assert(/hmVariant\("success-share-hide-v1", \["off", "on"\]\)/.test(s));
assert(/classList\.toggle\("hm-share-hidden"/.test(s));
assert(/success_share_hide_exposure/.test(s) && /success_share_hide_cta/.test(s));
assert(/\.hm-share-hidden #success-share-btn/.test(c));
assert(!/\.hm-share-hidden #success-share-block \{/.test(c), "must not hide the whole block (driver/city/planner links live in it)");
console.log("ok success_share_hide");
