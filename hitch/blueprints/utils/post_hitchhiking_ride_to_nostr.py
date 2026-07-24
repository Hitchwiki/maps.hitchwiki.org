"""
Class to allow posting hitchhiking rides in the standardized format to Nostr.
"""

import ast
import json
import os
import time
import uuid
from pathlib import Path

import geohash2
from pynostr.event import Event
from pynostr.key import PrivateKey
from pynostr.relay_manager import RelayManager

from hitch.blueprints.utils.hitchhiking_data_standard_pydantic_model import HitchhikingRecord

NSEC = os.getenv("NSEC")
RELAYS = ast.literal_eval(os.getenv("RELAYS"))

# Mirror every signed event we publish into dist/temporary.json so we have a local
# record independent of whether the relay accepted it / fetch_nostr has run yet.
TEMPORARY_EVENTS_FILE = Path(__file__).resolve().parents[3] / "dist" / "temporary.json"


def build_ride_d_tag(source: str, tags: list | None, client_d_tag: str | None) -> str:
    """Decide a ride event's `d` tag.

    Precedence (why): an edit passes the original `tags` so we reuse its `d` (same ride,
    new version); a new ride from the offline outbox passes a client-generated
    `client_d_tag` so retries reuse it and REPLACE the event instead of duplicating it
    (ride events are kind 36820, parameterized replaceable). The `source` prefix stays
    server-authoritative — the client only supplies the bare id. Otherwise mint a uuid.
    """
    # An edit passes the original tags, but tolerate an empty/malformed list (no `d`
    # entry) by falling through instead of raising StopIteration and breaking the post.
    if tags is not None:
        existing_d = next((tag[1] for tag in tags if tag[0] == "d"), None)
        if existing_d is not None:
            return existing_d
    if client_d_tag:
        return f"{source}-{client_d_tag}"
    return f"{source}-{uuid.uuid4()}"


def _append_event_to_temporary_json(event: Event) -> None:
    try:
        existing = json.loads(TEMPORARY_EVENTS_FILE.read_text()) if TEMPORARY_EVENTS_FILE.exists() else []
        if not isinstance(existing, list):
            existing = []
    except (OSError, json.JSONDecodeError):
        existing = []
    existing.append(event.to_dict())
    TEMPORARY_EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TEMPORARY_EVENTS_FILE.write_text(json.dumps(existing, indent=2))


class HitchhikingDataStandardToNostrPoster:
    def __init__(self):
        private_key_obj = PrivateKey.from_nsec(NSEC)
        self.private_key_hex = private_key_obj.hex()
        # Nostr requires the event's pubkey to be 64-char lowercase hex; bech32 npub
        # produces an event whose id/signature won't validate and the relay silently rejects it.
        self.pubkey_hex = private_key_obj.public_key.hex()
        self.npub = private_key_obj.public_key.bech32()
        print(f"Posting as npub {self.npub}")

        # Initialize the relay manager
        self.relay_manager = RelayManager(timeout=5)
        for relay in RELAYS:
            self.relay_manager.add_relay(relay)

        self.event_kind = int(os.getenv("NOSTR_EVENT_KIND"))

    def post(self, ride_record: HitchhikingRecord, tags: list = None, d_tag: str = None) -> str:
        """Post a ride in the standardized format to Nostr and return the d tag.

        Args:
            ride_record (HitchhikingRecord): The ride record to post.
            tags (list | None): A list of tags to include in the post.
                Used when updating an existing post where tags stay the same.
            d_tag (str | None): A client-supplied bare id for a NEW ride (offline outbox).
                Reused across retries so a resend replaces rather than duplicates.

        Returns:
            str: The identifying d tag of the posted event.
        """
        content = ride_record.model_dump_json(exclude_none=True, by_alias=True)

        start_location = ride_record.stops[0].location

        unix_timestamp_now = int(time.time())

        # Create cascading geohash tags for each precision from 1 to 10
        geohash_tags = [
            ["g", geohash2.encode(start_location.latitude, start_location.longitude, precision=p)] for p in range(1, 11)
        ]

        d_tag = build_ride_d_tag(ride_record.source, tags, d_tag)

        published_at_tag = str(unix_timestamp_now) if tags is None else next(tag[1] for tag in tags if tag[0] == "published_at")

        event = Event(
            kind=self.event_kind,
            created_at=unix_timestamp_now,
            content=content,
            pubkey=self.pubkey_hex,
            id=None,  # ID will be computed when signing
            sig=None,  # Signature will be added later
            tags=[
                ["d", d_tag],  # Use existing d tag if updating, otherwise create a new one
                *geohash_tags,  # geohash is always updated in case the ride's location changes
                # published_at stays the same across versions of the same ride,
                # so that we can identify updates to the same ride across versions
                ["published_at", published_at_tag],
            ],
        )

        event.sign(self.private_key_hex)

        _append_event_to_temporary_json(event)

        print("posting to relays")
        self.relay_manager.publish_event(event)
        self.relay_manager.run_sync()  # Sync with the relay to send the event
        print("posted, waiting a bit")
        time.sleep(5)

        while self.relay_manager.message_pool.has_ok_notices():
            ok_msg = self.relay_manager.message_pool.get_ok_notice()
            print(ok_msg)

        return d_tag

    def close(self):
        self.relay_manager.close_all_relay_connections()
