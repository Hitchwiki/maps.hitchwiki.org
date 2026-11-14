import json

from hitch.blueprints.main import count_rides_last_7d


def test_counts_only_maps_rides_in_window(tmp_path):
    now = 1_000_000_000_000
    day = 86_400_000
    rows = [
        {"id": "maps.hitchwiki.org-a", "t": now - day},
        {"id": "maps.hitchwiki.org-b", "t": now - 8 * day},
        {"id": "liftershalte.info-c", "t": now - day},
        {"id": "maps.hitchwiki.org-d", "t": None},
        {"id": "maps.hitchwiki.org-e", "t": now - 6 * day},
    ]
    p = tmp_path / "rides_index.json"
    p.write_text(json.dumps(rows))
    assert count_rides_last_7d(str(p), now) == 2
