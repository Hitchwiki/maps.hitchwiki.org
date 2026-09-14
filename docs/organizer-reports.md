# Reports for official-stop organizers

`/mitfahrbaenke` is a German, indexable entry point linked from the map menu,
official-spot details, and the generated sitemap. Visitors search with Photon
(the map's existing search provider) and choose a rectangle. Coordinates can also
be entered without JavaScript. Search results do not claim municipal boundaries.

`/mitfahrbaenke/bericht?bbox=west,south,east,north` is a server-rendered,
shareable report. Optional `von=YYYY-MM-DD&bis=YYYY-MM-DD` selects an inclusive
period and compares it with the immediately preceding period of equal length.
`format=csv` downloads the per-stop summary. Printing supports saving to PDF.
The page supplies a permanent link and HTML link text for municipal websites.
Arbitrary area reports are noindex; the landing page is the search entry point.

Report links to a stop use `/official-stop/<osm_node_id>`. This redirects to the
existing associated ride marker, or to the official node's coordinates when it
has no reviews. The map loads `/official-stops.json` alongside the generated
ride spots, adding missing official stops as gray markers without ratings or
invented ride records. Existing associated markers retain their reviews and
colors. The registry is read from the existing OSM table, so new stops appear
without requiring a full ride-data regeneration. Registry-only markers carry
their own names and OSM links and do not request nonexistent ride-detail files.

## Evidence and limitations

- All `OsmHitchhikingSpot` nodes in the selected rectangle are listed, including
  those without associated rides. This is mapped coverage, not a full inventory.
- Associations come from `dist/rides/by-spot/*.json`'s `spot.osm_id`, exactly as
  on the map, not from a newly invented proximity join. Multiple ride spots can
  map to one official node; a repeated ride ID is counted once.
- `dist/rides_index.json` supplies rides. The optional `rd` timestamp is the only
  date used for comparisons. Submission timestamps are not substituted. Unknown
  ride dates are counted separately, included in all-time totals, and excluded
  from both comparison periods. Dates follow the generated index's UTC day.
- Wait summaries include finite nonnegative values, including zero. Histograms
  retain all valid waits without trimming outliers. Each median shows its sample
  size. An empty sample is displayed as missing, never zero minutes.
- Attempts marked `no_ride` in the per-spot files are counted separately and
  excluded from successful ride counts and waiting-time statistics.
- Spatial association is not confirmation of bench use. Voluntary reports do
  not establish total usage, pickup success rates, or causal policy effects.
  The report explains these limits alongside the results.

No background task, external outreach, or schema migration is required. The
evidence cache is bounded to one generated snapshot and invalidated by the
`spots.json` and `rides_index.json` modification times. Missing or incomplete
generated files produce 503 rather than a misleading empty report. The full
index is read only on a cold cache; only associated rides remain cached.

Analytics events: `organizer_area_selected`, `organizer_report_viewed`,
`organizer_report_csv`, `organizer_report_print`, `organizer_report_link_copied`.
These measure resource use, not whether a visitor represents a municipality.

Validation: `tests/test_organizers.py` covers geographic scope, zero-report
stops, date boundaries, unknown dates, duplicate IDs, missing data, escaping,
CSV, and indexing. The existing Python and JavaScript suites also cover the
shared application and map. Browser checks exercise search, navigation, CSV
download, and desktop/mobile layouts with synthetic, explicitly local fixtures.
