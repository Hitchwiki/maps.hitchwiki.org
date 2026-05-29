# Analytics

Ad-hoc analytics scripts for the hitchhiking map. These are operational tools,
not part of the served app.

## Clicked spots map

`generate_clicked_spots_map.py` renders a high-resolution world map (6400×3200
px) with country borders and a 1 km circle around every hitchhiking spot whose
popup was opened on the map.

### How it works

Every time a user clicks a spot marker, the frontend lazily fetches
`GET /rides/by-spot/<lat>_<lon>.json` — the filename encodes the spot's
coordinates (see `hitch/scripts/show.py` → `generate_spot_id`, which formats
them as `f"{lat:.4f}_{lon:.4f}"`). The script reads these requests straight
from the production container's logs:

1. Runs `docker logs hitchhiking-map` via `subprocess` (no sudo needed).
2. A single regex extracts each click's **timestamp** and **coordinates**.
3. Aggregates clicks per spot and computes the time span the data covers.
4. Downloads + caches the Natural Earth 50m country borders (once).
5. Draws borders, a 1 km circle per spot, and a click-frequency-scaled marker.
6. Stamps the image with the log time range and generation time.

> ⚠️ Docker logs are **ephemeral and rotate**, so the map reflects only the
> logs currently retained by the container, not all-time history.

### Usage

```bash
# from the repo root, using the project venv (see CLAUDE.md)
.venv/bin/python analytics/generate_clicked_spots_map.py
```

Output: `analytics/clicked_spots_map.png`.

### Files

| File | Tracked | Notes |
|------|---------|-------|
| `generate_clicked_spots_map.py` | ✅ | The script |
| `README.md` | ✅ | This file |
| `.gitignore` | ✅ | Ignores the generated/cached files below |
| `clicked_spots_map.png` | 🚫 | Generated image |
| `clicked_spots.csv` | 🚫 | Click data cached from the logs |
| `ne_50m_admin_0_countries.geojson` | 🚫 | Cached Natural Earth borders |

### Requirements

`matplotlib` and `numpy` (plus `requests`) in the project `.venv`:

```bash
python3 -m venv .venv && .venv/bin/pip install matplotlib numpy requests
```
