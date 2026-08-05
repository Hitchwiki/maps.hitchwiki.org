"""The weekday every displayed ride date is prefixed with (hitch/translations/weekdays.py)."""

import datetime

import pytest

from hitch.translations import SUPPORTED_LANGUAGES
from hitch.translations.weekdays import (
    WEEKDAY_ABBR,
    WEEKDAY_NAMES,
    weekday_abbr,
    weekday_index,
    with_weekday,
)


def test_every_supported_language_has_seven_of_each():
    """A language added to SUPPORTED_LANGUAGES but not here would silently show English
    weekdays inside an otherwise translated page."""
    for lang in SUPPORTED_LANGUAGES:
        assert len(WEEKDAY_ABBR[lang]) == 7, lang
        assert len(WEEKDAY_NAMES[lang]) == 7, lang
        assert all(WEEKDAY_ABBR[lang]), lang
        assert all(WEEKDAY_NAMES[lang]), lang


def test_tables_are_monday_first():
    """Both tables are indexed by date.weekday(), so index 0 must be Monday."""
    assert WEEKDAY_ABBR["en"][0] == "Mon"
    assert WEEKDAY_NAMES["en"][6] == "Sunday"
    assert WEEKDAY_ABBR["de"][5] == "Sa."


@pytest.mark.parametrize(
    "value,expected",
    [
        # The two shapes real callers hand us: the ride card's stamp and RFC 9557.
        ("2026-08-01 11:32", 5),
        ("2026-08-01T11:32:00+02:00[Europe/Berlin]", 5),
        ("2026-08-01", 5),
        (datetime.date(2026, 8, 1), 5),
        (datetime.datetime(2026, 8, 1, 11, 32), 5),
        # Nothing to read a date out of -> no weekday, never a crash or a wrong day.
        ("", None),
        (None, None),
        ("not a date", None),
        ("2026-13-01", None),
        ("2026-02-30", None),
    ],
)
def test_weekday_index(value, expected):
    assert weekday_index(value) == expected


def test_weekday_abbr_is_localized():
    assert weekday_abbr("2026-08-01", "en") == "Sat"
    assert weekday_abbr("2026-08-01", "de") == "Sa."
    assert weekday_abbr("2026-08-01", "ja") == "土"
    # A language we don't carry falls back to English rather than raising.
    assert weekday_abbr("2026-08-01", "xx") == "Sat"


def test_with_weekday_prepends_and_passes_junk_through():
    assert with_weekday("2026-08-01 11:32", "en") == "Sat 2026-08-01 11:32"
    assert with_weekday("2026-08-01 11:32", "ru") == "сб 2026-08-01 11:32"
    # A card whose ride has no date must render as before, not as " " or "None".
    assert with_weekday("", "en") == ""
    assert with_weekday(None, "en") == ""
    assert with_weekday("--:--:--", "en") == "--:--:--"


def test_the_offset_never_moves_the_day():
    """Only the leading date is read.

    The stamp is already the ride's own local wall-clock time, so a late-evening ride
    with a +02:00 offset must stay on the day the hitchhiker was standing there, not be
    dragged onto the previous UTC day.
    """
    assert with_weekday("2026-08-01T00:30:00+02:00", "en") == "Sat 2026-08-01T00:30:00+02:00"
    assert with_weekday("2026-08-01T23:45:00-05:00", "en") == "Sat 2026-08-01T23:45:00-05:00"
