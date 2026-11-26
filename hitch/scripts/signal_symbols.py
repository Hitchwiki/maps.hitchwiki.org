"""maps#732: the emoji after a review's wait time ("wait: 10 min 👍").

In Kazakhstan and Kyrgyzstan drivers are stopped with a downward hand wave, not a
thumb. The stored method stays ``thumb`` (filters and statistics are unchanged);
only the symbol shown in a review line becomes 🫳 there. Keep the country set
in sync with ``HAND_WAVE_COUNTRIES`` in static/map.js.

Split out of show.py so it can be imported and tested (show.py does all its work
at import time), same reason as spot_access_hint.py / spot_naming.py.
"""

HAND_WAVE_COUNTRIES = frozenset({"KZ", "KG"})

# Loose box around KZ + KG. Only rides inside it are reverse-geocoded, so the
# nightly build does not pay for a lookup on every ride in the world.
_HAND_WAVE_BOX = (39.0, 56.0, 46.0, 88.0)  # lat_min, lat_max, lon_min, lon_max

SYMBOLS = {"asking": "💬", "sign": "🪧", "thumb": "👍"}


def signal_symbols(approaches, hand_wave=False):
    """Comma-joined symbols for a ride's signal methods, or None if unknown."""
    if approaches is None or not isinstance(approaches, list):
        return None
    signals = []
    for approach in approaches:
        signals.extend(approach.get("methods", []) or [])
    symbols = dict(SYMBOLS, thumb="🫳") if hand_wave else SYMBOLS
    return ",".join(symbols.get(sig, sig) for sig in dict.fromkeys(signals))


def in_hand_wave_box(lat, lon):
    lat_min, lat_max, lon_min, lon_max = _HAND_WAVE_BOX
    try:
        return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max
    except TypeError:
        return False


def hand_wave_flags(lats, lons, search):
    """One bool per (lat, lon): is it in a hand-wave country?

    ``search`` is ``reverse_geocoder.search`` (injected so tests need no geodata).
    """
    flags = [False] * len(lats)
    idx = [i for i, (la, lo) in enumerate(zip(lats, lons)) if in_hand_wave_box(la, lo)]
    if idx:
        results = search([(lats[i], lons[i]) for i in idx])
        for i, r in zip(idx, results):
            flags[i] = r.get("cc") in HAND_WAVE_COUNTRIES
    return flags
