"""IDEAS #1353: the builder reports an edge's wait as the median of its rides, not the mean."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hitch", "scripts"))
import build_ride_routes as b  # noqa: E402


def test_edge_wait_is_median():
    rides = [
        {"routed": True, "start_spot_id": "a", "passed": [("b", 0, 0)], "wait": w}
        for w in (5, 10, 90)
    ]
    trees = b.build_repeatable_trees(rides, {"a": {}, "b": {}}, min_support=1)
    assert trees[0]["nodes"][0][3] == 10
