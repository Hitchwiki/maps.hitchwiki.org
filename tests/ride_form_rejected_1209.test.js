// #1209: the ride form must count server-side rejections (bucket only, no raw text).
const fs = require('fs');
const src = fs.readFileSync(__dirname + '/../hitch/templates/ride_form.html', 'utf8');
const must = [
    /hmTrack\('ride_form_rejected'/,
    /j\._status = res\.status/,
    /reason: reasonBucket/,
];
for (const re of must) {
    if (!re.test(src)) { console.error('FAIL missing ' + re); process.exit(1); }
}
if (/ride_form_rejected'[^)]*json\.error/.test(src.replace(/\n/g, ' '))) {
    console.error('FAIL raw error text sent'); process.exit(1);
}
console.log('ok 1209');
