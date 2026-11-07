"""Write per-degree tiles of OSM fuel / rest / service / motorway-junction nodes for the routing-gang page.

Input: a JSON list of [kind, lat, lon, name, extra] (the Overpass pull kept at .state/rg-osm-nodes.json in the
automation repo; place:* rows are ignored). Output: hitch/static/osm-stops/<floor lat>_<floor lon>.json, each a
list of [cls, lat, lon, name] with cls f=fuel, j=motorway_junction, s=services, r=rest_area.
Why: public Overpass answers in 36 s or not at all (EXP-1114); the page reads these static files instead.

    python3 scripts/build_osm_stop_tiles.py /path/to/rg-osm-nodes.json
"""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

CLS = {"fuel": "f", "motorway_junction": "j", "services": "s", "rest_area": "r"}
OUT = Path(__file__).resolve().parent.parent / "hitch" / "static" / "osm-stops"


def build(rows):
    tiles = defaultdict(list)
    for row in rows:
        c = CLS.get(row[0])
        if not c:
            continue
        lat, lon = float(row[1]), float(row[2])
        tiles[(math.floor(lat), math.floor(lon))].append([c, round(lat, 5), round(lon, 5), (row[3] or "")[:60]])
    return tiles


def main(path):
    tiles = build(json.loads(Path(path).read_text()))
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for (la, lo), items in tiles.items():
        items.sort(key=lambda x: (x[1], x[2]))
        (OUT / f"{la}_{lo}.json").write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(tiles)} tiles, {sum(len(v) for v in tiles.values())} stops")


if __name__ == "__main__":
    main(sys.argv[1])
