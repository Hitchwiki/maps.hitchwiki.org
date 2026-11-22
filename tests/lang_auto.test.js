// Static checks for the lang-auto-v1 first-visit switch (IDEAS #1660).
const fs = require("fs"), assert = require("assert");
const s = fs.readFileSync(__dirname + "/../hitch/templates/map.html", "utf8");
for (const needle of ["lang-auto-v1", "lang_auto_assigned", "lang_auto_engaged", "lang_auto_back_en", "location.replace", "searchParams.delete('ref')"])
  assert(s.includes(needle), "missing " + needle);
assert(s.indexOf("lang-auto-v1") < s.indexOf("hmLangOfferShown"), "assignment must run before the pill script");
console.log("ok");
