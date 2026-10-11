const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync('hitch/static/map.js', 'utf8');
const start = source.indexOf('function cityExitCellIndex(');
const end = source.indexOf('function summaryText(', start);
assert.ok(start >= 0 && end > start);
const cityExitCellIndex = new Function(source.slice(start, end) + ';return cityExitCellIndex;')();
const cells = JSON.parse(fs.readFileSync('hitch/static/city_exit_cells.json', 'utf8'));

test('data file has aggregate rows only', () => {
  assert.ok(cells.length >= 30);
  for (const c of cells) assert.equal(c.length, 5);
});
test('a spot inside a cell matches, one 5 km away does not', () => {
  const c = cells[0];
  assert.equal(cityExitCellIndex(cells, {lat: c[0] + 0.002, lon: c[1] + 0.002}), 0);
  assert.equal(cityExitCellIndex(cells, {lat: c[0] + 0.05, lon: c[1]}), -1);
});
test('official stops and missing data never show the ask', () => {
  const c = cells[0];
  assert.equal(cityExitCellIndex(cells, {lat: c[0], lon: c[1], osm_id: 5}), -1);
  assert.equal(cityExitCellIndex(cells, {lat: c[0], lon: c[1], official_unreviewed: true}), -1);
  assert.equal(cityExitCellIndex(null, {lat: c[0], lon: c[1]}), -1);
});
