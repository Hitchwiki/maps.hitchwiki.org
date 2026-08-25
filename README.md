
This project is deployed on the Hitchwiki server at the following locations:
* the Map `maps.hitchwiki.org` at`/var/www/maps.hitchwiki.org`
* the Nostr relay used as a the central data store `wss://relay.maps.hitchwiki.org` at `/var/www/relay.maps.hitchwiki.org`

---

<!-- PROJECT SHIELDS -->
<!--
*** Markdown "reference style" links for readability.
*** Reference links are enclosed in brackets [ ] instead of parentheses ( ).
*** See the bottom of this document for the declaration of the reference variables
*** for contributors-url, forks-url, etc. This is an optional, concise syntax you may use.
*** https://www.markdownguide.org/basic-syntax/#reference-style-links
-->
[![Contributors][contributors-shield]][contributors-url]
[![Issues][issues-shield]][issues-url]
[![Unlicense License][license-shield]][license-url]

<!-- ABOUT THE PROJECT -->
<div align="center">
  <h3 align="center">Hitchhiking Map</h3>
  <h2 align="center"><a href="https://maps.hitchwiki.org/">maps.hitchwiki.org</a></h2>
  <p align="center">
    The map to hitchhiking the world.
    <br />
    <br />
    <a href="https://github.com/Hitchwiki/maps.hitchwiki.org/issues/new?labels=bug&template=bug_report.md">Report Bug</a>
    &middot;
    <a href="https://github.com/Hitchwiki/maps.hitchwiki.org/issues/new?labels=enhancement&template=feature-request---.md">Request Feature</a>
  </p>
</div>

