"""Where a ride came from, and what our users may do with it.

Not every ride on this map is ours. `ride_event` holds three kinds of row:

* rides logged here (`source` == ``THIS_NOSTR_SOURCE``),
* legacy datasets this project imported (hitchmap.com, hitchwiki.org, liftershalte.info),
* rides another platform published straight to the relays under *their* key
  (triphopping.com).

Editing or claiming a ride republishes it as a kind-36820 event with the ride's original
`d` tag, signed with our ``NSEC``. Kind 36820 is parameterized-replaceable per
``(pubkey, kind, d)``, so it only *replaces* the ride when the original carried the same
pubkey — otherwise the rewrite lands on the relays as a second, competing event and the
next fetch upsert (also keyed on ``(pubkey, d)``) stores it as a second row, i.e. the same
ride twice on the map. There is no way to withdraw the original either: NIP-09 honours
only a deletion signed by the author.

Hence the two conditions in `ride_is_replaceable`:

* **policy** — the source is one of ours. Someone who logged a ride on triphopping.com
  changes it there; we are not that platform's editor even if the hitchhiker is our user.
* **ownership** — the event was signed by a key we hold the nsec for (`our_ride_pubkeys`).
  Holding the nsec is the whole point: it is what makes a replacement possible rather than
  a fork. A key we merely recognise is not enough.

The two are separate on purpose: rides carrying one of our source names exist under keys
we do not hold — the bulk imports went out under a key whose nsec we no longer have — and
those stay read-only.
"""

import os
from functools import lru_cache

from pynostr.key import PrivateKey

# What this deployment stamps on the rides it publishes. Default deliberately left as the
# placeholder from example.env: a fork that forgets to set it should be obvious in the
# data, not silently attribute its rides to maps.hitchwiki.org.
THIS_NOSTR_SOURCE = os.getenv("THIS_NOSTR_SOURCE", "yourdomain.com")

# Sources whose rides our users may edit and claim. Everything this project took
# responsibility for: what we publish today, plus the historical bulk imports.
OUR_RIDE_SOURCES = frozenset(
    {
        THIS_NOSTR_SOURCE,
        "maps.hitchwiki.org",
        "hitchmap.com",
        "hitchwiki.org",
        "liftershalte.info",
    }
)

# Other platforms' rides. Listed only so the split is documented in one place — anything
# not in OUR_RIDE_SOURCES is treated as foreign, including sources that appear later.
THIRD_PARTY_RIDE_SOURCES = frozenset(
    {
        "triphopping.com",
    }
)


def ride_source(ride):
    """The platform a ride was recorded on.

    The standard's `source` field inside the event content is authoritative; the extracted
    column is only a fallback for rows whose content failed to parse.
    """
    return (ride.content or {}).get("source") or ride.source


def our_nsecs():
    """Every Nostr secret key this deployment holds, most important first.

    A list because more than one is conceivable — an old signing key whose nsec we still
    have would belong here — but today it is exactly ``NSEC``. Note that `post()` always
    signs with ``NSEC``, so adding a second entry also means teaching the poster to pick
    the key matching the ride being rewritten; until then a second entry would let a user
    "edit" a ride into a duplicate.
    """
    return [nsec for nsec in [os.getenv("NSEC")] if nsec]


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


@lru_cache(maxsize=1)
def our_ride_pubkeys():
    """Pubkeys of the keys we hold the nsec for — the events we can actually replace."""
    keys = set()
    for nsec in our_nsecs():
        try:
            keys.add(PrivateKey.from_nsec(nsec).public_key.hex())
        except Exception:
            # An unusable key contributes nothing; it must not take the whole page down.
            continue
    return frozenset(keys)


def ride_is_replaceable(ride):
    """Whether our users may rewrite this ride.

    Source and signing key both matter — see the module docstring. The stored tags matter
    too: a republish reuses the event's `d` and `published_at` tags, and `post()` silently
    mints a fresh `d` when it can't find one, which would put a *second* copy of the ride
    on the map. Nothing in the table is missing them today; this is here so a malformed row
    is read-only rather than duplicated.
    """
    if ride_source(ride) not in OUR_RIDE_SOURCES:
        return False
    if (ride.pubkey or "").lower() not in our_ride_pubkeys():
        return False
    tags = ride.tags or []
    tag_values = {t[0]: t[1] for t in tags if isinstance(t, (list, tuple)) and len(t) >= 2}
    return tag_values.get("d") == ride.d and "published_at" in tag_values
