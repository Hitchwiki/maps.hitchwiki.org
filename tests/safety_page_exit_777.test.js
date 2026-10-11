const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const js = fs.readFileSync('hitch/static/hitchhiking_safety.js', 'utf8');
const html = fs.readFileSync('hitch/templates/hitchhiking_safety.html', 'utf8');

test('safety page tracks view and first cohort change without cohort contents', () => {
  assert.match(js, /track\("safety_page_viewed"\)/);
  assert.match(js, /track\("safety_cohort_changed"\)/);
  assert.match(js, /window\.hmTrack\(name, \{\}\)/);
});
test('safety page carries the tracked chat link', () => {
  assert.match(html, /data-chat-place="safety_page"/);
  assert.match(html, /href="\{\{ GENERAL_CHAT_URL \}\}"/);
});