## About The Project
This project is the continuation of a similar map on Hitchwiki that was present until 2022. Read [this paper](https://arxiv.org/pdf/2506.21946) to learn more about the history.

This project embraces Nostr - hitchhiking rides that are submitted are published as Nostr event following the [data standard](https://github.com/Hitchwiki/hitchhiking-data-standard) in the first place. So events on Nostr relays become the single source of truth (database) for hitchhiking rides that also other apps (not only this one) can contribute to.

Join the conversation about a map for hitchhiking in our [Signal Chat](https://signal.group/#CjQKIFSj0oaPjMY_eB1uHfXEuxH459W6gtfEke0krGgTabZBEhB1ZK3YP53QSPBuviWzHO_F).

### History

This repository, [`Hitchwiki/maps.hitchwiki.org`](https://github.com/Hitchwiki/maps.hitchwiki.org), is a fork of [`hitchmap/hitchmap`](https://github.com/hitchmap/hitchmap).

## Accessing the data

Every ride submitted through maps.hitchwiki.org is published to the Nostr network
following the [hitchhiking data standard](https://github.com/Hitchwiki/hitchhiking-data-standard),
so the data is open for anyone to use. There are two supported ways to consume it:

### For researchers — download the full dataset

A snapshot of all rides is published on Hugging Face:

[**Hitchwiki/hitchhiking-rides-dataset**](https://huggingface.co/datasets/Hitchwiki/hitchhiking-rides-dataset)

- **Updated weekly** (Mondays) — see [`deploy/cron.sh`](deploy/cron.sh).
- Built by [`hitch/scripts/sync_hitchhiking_rides_dataset.py`](hitch/scripts/sync_hitchhiking_rides_dataset.py),
  which reads `dist/allPosts.json` (the Nostr ride events fetched by
  [`hitch/scripts/fetch_hitchhiking_events/`](hitch/scripts/fetch_hitchhiking_events)).
- One row per ride, sorted by `submission_time` descending (newest first; nulls last).

This is the simplest option when you just want a single, ready-to-analyze file.

### For other hitchhiking sites — sync rides continuously

If you run another hitchhiking platform and want to stay up to date, fetch rides
straight from the Nostr relays rather than downloading static snapshots. The
`fetch_hitchhiking_events` script does this and can filter by date and source,
so you can pull only recent rides or only those from a given app:

[**fetch_hitchhiking_events**](https://github.com/Hitchwiki/hitchhiking-data-standard/tree/main/nostr/fetch_hitchhiking_events)

See that script's README for setup and usage examples.

## Getting Started locally (Docker setup below)

Set up Python virtual environment, install requirements and download the latest database dump:

Works with Python 3.12.6

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
cp example.env .env
cp tests/hitchwiki_articles.json dist/hitchwiki_articles.json
```
And set the missing env variables and wiki bot passwords. If you do not have a Nostr key pair you can use the below snipped to create one:

```python
from pynostr.key import PrivateKey
private_key = PrivateKey()
print(f"Private Key (nsec): {private_key.bech32()}")
print(f"Public Key (npub):  {private_key.public_key.bech32()}")
```

Put file from `https://simplemaps.com/static/data/world-cities/basic/simplemaps_worldcities_basicv1.901.zip` into `dist/` as `worldcities.zip` but any `worldcities.csv` file with `city`, `country`, `population` column works.

### Deploy with Docker

```bash
# recommended for local testing
sudo docker compose up --build
# or to deploy for production
sudo docker compose up --build -d --remove-orphans

# connect to the container
sudo docker exec -it hitchhiking-map /bin/bash  

# if down just:
sudo docker restart hitchhiking-map    

sudo docker stop hitchhiking-map 
sudo docker rm hitchhiking-map 
```

#### Redeploying after changes

Pick the lightest option that covers the files you changed. The host's `./hitch/static`, `./hitch/templates`, `./dist`, `./db`, and `./logs` are bind-mounted into the container (see `docker-compose.yml`), so changes to those files are visible inside the container immediately — only Flask's in-process caches need busting. Anything else lives in the image and requires a rebuild.

| Changed files | What to run | Why |
| --- | --- | --- |
| `hitch/static/**` (CSS, JS, images), `dist/**` (generated JSON) | nothing — just hard-refresh the browser (or bump the asset URL to bypass the browser cache) | Flask reads static files from disk per request; the bind mount means the new bytes are already served. |
| `hitch/templates/**` (Jinja `.html`) | `sudo docker restart hitchhiking-map` | Files are bind-mounted, but Jinja caches compiled templates in memory — a process restart drops the cache. No image rebuild needed. |
| Python source: `hitch/**/*.py`, `settings.py`, `hitch/scripts/**`, `hitch/scripts/fetch_hitchhiking_events/**` (TS), `requirements.txt`, `Dockerfile`, `deploy/run.sh`, `deploy/cron.sh` | `sudo docker compose up --build -d` | These are baked into the image at build time (not bind-mounted), so the running container keeps the old copy until the image is rebuilt and the container recreated. |
| `docker-compose.yml`, `.env` | `sudo docker compose up -d` (add `--build` if image contents also changed) | Compose recreates the container so new env vars / volume / port settings take effect. A plain `docker restart` keeps the old container config. |
| `db/*.sqlite` schema (new column added to a model) | run the manual `ALTER TABLE` against the prod DB *before* rebuilding — see `CLAUDE.md` → "Database migrations" | There is no migration framework; `flask init` won't add columns to existing tables. |

#### Serving with Apache

In order to run the project continuously, use `deploy/cron.sh` to set up corresponding cronjobs to update the views and `deploy/apache.conf` as a basic NGINX configuration.

```shell
sudo cp deploy/apache.conf /etc/apache2/sites-available/25-hwmaptest.conf
```

```shell
# install the following
sudo a2enmod proxy
sudo a2enmod proxy_http
sudo a2enmod headers

# to start the deployment
sudo apachectl configtest
sudo systemctl reload apache2
```

### Google search cosole
To enable it put the verification file like `googlexxx.html` into `dist/`.

## Data
If you find the data collected and provided by maps.hitchwiki.org helpful, feel free to cite it using:
```
@misc{hitchhiking,
author = {Till Wenke},
title = {Dataset of Hitchhiking Trips},
year = {2025},
url = {https://maps.hitchwiki.org},
}
```

### Other applications using our data

We are aware of the following applications making downstream usage of data collected under this or its predecessor project, we expect them to use correct attribution and licensing:

- hitchmap.com
- hitchr.world

## License

The software provided in this repository is licensed under AGPL 3.0. The Hitchwiki Maps database is licensed under the [ODbL](https://opendatacommons.org/licenses/odbl/1-0/), the license used by OpenStreetMap.

The ODbL covers the database (the collection of spots and rides), but not the individual contents inside it (see [ODbL §2.4](https://opendatacommons.org/licenses/odbl/1-0/)). The individual reviews users contribute — their free-text comments and the username they publish under — are separately licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Re-use the database as a whole under the ODbL; re-use individual reviews under CC BY-SA 4.0 with attribution.

<!-- MARKDOWN LINKS & IMAGES -->
<!-- https://www.markdownguide.org/basic-syntax/#reference-style-links -->
[contributors-shield]: https://img.shields.io/github/contributors/Hitchwiki/maps.hitchwiki.org.svg?style=for-the-badge
[contributors-url]: https://github.com/Hitchwiki/maps.hitchwiki.org/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/Hitchwiki/maps.hitchwiki.org.svg?style=for-the-badge
[forks-url]: https://github.com/Hitchwiki/maps.hitchwiki.org/network/members
[stars-shield]: https://img.shields.io/github/stars/Hitchwiki/maps.hitchwiki.org.svg?style=for-the-badge
[stars-url]: https://github.com/Hitchwiki/maps.hitchwiki.org/stargazers
[issues-shield]: https://img.shields.io/github/issues/Hitchwiki/maps.hitchwiki.org.svg?style=for-the-badge
[issues-url]: https://github.com/Hitchwiki/maps.hitchwiki.org/issues
[license-shield]: https://img.shields.io/github/license/Hitchwiki/maps.hitchwiki.org.svg?style=for-the-badge
[license-url]: https://github.com/Hitchwiki/maps.hitchwiki.org/blob/master/LICENSE.txt
[Flask]: https://img.shields.io/badge/flask-000000?style=for-the-badge&logo=flask&logoColor=white
[Flask-url]: https://flask.palletsprojects.com/en/stable/

# Development

How we want to work on Hirchwiki Maps is defined in GOVERNANCE.md and refined in CONTRIBUTING.md.

## Testing

Run the complete, deterministic test suite (Python API tests with coverage and
browser-independent JavaScript unit tests):

```bash
make test
```

To run one side while developing:

```bash
make test-python
make test-javascript
```

Tests marked `network` contact live Nostr relays, so they are excluded from
normal local and pull-request runs. Run them explicitly when checking relay
health:

```bash
python -m pytest tests/ -v -m network
```

Pull requests receive an updated coverage overview comment with Python and
JavaScript coverage percentages. The same report is available in the GitHub
Actions run summary.

## OpenStreetMap Integration

We use the [`highway=hitchhiking`](https://wiki.openstreetmap.org/wiki/Tag:highway=hitchhiking) OSM tag to bridge the gap between official, everyday hitchhiking spots and unofficial ones submitted by users. Rides submitted near an OSM-tagged spot are automatically linked to it, connecting community-reported experiences with officially mapped infrastructure.

### Grouping spots by OSM areas (one-off manual sync)

Spots that fall inside the same gas station / motorway service area or the same "road island" (the patch of land enclosed by the slip-roads of a junction) are the same physical hitchhiking spot even when the pins are tens of metres apart. `show.py` merges them into a single marker using two polygon tables built from OpenStreetMap:

- `service_area` — built by `sync_service_areas`
- `road_island` — built by `sync_road_islands`

These are **one-off jobs, not cron jobs.** They make thousands of Overpass calls and the data barely changes, so run them **manually** only when you want to (re)build the polygons — e.g. on first setup or occasionally as new spots accumulate:

```bash
# inside the container (or any env with the app + DB)
flask --app hitch generate sync_service_areas   # build/refresh service_area
flask --app hitch generate sync_road_islands    # build/refresh road_island (run after service areas)
```

Both are slow but **resumable**: they snapshot their work to `db/.<script>.snapshot.json` / `.progress.json`, commit incrementally, and a re-run picks up where an interrupted one left off. On successful completion those checkpoint files are deleted (their absence is how you know a run finished). Re-running never deletes existing rows, so it's safe to re-run anytime.

They query the standard public Overpass endpoint (`https://overpass-api.de/api/interpreter`) with polite throttling and HTTP 429 back-off; override `OVERPASS_BULK_URL` to point at a different/bulk instance if needed. After a sync, the next `show.py` run automatically uses the updated polygons.

## Routing

The map's route planner is powered by a graph built from real rides. For every ride with a destination, `build_ride_routes.py` fetches an OSRM driving route and records which other known start spots lie along it; corridors shared by multiple rides become the "repeatable" trees the frontend searches. It runs **daily at 2 AM via cron**, but you can rebuild it manually — **inside the container** (the host venv lacks `shapely`, so spot grouping would be skipped and routes would reference phantom spots):

```bash
# inside the container — full rebuild (never use --limit, it writes partial data)
sudo docker exec hitchhiking-map python3 /app/hitch/scripts/build_ride_routes.py --skip-detailed
```

This writes `dist/repeatable_routes.json` (+ `oneoff_routes.json`, `test_routes.json`). OSRM responses are cached in `dist/route_cache.jsonl`, so a rerun only fetches routes for rides added since last time.

### Enriching rides that have no destination

Many hitchwiki.org / hitchmap.com rides reach us with only a start point — no destination — which leaves them out of the routing graph. Two **occasional, manual batch jobs** (not cron) infer destinations for these and store them in the `derived_ride_location` table (keyed by the Nostr `d` tag, distinguished by a `kind` column). `show.py` and `build_ride_routes.py` then merge a derived destination onto any ride whose `stops` lack one. Both are standalone `python3` scripts; the prod DB is root-owned, so pass `--db` and run under `sudo`.

**1. Mine the destination from the ride's comment (LLM).** Some comments name the city the ride actually reached ("got a lift to Kayseri"). `extract_destinations.py` runs in three stages — a cheap regex prefilter, an LLM pass that decides which city (if any) each ride reached, and a geocode+store step (`kind=derived-comment-city`, `is_exact=0` — the coordinate is a city centre inferred from prose). The OpenAI key is read from `OPENAI_API_KEY` only, never written to disk:

```bash
# stage 1 — find no-destination rides whose comment mentions arriving somewhere
python3 hitch/scripts/extract_destinations.py prefilter

# stage 2 — LLM extracts the reached city per comment (needs the key)
OPENAI_API_KEY=sk-... python3 hitch/scripts/extract_destinations.py extract

# stage 3 — geocode the cities against dist/worldcities.csv and upsert
sudo python3 hitch/scripts/extract_destinations.py geocode-store --db db/hitchhiking-prod.sqlite
```

**2. Reconstruct chains of consecutively-logged rides.** When a named user logged a whole trip in one sitting — a run of their no-destination rides entered minutes apart whose starts march in one direction — the start of each ride is, in practice, the destination of the one before it. `derive_consecutive_destinations.py` finds those chains and stores each ride's destination as the next ride's logged start (`kind=derived-consecutive-ride`, `is_exact=1` — it's a real logged spot). It never overwrites a comment-derived row.

```bash
# preview the chains it would write (change nothing)
python3 hitch/scripts/derive_consecutive_destinations.py --db db/hitchhiking-prod.sqlite --dry-run

# write them
sudo python3 hitch/scripts/derive_consecutive_destinations.py --db db/hitchhiking-prod.sqlite
```

**After running either enrichment job, regenerate the map data and routing graph** so the new destinations take effect (both in the container):

```bash
sudo docker exec hitchhiking-map /usr/local/bin/flask --app hitch generate show --force
sudo docker exec hitchhiking-map python3 /app/hitch/scripts/build_ride_routes.py --skip-detailed
```
