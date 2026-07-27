"""Resolve a human-readable name for a hitchhiking spot.

A pure library, shared by `show.py` (which resolves a name per spot when it writes the
per-spot detail files) and `spot_names.py` (which reverse-geocodes the spots no OSM
feature can name). Kept out of `show.py` because that module does all of its work at
import time, so nothing defined there can be imported or tested on its own.

The cascade, first match wins:

    1. OSM `highway=hitchhiking` spot within 100 m
    2. the service-area polygon the spot was merged into
    3. OSM fuel station within 100 m
    4. OSM car-pooling spot within 100 m
    5. the cached reverse geocode ("<street>, <city>")

An official hitchhiking spot outranks the service area containing it: a name someone
chose for the *hitchhiking* feature describes the spot better than the name of the rest
area around it.
"""

# OSM tags that can stand in for a display name, most specific first. `brand` and
# `operator` matter for fuel: a great many stations carry no `name` at all, and "Shell"
# identifies the spot far better than the street it sits on.
NAME_TAGS = ("name", "brand", "operator")

# Photon reverse properties naming an administrative division, smallest first. Used only
# when the response carries neither a street nor a city.
DIVISION_KEYS = ("district", "locality", "county", "state")


def _clean(value):
    """A non-blank string, or None. OSM and Photon both emit whitespace-only values."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def osm_name_from_tags(tags):
    """Display name for an OSM feature, or None if its tags carry nothing usable."""
    if not tags:
        return None
    for key in NAME_TAGS:
        name = _clean(tags.get(key))
        if name:
            return name
    return None


def photon_label(props):
    """Label for a Photon reverse-geocode result, or None if it says nothing useful.

    Photon's own `name` property is deliberately ignored: it holds the nearest feature,
    which is as often an unrelated shop as it is the rest area we actually want. The
    street the hitchhiker stands on is predictable; `name` is not.
    """
    if not props:
        return None
    street = _clean(props.get("street"))
    city = _clean(props.get("city"))
    if street and city:
        return f"{street}, {city}"
    if street:
        return street
    if city:
        return city

    # Neither: name the place by its smallest administrative division, qualified by a
    # larger one so a "Straldzha" is not ambiguous across countries.
    divisions = []
    for key in DIVISION_KEYS:
        value = _clean(props.get(key))
        if value and value not in divisions:
            divisions.append(value)
    if divisions:
        return ", ".join(divisions[:2])
    return None


def resolve_spot_name(hitchhiking_tags, service_area_name, fuel_tags, car_pooling_tags, geocoded_name):
    """The spot's display name, or None when no source can name it.

    Every step falls through when its source exists but is unnamed — a spot merged into
    an unnamed service-area polygon, or matched to a fuel station with no name/brand/
    operator, must still get the next-best name rather than none at all.
    """
    return (
        osm_name_from_tags(hitchhiking_tags)
        or _clean(service_area_name)
        or osm_name_from_tags(fuel_tags)
        or osm_name_from_tags(car_pooling_tags)
        or _clean(geocoded_name)
    )
