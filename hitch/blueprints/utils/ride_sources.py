"""Where a ride came from, and what our users may do with it.

Not every ride on this map is ours. `ride_event` holds three kinds of row:

* rides logged here (`source` == ``THIS_NOSTR_SOURCE``),
* legacy datasets this project imported and republished to Nostr under its own key
  (hitchmap.com, hitchwiki.org),
* rides other platforms published straight to the relays under *their* key
  (triphopping.com, liftershalte.info).

Editing or claiming a ride republishes it as a kind-36820 event with the ride's original
`d` tag, signed with our ``NSEC``. Kind 36820 is parameterized-replaceable per
``(pubkey, kind, d)``, so that only *replaces* the ride when the original carried our
pubkey too — otherwise the "edit" lands on the relays as a second, competing event and
the next fetch upsert (also keyed on ``(pubkey, d)``) stores it as a second row, i.e. the
same ride twice on the map.

Hence the two conditions in `ride_is_replaceable`:

* **policy** — the source is one of ours. Someone who logged a ride on triphopping.com
  changes it there; we are not that platform's editor even if the hitchhiker is our user.
* **mechanics** — the stored event's pubkey is ours, so the replacement actually lands.

The two are separate on purpose: hitchmap.com rides exist under both our key (imported by
us) and a third party's, and only the first group can be rewritten.
"""

import os
from functools import lru_cache

from pynostr.key import PrivateKey

# What this deployment stamps on the rides it publishes. Default deliberately left as the
# placeholder from example.env: a fork that forgets to set it should be obvious in the
# data, not silently attribute its rides to maps.hitchwiki.org.
THIS_NOSTR_SOURCE = os.getenv("THIS_NOSTR_SOURCE", "yourdomain.com")

# Sources whose rides our users may edit and claim. Everything this project put on the
# relays itself: what we publish today, plus the historical bulk imports.
OUR_RIDE_SOURCES = frozenset(
    {
        THIS_NOSTR_SOURCE,
        "maps.hitchwiki.org",
        "hitchmap.com",
        "hitchwiki.org",
    }
)

# Other platforms' rides. Listed only so the split is documented in one place — anything
# not in OUR_RIDE_SOURCES is treated as foreign, including sources that appear later.
THIRD_PARTY_RIDE_SOURCES = frozenset(
    {
        "liftershalte.info",
        "triphopping.com",
    }
)


def ride_source(ride):
    """The platform a ride was recorded on.

    The standard's `source` field inside the event content is authoritative; the extracted
    column is only a fallback for rows whose content failed to parse.
    """
    return (ride.content or {}).get("source") or ride.source


@lru_cache(maxsize=1)
def our_pubkey_hex():
    """Hex pubkey of the key this app signs ride events with, or None if unconfigured.

    Cached: it is a secp256k1 derivation from a value that cannot change without a
    restart, and `ride_is_replaceable` runs once per ride card on a spot page.
    """
    nsec = os.getenv("NSEC")
    if not nsec:
        return None
    try:
        return PrivateKey.from_nsec(nsec).public_key.hex()
    except Exception:
        # A malformed key must not 500 every ride page — it just means nothing is editable.
        return None


def ride_is_replaceable(ride):
    """Whether republishing this ride under our key would replace it rather than fork it.

    Source and pubkey both matter — see the module docstring. The stored tags matter too:
    a republish reuses the event's `d` and `published_at` tags, and `post()` silently mints
    a fresh `d` when it can't find one, which would put a *second* copy of the ride on the
    map. Nothing in the table is missing them today; this is here so a malformed row is
    read-only rather than duplicated.
    """
    if ride_source(ride) not in OUR_RIDE_SOURCES:
        return False
    ours = our_pubkey_hex()
    if not ours or ride.pubkey != ours:
        return False
    tags = ride.tags or []
    tag_values = {t[0]: t[1] for t in tags if isinstance(t, (list, tuple)) and len(t) >= 2}
    return tag_values.get("d") == ride.d and "published_at" in tag_values
