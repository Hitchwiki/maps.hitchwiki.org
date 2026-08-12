"""Scalar ride facts shared by /ride/<d_tag> and /pending_rides.json."""

from types import SimpleNamespace

from hitch.blueprints.utils.ride_facts import (
    haversine_km,
    hitchhiker_name,
    is_informative,
    ride_map_entry,
    spot_id_for,
    stop_facts,
)
from hitch.helpers import haversine_np


def _stops(with_destination=True):
    stops = [
        {
            "location": {"latitude": 51.08170, "longitude": 13.73629},
            "departure_time": "2026-07-02T14:00",
            "waiting_duration": "PT12M",
        }
    ]
    if with_destination:
        stops.append(
            {
                "location": {"latitude": 52.51739, "longitude": 13.39513},
                "arrival_time": "2026-07-02T16:30",
            }
        )
    return stops


class TestStopFacts:
    def test_reads_both_ends_of_the_ride(self):
        facts = stop_facts(_stops())
        assert facts["pickup_lat"] == 51.08170
        assert facts["pickup_lon"] == 13.73629
        assert facts["dest_lat"] == 52.51739
        assert facts["dest_lon"] == 13.39513
        assert facts["departure_time"] == "2026-07-02T14:00"
        assert facts["arrival_time"] == "2026-07-02T16:30"
        assert facts["waiting_minutes"] == 12

    def test_a_ride_with_no_destination_has_no_second_stop(self):
        facts = stop_facts(_stops(with_destination=False))
        assert facts["pickup_lat"] == 51.08170
        assert facts["dest_lat"] is None
        assert facts["dest_lon"] is None
        assert facts["arrival_time"] is None

    def test_empty_and_malformed_stops_yield_all_none(self):
        for stops in ([], None, "not a list", [{}]):
            facts = stop_facts(stops)
            assert facts["pickup_lat"] is None
            assert facts["waiting_minutes"] is None

    def test_a_waiting_duration_we_do_not_understand_is_dropped_not_guessed(self):
        # Anything other than the PT<n>M our own form writes (e.g. an hours-based
        # duration from a foreign source) must read as "unknown", never as a number.
        stops = _stops()
        stops[0]["waiting_duration"] = "PT2H30M"
        assert stop_facts(stops)["waiting_minutes"] is None


class TestHaversine:
    def test_known_distance(self):
        # Dresden -> Berlin, ~166 km.
        assert 160 < haversine_km(51.08170, 13.73629, 52.51739, 13.39513) < 172

    def test_missing_endpoint_is_not_a_distance(self):
        assert haversine_km(51.0, 13.0, None, 13.4) is None


class TestHitchhikerName:
    def test_first_named_hitchhiker_wins(self):
        assert hitchhiker_name([{"nickname": "kim"}, {"nickname": "sam"}]) == "kim"

    def test_blank_and_missing_names_read_as_anonymous(self):
        assert hitchhiker_name([{"nickname": "  "}]) == "Anonymous"
        assert hitchhiker_name([{}]) == "Anonymous"
        assert hitchhiker_name([]) == "Anonymous"
        assert hitchhiker_name(None) == "Anonymous"


class TestIsInformative:
    def test_anonymous_rating_only_rides_are_not_informative(self):
        # show.py drops exactly these from every detail view, so surfacing one as
        # pending would show a ride that vanishes at the next cron run.
        assert is_informative("Anonymous", None, None) is False
        assert is_informative("Anonymous", "   ", None) is False

    def test_any_of_a_name_a_comment_or_a_wait_is_enough(self):
        assert is_informative("kim", None, None) is True
        assert is_informative("Anonymous", "long wait but a great driver", None) is True
        assert is_informative("Anonymous", None, 12) is True


class TestSpotId:
    def test_matches_the_five_decimal_frontend_format(self):
        assert spot_id_for(51.0817012, 13.7362899) == "51.08170_13.73629"
        assert spot_id_for(51, 13) == "51.00000_13.00000"
        assert spot_id_for(-8.5, -34.9) == "-8.50000_-34.90000"


