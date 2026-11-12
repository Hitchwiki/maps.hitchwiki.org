const fs=require("fs"),assert=require("assert");
const s=fs.readFileSync(__dirname+"/../hitch/static/map.js","utf8");
const m=s.match(/function isWikiReaderRef[\s\S]*?\n}\n/);assert(m);
const READ=["wiki_main_page","wiki_link","wiki_route_link","wiki_article"],SEEK=["wiki_infobox_pin","wiki_infobox_map","wiki_infobox_here"];
const f=new Function("WIKI_READER_REFS","WIKI_SEEKER_REFS",m[0]+"return isWikiReaderRef;")(READ,SEEK);
assert(f("wiki_mobile_menu")&&f("wiki_record_ride_pickup")&&f("wiki_article"));
assert(!f("wiki_infobox_pin")&&!f("wiki_infobox_new")&&!f("")&&!f("reddit"));
assert(/isWikiReaderRef\(lref\)/.test(s));
console.log("ok wiki_reader_pledge");
