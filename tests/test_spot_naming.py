"""Spot-name resolution: the OSM/geocoder cascade behind the spot pane title."""

from hitch.scripts.spot_naming import osm_name_from_tags, photon_label, resolve_spot_name


class TestPhotonLabel:
    """Photon reverse properties -> "street, city"-style label."""

    def test_street_and_city(self):
        assert photon_label({"street": "An der A10", "city": "Michendorf"}) == "An der A10, Michendorf"

    def test_street_without_city(self):
        assert photon_label({"street": "E45"}) == "E45"

    def test_city_without_street(self):
        assert photon_label({"city": "Ljungby"}) == "Ljungby"

    def test_falls_back_to_administrative_divisions(self):
        # No street and no city: name the place by its smallest division, qualified
        # by a larger one so "Straldzha" is not ambiguous across countries.
        assert photon_label({"district": "Straldzha", "state": "Yambol"}) == "Straldzha, Yambol"

    def test_single_administrative_division(self):
        assert photon_label({"state": "Yambol"}) == "Yambol"

    def test_does_not_repeat_an_identical_division(self):
        assert photon_label({"district": "Yambol", "state": "Yambol"}) == "Yambol"

    def test_ignores_the_nearest_poi(self):
        # Photon's `name` is the nearest feature, which is as often an unrelated shop
        # as it is the rest area we want. A street is predictable; `name` is not.
        assert photon_label({"name": "Döner Palast"}) is None

    def test_nothing_usable(self):
        assert photon_label({}) is None


class TestOsmNameFromTags:
    """OSM tags -> a display name, preferring the most specific tag."""

    def test_prefers_name(self):
        assert osm_name_from_tags({"name": "Michendorf Nord", "brand": "TotalEnergies"}) == "Michendorf Nord"

    def test_falls_back_to_brand(self):
        # An unnamed station of a known chain is still better identified as "Shell"
        # than by the street it sits on.
        assert osm_name_from_tags({"brand": "Shell", "operator": "Lothar Johann"}) == "Shell"

    def test_falls_back_to_operator(self):
        assert osm_name_from_tags({"operator": "Lothar Johann"}) == "Lothar Johann"

    def test_no_usable_tag(self):
        assert osm_name_from_tags({"amenity": "fuel"}) is None

    def test_no_tags(self):
        assert osm_name_from_tags(None) is None

    def test_blank_tag_is_not_a_name(self):
        assert osm_name_from_tags({"name": "   "}) is None


class TestResolveSpotName:
    """Precedence across the five sources."""

    def test_hitchhiking_spot_outranks_service_area(self):
        # A name someone chose for the *hitchhiking* feature describes the spot better
        # than the name of the rest area that happens to surround it.
        assert (
            resolve_spot_name(
                hitchhiking_tags={"name": "Autobahnauffahrt Ost"},
                service_area_name="Raststätte Michendorf-Nord",
                fuel_tags={"name": "Michendorf Nord"},
                car_pooling_tags=None,
                geocoded_name="An der A10, Michendorf",
            )
            == "Autobahnauffahrt Ost"
        )

    def test_service_area_outranks_fuel(self):
        assert (
            resolve_spot_name(
                hitchhiking_tags=None,
                service_area_name="Raststätte Michendorf-Nord",
                fuel_tags={"name": "Michendorf Nord"},
                car_pooling_tags=None,
                geocoded_name="An der A10, Michendorf",
            )
            == "Raststätte Michendorf-Nord"
        )

    def test_unnamed_service_area_falls_through_to_fuel(self):
        # 403 of 3657 service_area polygons have a NULL name; the spot is still merged
        # into that polygon, so it must fall through rather than end up unnamed.
        assert (
            resolve_spot_name(
                hitchhiking_tags=None,
                service_area_name=None,
                fuel_tags={"name": "Michendorf Nord"},
                car_pooling_tags=None,
                geocoded_name="An der A10, Michendorf",
            )
            == "Michendorf Nord"
        )

    def test_fuel_outranks_car_pooling(self):
        assert (
            resolve_spot_name(
                hitchhiking_tags=None,
                service_area_name=None,
                fuel_tags={"name": "Michendorf Nord"},
                car_pooling_tags={"name": "P+R Kaulsdorf"},
                geocoded_name=None,
            )
            == "Michendorf Nord"
        )

    def test_car_pooling_outranks_geocode(self):
        assert (
            resolve_spot_name(
                hitchhiking_tags=None,
                service_area_name=None,
                fuel_tags=None,
                car_pooling_tags={"name": "P+R Kaulsdorf"},
                geocoded_name="An der A10, Michendorf",
            )
            == "P+R Kaulsdorf"
        )

    def test_geocode_is_the_last_resort(self):
        assert (
            resolve_spot_name(
                hitchhiking_tags=None,
                service_area_name=None,
                fuel_tags=None,
                car_pooling_tags=None,
                geocoded_name="An der A10, Michendorf",
            )
            == "An der A10, Michendorf"
        )

    def test_untaggable_osm_feature_falls_through_to_geocode(self):
        # Matching a fuel station with no name/brand/operator must not shadow the
        # geocoded street the way a matched-but-unnamed feature otherwise would.
        assert (
            resolve_spot_name(
                hitchhiking_tags=None,
                service_area_name=None,
                fuel_tags={"amenity": "fuel"},
                car_pooling_tags=None,
                geocoded_name="An der A10, Michendorf",
            )
            == "An der A10, Michendorf"
        )

    def test_nothing_at_all(self):
        assert resolve_spot_name(None, None, None, None, None) is None
