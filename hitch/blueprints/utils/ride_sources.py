"""Where a ride came from, and what our users may do with it.

Not every ride on this map is ours. `ride_event` holds three kinds of row:

* rides logged here (`source` == ``THIS_NOSTR_SOURCE``),
* legacy datasets this project imported (hitchmap.com, hitchwiki.org, liftershalte.info),
* rides another platform published straight to the relays under *their* key
  (triphopping.com).

Editing or claiming a ride republishes it as a kind-36820 event with the ride's original
`d` tag, signed with our ``NSEC``. Kind 36820 is parameterized-replaceable per
``(pubkey, kind, d)``, so it only *replaces* the ride when the original carried the same
pubkey.

Hence the two conditions in `ride_is_replaceable`:

* **policy** — the source is one of ours. Someone who logged a ride on triphopping.com
  changes it there; we are not that platform's editor even if the hitchhiker is our user.
* **ownership** — the event was signed by a key of ours (`OUR_RIDE_PUBKEYS`). That is more
  than the key we publish with today: the bulk imports went out under an earlier key, and
  those rides are just as much ours to rewrite.

Rewriting a ride signed by one of the *older* keys cannot replace the original on the
relays — we don't hold that nsec, and NIP-09 only honours a deletion signed by the author,
so the pre-edit event is out there for good. `SupersededRideEvent` is how the old copy is
kept off this map: the coordinate is recorded on rewrite and both fetch scripts skip it,
which is what stops the weekly full re-fetch showing the ride twice.
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


# Keys this project has published rides under in the past but no longer signs with. The
# bulk imports (hitchmap.com, hitchwiki.org, liftershalte.info) went out under this one.
# Rides signed by it are ours to rewrite; see the module docstring for what that costs.
DEFAULT_IMPORT_PUBKEYS = ("d17ff51bfc32d49217e8cb5bfa558a5a78e6cbe3ea4d947acbc7f11ca5c5dbd5",)


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
    """Every Nostr key whose rides this project may rewrite: today's plus our old ones.

    Override the historical set with OUR_IMPORT_PUBKEYS (comma-separated hex) — a fork
    inherits neither our signing key nor our imports, and must not treat ours as its own.
    """
    raw = os.getenv("OUR_IMPORT_PUBKEYS")
    imported = [k.strip().lower() for k in raw.split(",")] if raw is not None else list(DEFAULT_IMPORT_PUBKEYS)
    return frozenset(k for k in [our_pubkey_hex(), *imported] if k)


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


def needs_supersede(ride):
    """Whether rewriting this ride leaves a stale copy behind that must be filtered out.

    True exactly when the ride is ours but was signed by an older key: the new event goes
    out under the current one, so it sits *beside* the original instead of replacing it.
    """
    return (ride.pubkey or "").lower() != our_pubkey_hex()
