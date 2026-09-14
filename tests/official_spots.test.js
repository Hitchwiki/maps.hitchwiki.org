const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync('hitch/static/map.js', 'utf8');
const start = source.indexOf('function mergeOfficialSpots(');
const end = source.indexOf('// Load markers from JSON data', start);
assert.ok(start >= 0 && end > start);
const {mergeOfficialSpots, markerAppearance} = new Function(
  source.slice(start, end) + ';return {mergeOfficialSpots, markerAppearance};'
)();

test('unreviewed official stops are gray and have no fabricated rating', () => {
  const result = markerAppearance({official_unreviewed:true, review_count:0, rating:null});
  assert.equal(result.color, '#9ca3af');
  assert.equal(result.rating, null);
  assert.equal(markerAppearance({rating:5, review_count:2}).color, 'lightgreen');
  assert.equal(markerAppearance({official_unreviewed:true, review_count:1, rating:4}).color, 'lightgreen');
});

test('an already represented official node does not produce a duplicate marker', () => {
  const reviewed = {lat:50.20003, lon:7.20003, rating:5, review_count:1, osm:true};
  const official = [
    {lat:50.2, lon:7.2, map_spot_id:'50.20003_7.20003'},
    {lat:50.1, lon:7.1, map_spot_id:'50.10000_7.10000', official_unreviewed:true},
  ];
  const result = mergeOfficialSpots([reviewed], official);
  assert.equal(result.length, 2);
  assert.equal(result[0], reviewed);
  assert.equal(result[1], official[1]);
  assert.equal(mergeOfficialSpots(result, official).length, 2);
});

test('co-located nodes have one marker, including coordinates on the equator', () => {
  const rows = [{lat:0,lon:0,map_spot_id:'0.00000_0.00000'}, {lat:0,lon:0,map_spot_id:'0.00000_0.00000'}];
  assert.equal(mergeOfficialSpots([], rows).length, 1);
});

test('a newly designated stop enriches its existing marker without losing reviews', () => {
  const reviewed = {lat:50.2, lon:7.2, rating:5, review_count:2};
  const official = {lat:50.2, lon:7.2, map_spot_id:'50.20000_7.20000', osm_id:123, name:'Bench'};
  const result = mergeOfficialSpots([reviewed], [official]);
  assert.equal(result.length, 1);
  assert.equal(result[0].osm, true);
  assert.equal(result[0].rating, 5);
  assert.equal(result[0].review_count, 2);
  assert.equal(reviewed.osm, undefined);
});
