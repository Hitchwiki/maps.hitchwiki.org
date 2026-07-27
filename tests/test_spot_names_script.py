"""The spot_name cache: which spots get geocoded, and what a failure is allowed to store."""

import json
import sqlite3

import pytest
import requests

from hitch.scripts.spot_names import ensure_table, geocode, load_spots, pending, resolve_pending


def photon_response(props):
    """A minimal stand-in for a Photon reverse response."""

    class Response:
        @staticmethod
        def raise_for_status():
            pass

        @staticmethod
        def json():
            return {"features": [{"properties": props}] if props is not None else []}

    return Response


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    ensure_table(connection)
    yield connection
    connection.close()


class TestLoadSpots:
    def test_derives_the_spot_id_the_frontend_derives(self, tmp_path):
        # Must match generate_spot_id / the map's `lat.toFixed(5)_lon.toFixed(5)`,
        # or the name is cached under an id no per-spot file will ever look up.
        path = tmp_path / "spots.json"
        path.write_text(json.dumps([{"lat": 52.30217, "lon": 13.01991, "rating": 4.0}]))
        assert load_spots(path) == [("52.30217_13.01991", 52.30217, 13.01991)]

    def test_rounds_to_five_decimals(self, tmp_path):
        path = tmp_path / "spots.json"
        path.write_text(json.dumps([{"lat": 52.3021712, "lon": 13.0199149}]))
        assert load_spots(path)[0][0] == "52.30217_13.01991"

    def test_skips_entries_without_coordinates(self, tmp_path):
        path = tmp_path / "spots.json"
        path.write_text(json.dumps([{"rating": 4.0}, {"lat": 1.0, "lon": 2.0}]))
        assert load_spots(path) == [("1.00000_2.00000", 1.0, 2.0)]


class TestGeocode:
    def test_returns_the_label_from_a_successful_response(self):
        answered, name = geocode(52.3, 13.0, get=lambda *a, **kw: photon_response({"street": "An der A10", "city": "Michendorf"}))
        assert (answered, name) == (True, "An der A10, Michendorf")

    def test_an_answer_with_nothing_usable_is_still_an_answer(self):
        answered, name = geocode(52.3, 13.0, get=lambda *a, **kw: photon_response({}))
        assert (answered, name) == (True, None)

    def test_an_empty_feature_list_is_still_an_answer(self):
        answered, name = geocode(52.3, 13.0, get=lambda *a, **kw: photon_response(None))
        assert (answered, name) == (True, None)

    def test_a_network_failure_is_not_an_answer(self):
        def boom(*args, **kwargs):
            raise requests.Timeout("too slow")

        assert geocode(52.3, 13.0, get=boom) == (False, None)


class TestResolvePending:
    def test_stores_the_resolved_name(self, conn):
        spots = [("52.30217_13.01991", 52.30217, 13.01991)]
        resolve_pending(conn, spots, get=lambda *a, **kw: photon_response({"city": "Michendorf"}), delay=0)
        assert conn.execute("select spot_id, name from spot_name").fetchall() == [("52.30217_13.01991", "Michendorf")]

    def test_an_unnameable_spot_is_stored_as_null_and_never_retried(self, conn):
        # Photon answered and had nothing; re-asking every night would waste the budget
        # that new spots need.
        spots = [("1.00000_2.00000", 1.0, 2.0)]
        resolve_pending(conn, spots, get=lambda *a, **kw: photon_response({}), delay=0)
        assert conn.execute("select name from spot_name").fetchall() == [(None,)]
        assert pending(conn, spots) == []

    def test_a_network_failure_stores_nothing_and_stays_pending(self, conn):
        # Otherwise a five-minute outage would permanently mark thousands of spots
        # "unnameable" with no way to notice.
        def boom(*args, **kwargs):
            raise requests.ConnectionError("relay down")

        spots = [("1.00000_2.00000", 1.0, 2.0)]
        resolve_pending(conn, spots, get=boom, delay=0)
        assert conn.execute("select count(*) from spot_name").fetchone() == (0,)
        assert pending(conn, spots) == spots

    def test_limit_caps_the_run(self, conn):
        spots = [(f"{i}.00000_2.00000", float(i), 2.0) for i in range(5)]
        resolve_pending(conn, spots, get=lambda *a, **kw: photon_response({"city": "X"}), delay=0, limit=2)
        assert conn.execute("select count(*) from spot_name").fetchone() == (2,)

    def test_limit_zero_means_unlimited(self, conn):
        spots = [(f"{i}.00000_2.00000", float(i), 2.0) for i in range(5)]
        resolve_pending(conn, spots, get=lambda *a, **kw: photon_response({"city": "X"}), delay=0, limit=0)
        assert conn.execute("select count(*) from spot_name").fetchone() == (5,)

    def test_dry_run_writes_nothing(self, conn):
        spots = [("1.00000_2.00000", 1.0, 2.0)]
        resolve_pending(conn, spots, get=lambda *a, **kw: photon_response({"city": "X"}), delay=0, dry_run=True)
        assert conn.execute("select count(*) from spot_name").fetchone() == (0,)

    def test_already_resolved_spots_are_not_re_requested(self, conn):
        spots = [("1.00000_2.00000", 1.0, 2.0)]
        resolve_pending(conn, spots, get=lambda *a, **kw: photon_response({"city": "X"}), delay=0)

        def fail_if_called(*args, **kwargs):
            raise AssertionError("re-requested a spot already in the cache")

        resolve_pending(conn, spots, get=fail_if_called, delay=0)
        assert conn.execute("select name from spot_name").fetchall() == [("X",)]