class TestRideMapEntry:
    def _ride(self, **overrides):
        fields = dict(
            d="maps.hitchwiki.org-abc",
            stops=_stops(),
            hitchhikers=[{"nickname": "kim"}],
            comment="great ride",
            rating=4,
            submission_time="2026-07-02T16:35:00",
            # The spot pane filters on these two, so they travel with a pending ride.
            mode_of_transportation=None,
            signals=None,
            # A give-up: its last stop is a planned destination, so the entry must carry
            # neither a destination nor a distance.
            no_ride=False,
        )
        fields.update(overrides)
        return SimpleNamespace(**fields)

    def test_carries_everything_a_marker_and_a_ride_card_need(self):
        entry = ride_map_entry(self._ride())
        assert entry["id"] == "maps.hitchwiki.org-abc"
        assert entry["spot_id"] == "51.08170_13.73629"
        assert entry["lat"] == 51.08170
        assert entry["lon"] == 13.73629
        assert entry["dest_lat"] == 52.51739
        assert entry["rating"] == 4
        assert entry["wait"] == 12
        # show.py's map distance is the haversine_np road-distance estimate (great-circle
        # x 1.25 by default), not the ~166 km straight-line figure the ride page shows —
        # ~166 * 1.25 ~= 208.
        assert 200 < entry["distance"] < 216
        assert entry["comment"] == "great ride"
        assert entry["hitchhiker_name"] == "kim"
        assert entry["submission_time"] == "2026-07-02T16:35:00"
        assert entry["ride_datetime"] == "2026-07-02T14:00"
        assert entry["arrival_datetime"] == "2026-07-02T16:30"

    def test_a_give_up_reports_no_destination_and_no_distance(self):
        # Its second stop is where the hitchhiker meant to go, not where a car took them.
        # show.py drops both for a give-up, and this entry stands in for a ride until
        # show.py catches up — so the line and the distance must not appear and then
        # vanish ten minutes later.
        entry = ride_map_entry(self._ride(no_ride=True))
        assert entry["dest_lat"] is None
        assert entry["dest_lon"] is None
        assert entry["distance"] is None
        # The spot itself is still a real place someone stood, so the marker survives.
        assert entry["spot_id"] == "51.08170_13.73629"

    def test_distance_matches_haversine_np_exactly(self):
        # The property that stops ride_map_entry's distance from drifting away from
        # show.py's: they must be computed with the literal same function.
        entry = ride_map_entry(self._ride())
        expected = float(haversine_np(51.08170, 13.73629, 52.51739, 13.39513))
        assert entry["distance"] == round(expected, 1)

    def test_photos_ride_along_so_the_spot_strip_does_not_lag_the_ride_card(self):
        # A photo uploaded minutes ago is not in the per-spot files yet, so the pending
        # entry has to carry it or the strip would trail the card by a show.py cycle.
        entry = ride_map_entry(self._ride(), ["/ride-images/2026/07/a.jpg"])
        assert entry["images"] == ["/ride-images/2026/07/a.jpg"]

    def test_a_ride_with_no_photos_ships_no_images_key(self):
        # Matching the per-spot files: an empty list on every entry is payload for a
        # field almost no ride has.
        assert "images" not in ride_map_entry(self._ride())
        assert "images" not in ride_map_entry(self._ride(), [])

    def test_the_vehicle_and_signal_the_spot_pane_filters_on_travel_along(self):
        # Without them the pane could not apply a vehicle/signal filter to a ride
        # show.py has not picked up yet, and that one ride would show through a filter
        # that excludes it.
        entry = ride_map_entry(
            self._ride(
                mode_of_transportation={"kind": "truck"},
                signals=[{"methods": ["thumb", "sign"]}, {"methods": ["thumb"]}],
            )
        )
        assert entry["vehicle_kind"] == "truck"
        # Deduplicated in order of first appearance, like show.py's column.
        assert entry["signal_methods"] == ["thumb", "sign"]

    def test_an_unrecorded_vehicle_or_signal_is_omitted_not_null(self):
        # Same convention as images above, and the one map.js reads: a key that isn't
        # there means "not recorded", so nulls would be payload for nothing.
        entry = ride_map_entry(self._ride())
        assert "vehicle_kind" not in entry
        assert "signal_methods" not in entry
        # Malformed values (a bare string where the standard has an object, an approach
        # with no methods) read as not recorded rather than raising.
        entry = ride_map_entry(self._ride(mode_of_transportation="car", signals=[{"methods": []}, {}]))
        assert "vehicle_kind" not in entry
        assert "signal_methods" not in entry

    def test_a_ride_with_no_pickup_coordinates_cannot_be_placed(self):
        assert ride_map_entry(self._ride(stops=[])) is None

    def test_a_low_value_ride_is_withheld(self):
        # It would appear for ten minutes and then be dropped by show.py.
        # Note: _stops() always sets a waiting_duration on the first stop, which alone
        # makes a ride informative, so this case needs a stop list with no wait at all.
        stops = [{"location": {"latitude": 51.08170, "longitude": 13.73629}, "departure_time": "2026-07-02T14:00"}]
        ride = self._ride(hitchhikers=[], comment=None, stops=stops)
        assert ride_map_entry(ride) is None
