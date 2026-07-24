# Spot names

Show a human-readable name at the top of the spot pane instead of only coordinates, e.g.
`Raststätte Michendorf-Nord` for `/spot/52.30217_13.01991`.

## Goal

Every spot that can be named gets a name. The name comes from OSM data we already
store where possible, and from a cached reverse geocode otherwise. Spots that
cannot be named look exactly as they do today.

## Naming cascade

`show.py` resolves one name per spot, first match wins:

| # | Source | Match rule | Example | Rows with a name |
|---|---|---|---|---|
| 1 | `osm_hitchhiking_spot.tags.name` | ≤100 m | official spot name | 466 |
| 2 | `service_area.name` | polygon containing the spot | `Raststätte Michendorf-Nord` | 3,254 |
| 3 | `osm_fuel_station_spot.tags` | ≤100 m | `Michendorf Nord` | 324,068 |
| 4 | `osm_car_pooling_spot.tags.name` | ≤100 m | `P+R Kaulsdorf` | 1,533 |
| 5 | `spot_name.name` | exact `spot_id` | `An der A10, Michendorf` | the remaining ~30k |

No match at any step → no name; the pane header renders as it does today.

An official hitchhiking spot outranks the service area it sits in: a name someone
chose for the *hitchhiking* feature describes the spot better than the name of the
rest area around it.

For fuel (step 3), prefer `tags.name`, then `tags.brand`, then `tags.operator` — an
unnamed station of a known chain is still better identified as `Shell` than as a
street.

Only 5,520 of 35,140 spots (16%) have any OSM feature within 100 m, so step 5 is the
common case, not the exception.

### Service-area names must match the merge

`show.py` already assigns each coordinate a containing service-area polygon
(`assign_polygon`, largest polygon wins) and merges every spot inside one polygon
onto a single anchor. Step 2 reuses **that same polygon id**, not a fresh lookup, so
the displayed name always describes the area the spot was merged into.

This is what produces the motivating example. The spot at `52.30217, 13.01991` lies
inside both the fuel building `24628816` (`Michendorf Nord`) and the larger
`highway=services` polygon `369344514` (`Raststätte Michendorf-Nord`); the
largest-polygon rule picks the latter for merging, and therefore for the name.

`service_area.name` is NULL for 403 of 3,657 polygons — those fall through to step 3.

### Memory constraint on the OSM tag lookups

`show.py` loads all 406,013 fuel rows to do the distance join. Adding their `tags`
JSON to that read would cost roughly 200 MB resident, on a host the OOM killer has
already visited (CLAUDE.md, "Container killed by OOM").

So tags are **not** part of the bulk read. The distance joins keep returning ids
exactly as they do now; a second query then fetches tags for only the matched ids:

```sql
SELECT id, tags FROM osm_fuel_station_spot WHERE id IN (…~5.4k ids…)
```

The same two-phase pattern is used for the hitchhiking and car-pooling tables, for
uniformity, even though those are small.

## `spot_name` table and `hitch/scripts/spot_names.py`

A new standalone script, modelled directly on `hitch/scripts/ride_places.py`: plain
`python3` (not `flask generate`), no app context, raw `sqlite3`, its own
`CREATE TABLE IF NOT EXISTS`, and it only resolves rows it does not already have.

```sql
CREATE TABLE IF NOT EXISTS spot_name (
    spot_id     VARCHAR(64) PRIMARY KEY,
    name        VARCHAR(255),
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    geocoded_at VARCHAR(32) NOT NULL
);
```

A matching `SpotName` model goes in `hitch/models.py` so the schema is documented
where the others are. Because there is no migration framework, creating the table on
production is the script's own `CREATE TABLE IF NOT EXISTS` on first run.

### Input

The spot list is read from `dist/spots.json`, not from the database — that file is
the canonical, post-merge set of spots, and `spot_id` is derived from its coordinates
exactly as `generate_spot_id` does (`lat.toFixed(5)_lon.toFixed(5)`).

This makes the script depend on `show` having run, the same dependency `sync_fuel`
already has.

### Geocoding

Photon reverse, the same endpoint `route_preview.py` and `share_card.js` use:

```
GET https://photon.komoot.io/reverse?lat=…&lon=…&lang=en&limit=1
```

Rate-limited to 1 request/second, with the project `User-Agent`.

Label, from the first feature's `properties`:

1. `street` and `city` → `"{street}, {city}"`
2. `street` alone → `"{street}"`
3. `city` alone → `"{city}"`
4. no `street` and no `city` → the first present of `district`, `locality`,
   `county`, `state`, then the first *later* key in that same list that is present
   and different, joined by a comma → `"Straldzha, Yambol"`
5. none of those → `name = NULL`

Photon's `name` property is deliberately ignored. It holds the nearest POI, which is
sometimes the rest area and sometimes an unrelated kebab shop; a street is
predictable and always describes where the hitchhiker actually stands.

### Failure handling

A row is written **only on a successful HTTP response**. A row with `name = NULL`
therefore means "Photon answered and had nothing to offer" and is never retried. A
timeout, connection error, or 5xx writes nothing at all, so the spot is retried on
the next run rather than being cached as permanently unnamed.

### Runtime and scheduling

- `--limit N` caps the number of geocodes in one run. Default 2000 (≈33 min at
  1 req/s), which keeps a cron run bounded.
