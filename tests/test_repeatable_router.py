"""Unit tests for the repeatable-routes routing engine.

These use tiny synthetic graphs (no dependency on the generated data file) so the
routing logic — walk/car legs, car switching between corridors, walking between
spots, and unreachable queries — is checked deterministically.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hitch" / "scripts"))

import repeatable_router as rr  # noqa: E402


def make_router(spots, trees, max_walk_km=2.0):
    return rr.RepeatableRouter({"spots": spots, "trees": trees}, max_walk_km=max_walk_km)


def test_straight_corridor_walk_car_walk():
    # Three spots roughly west->east; one ride corridor A->B->C.
    spots = [[50.0, 14.0], [50.0, 14.5], [50.0, 15.0]]
    trees = [{"s": 0, "nodes": [[1, -1, 3], [2, 0, 3]]}]
    router = make_router(spots, trees)

    # Origin just north of A, destination just north of C.
    res = router.route((50.005, 14.0), (50.005, 15.0))
    assert res["found"]
    modes = [leg["mode"] for leg in res["legs"]]
    assert modes == ["walk", "car", "walk"]
    # The single car leg spans the whole corridor (B collapsed into "via").
    assert res["num_car_legs"] == 1
    assert res["car_km"] > 60  # ~71 km great-circle * road factor


def test_car_switch_between_two_corridors_costs_a_wait():
    # Corridor 1: A->B (wait 10). Corridor 2 starts at B: B->C (wait 20). Reaching
    # C from A switches cars at the shared spot B, which is a new ride => new wait.
    spots = [[50.0, 14.0], [50.0, 14.5], [50.0, 15.0]]
    trees = [
        {"s": 0, "nodes": [[1, -1, 2, 10]]},  # A->B, wait 10
        {"s": 1, "nodes": [[2, -1, 2, 20]]},  # B->C, wait 20
    ]
    router = make_router(spots, trees)
    res = router.route((50.0, 14.0), (50.0, 15.0))
    assert res["found"]
    # Two distinct rides => two car legs and two waits (10 + 20).
    car_legs = [leg for leg in res["legs"] if leg["mode"] == "car"]
    assert len(car_legs) == 2
    assert res["wait_minutes"] == 30


def test_walk_between_nearby_spots():
    # Two corridors that don't share a spot but pass within walking distance:
    # A->B (corridor 1) and B'->C (corridor 2) where B and B' are ~0.5 km apart.
    spots = [
        [50.0, 14.0],  # 0 A
        [50.0, 14.5],  # 1 B
        [50.0045, 14.5],  # 2 B' (~0.5 km north of B)
        [50.0045, 15.0],  # 3 C
    ]
    trees = [
        {"s": 0, "nodes": [[1, -1, 2]]},  # A->B
        {"s": 2, "nodes": [[3, -1, 2]]},  # B'->C
    ]
    router = make_router(spots, trees)
    res = router.route((50.0, 14.0), (50.0045, 15.0))
    assert res["found"]
    modes = [leg["mode"] for leg in res["legs"]]
    # Expect: walk to A, car to B, walk B->B', car to C, walk to dest.
    assert modes.count("car") == 2
    assert "walk" in modes[1:-1]  # a walk between the two car legs


def test_directed_edges_no_reverse_travel():
    # Corridor only goes A->B. Travelling B->A by car must not be possible; with no
    # walk shortcut in range, the query is unreachable.
    spots = [[50.0, 14.0], [50.0, 15.0]]  # ~71 km apart, beyond walk range
    trees = [{"s": 0, "nodes": [[1, -1, 2]]}]
    router = make_router(spots, trees)
    res = router.route((50.0, 15.0), (50.0, 14.0))  # reversed
    assert not res["found"]


def test_unreachable_when_no_spot_in_walk_range():
    spots = [[50.0, 14.0], [50.0, 14.5]]
    trees = [{"s": 0, "nodes": [[1, -1, 2]]}]
    router = make_router(spots, trees, max_walk_km=1.0)
    # Origin 50 km away from any spot.
    res = router.route((51.0, 14.0), (50.0, 14.5))
    assert not res["found"]


def test_waiting_charged_once_per_boarding():
    # Corridor A->B->C with per-edge waits (4th node element). Riding through B in
    # one car must charge only the boarding wait at A, not B's wait too.
    spots = [[50.0, 14.0], [50.0, 14.5], [50.0, 15.0]]
    trees = [{"s": 0, "nodes": [[1, -1, 3, 20], [2, 0, 3, 99]]}]  # wait A->B=20, B->C=99
    router = make_router(spots, trees)
    res = router.route((50.0, 14.0), (50.0, 15.0))
    assert res["found"]
    # One contiguous car leg => one wait, and it's the boarding edge's (20), not 99.
    assert res["wait_minutes"] == 20
    car_leg = next(leg for leg in res["legs"] if leg["mode"] == "car")
    assert car_leg["wait_minutes"] == 20


def test_waiting_counts_each_separate_boarding():
    # Two corridors separated by a walk => two boardings => two waits summed.
    spots = [[50.0, 14.0], [50.0, 14.5], [50.0045, 14.5], [50.0045, 15.0]]
    trees = [
        {"s": 0, "nodes": [[1, -1, 2, 10]]},  # A->B, wait 10
        {"s": 2, "nodes": [[3, -1, 2, 15]]},  # B'->C, wait 15
    ]
    router = make_router(spots, trees)
    res = router.route((50.0, 14.0), (50.0045, 15.0))
    assert res["found"]
    assert res["wait_minutes"] == 25  # 10 + 15


def test_direct_walk_when_destination_is_close():
    spots = [[50.0, 14.0], [50.0, 14.5]]
    trees = [{"s": 0, "nodes": [[1, -1, 2]]}]
    router = make_router(spots, trees)
    # Destination ~0.1 km from origin: a plain walk beats any detour.
    res = router.route((50.0, 14.0), (50.001, 14.0))
    assert res["found"]
    assert [leg["mode"] for leg in res["legs"]] == ["walk"]
    assert res["car_km"] == 0
