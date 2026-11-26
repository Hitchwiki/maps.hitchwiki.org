"""maps#732: review lines in Kazakhstan/Kyrgyzstan show 🫳, not 👍."""

import math

from hitch.scripts.signal_symbols import hand_wave_flags, signal_symbols


def test_thumb_is_thumbs_up_by_default():
    assert signal_symbols([{"methods": ["thumb"]}]) == "👍"


def test_thumb_is_hand_wave_in_hand_wave_country():
    assert signal_symbols([{"methods": ["thumb", "sign"]}], hand_wave=True) == "🫳,🪧"


def test_other_methods_unchanged_and_deduplicated():
    assert signal_symbols([{"methods": ["sign"]}, {"methods": ["sign", "asking"]}], hand_wave=True) == "🪧,💬"


def test_no_signals():
    assert signal_symbols(None) is None
    assert signal_symbols(float("nan")) is None


def test_flags_only_geocode_inside_box():
    calls = []

    def fake_search(points):
        calls.append(points)
        return [{"cc": "KG"} if p[1] > 70 else {"cc": "RU"} for p in points]

    lats = [52.5, 42.87, 43.0, 51.0, math.nan]
    lons = [13.4, 74.6, 76.9 - 30, 60.0, 74.0]  # Berlin, Bishkek, Caspian, near Orenburg (RU), NaN
    flags = hand_wave_flags(lats, lons, fake_search)
    assert flags == [False, True, False, False, False]
    assert len(calls) == 1 and (52.5, 13.4) not in calls[0]


def test_flags_no_lookup_outside_box():
    def boom(points):
        raise AssertionError("should not be called")

    assert hand_wave_flags([48.1], [11.6], boom) == [False]