- `--limit 0` means unlimited.
- `--dry-run` prints the resolved labels without writing.
- Commits every 100 rows, so an interrupted run keeps its progress and simply
  resumes.

The initial backlog of ~30k spots is drained by one manual `--limit 0` run under
`nohup` (~8 h). Afterwards only newly created spots remain — a handful per day — so
the daily cron run finishes in seconds.

Cron: daily at 4:30 AM, after `sync_fuel` (3:45) and well clear of the nightly
`show` runs it depends on.

Note the script lives under `hitch/scripts/`, which is **not** bind-mounted into the
container — it needs an image rebuild before the cron entry takes effect
(CLAUDE.md, "Testing sync / generate scripts").

## Output

`show.py` writes the name into the per-spot detail file only:

```json
{"spot": {"name": "Raststätte Michendorf-Nord", "wait": 51, "distance": 372, …}, "rides": […]}
```

The key is omitted when there is no name, matching how the other optional `spot`
keys behave.

The name is deliberately **not** added to `spots.json`. That file is downloaded by
every visitor on map load; ~30k name strings would add roughly 1 MB to it, and
nothing in the chosen scope needs a name before a marker is clicked.

## Frontend

**Markup** (`map.html`): a new `<div id="spot-name">` above the existing
`#spot-coords-line`, inside `#spot-header-row`.

**Style** (`style.css`): `#spot-name` bold, ~1.15em, hidden by default;
`#spot-coords-line` becomes smaller and muted (grey) so the name reads as the title.

```
┌─ spot pane ───────────────────┐
│ Raststätte Michendorf-Nord    │  ← #spot-name, bold 1.15em
│ 52.3022, 13.0199              │  ← #spot-coords-line, small grey
│ Go to on Google Maps          │
│ See on Google Street View     │
│ Go to on OpenStreetMap        │
│ ↳ Share this spot             │
└───────────────────────────────┘
```

**Behaviour** (`map.js`):

- `markerClick` clears `#spot-name` and hides it, so a previously opened spot's name
  never bleeds into the next one during the fetch.
- `handleMarkerClick`, which already merges `payload.spot` into `marker.options._data`,
  fills and shows `#spot-name` when a name is present.
- Unnamed spots keep the element hidden, so the pane looks exactly as it does today
  and the header does not shift height.
- The name is escaped with the existing `escapeHtml` helper — it is OSM- and
  geocoder-supplied text.

**Share button**: `dataset.shareTitle` is set alongside the existing
`dataset.shareUrl`, mirroring `#share-country-btn`:

- named → `"Raststätte Michendorf-Nord – Hitchwiki Maps"`
- unnamed → the template's current static `"Hitchhiking spot on Hitchwiki Maps"`

Since `shareUrl` is set in `markerClick` (before the fetch) and the name only arrives
in `handleMarkerClick`, the title is set in `handleMarkerClick` too.

## `/spot/<id>` page title and OpenGraph

`_spot_preview` in `hitch/blueprints/main.py` already parses the per-spot file, so
the name costs no extra I/O.

One change is required to its contract: it currently returns `None` when no ride has
a rating, which would throw the name away for a named-but-unrated spot. It must
return the name regardless, with `rating`/`count`/`wait`/`distance` becoming optional
fields of the returned dict.

`render_spot` then builds:

- `spot_title`: `"Raststätte Michendorf-Nord — hitchhiking spot"`, falling back to
  today's `"Hitchhiking spot at 52.30217, 13.01991"` when unnamed.
- `spot_description`: `_spot_description` returns `None` for a preview with no
  `rating`, so a named-but-unrated spot has a real title but no description.

That last point is what keeps the existing `noindex` rule intact: the template's
robots meta keys off `spot_description`, so emitting any sentence for a spot with no
ride data would turn ~30k thin pages indexable. A name alone does not make a spot
worth indexing.

## Out of scope

- Names in `spots.json`, marker hover tooltips, `rides_index.json`, or search.
- Any change to how spots are merged or anchored.
- Translating or localising names; Photon is queried with `lang=en` and OSM names are
  used verbatim.

## Testing

- **`spot_names.py` label building** — a pure function mapping Photon `properties` to
  a label, unit-tested against each cascade branch including the empty case.
- **Failure handling** — a mocked timeout writes no row; a mocked 200 with no usable
  fields writes a row with `name = NULL`.
- **`show.py` cascade** — a unit test over the resolver with synthetic inputs asserts
  the precedence order, in particular that an official hitchhiking spot beats a
  containing service area, and that a NULL `service_area.name` falls through to fuel.
- **Fuel tag preference** — `name` > `brand` > `operator`.
- **`_spot_preview`** — a per-spot file with a name but no rated ride still yields a
  preview carrying the name, and `_spot_description` does not raise on it.
- **Frontend** — verified in a browser (no headless browser on this host, per
  CLAUDE.md): a named spot shows the title, an unnamed one is visually unchanged, and
  opening a named spot then an unnamed one leaves no stale name.
- **End to end** — run `spot_names.py --dry-run --limit 20`, then `show --force`, then
  check `dist/rides/by-spot/52.30217_13.01991.json` contains
  `"name": "Raststätte Michendorf-Nord"`.
