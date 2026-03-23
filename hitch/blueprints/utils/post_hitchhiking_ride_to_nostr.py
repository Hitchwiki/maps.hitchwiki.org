"""
Class to allow posting hitchhiking rides in the standardized format to Nostr.
"""

import ast
import os
import time
import uuid

import geohash2
from pynostr.event import Event
from pynostr.key import PrivateKey
from pynostr.relay_manager import RelayManager

from hitch.blueprints.utils.hitchhiking_data_standard_pydantic_model import HitchhikingRecord

NSEC = os.getenv("NSEC")
RELAYS = ast.literal_eval(os.getenv("RELAYS"))


class HitchhikingDataStandardToNostrPoster:
    def __init__(self):
        private_key_obj = PrivateKey.from_nsec(NSEC)
        self.private_key_hex = private_key_obj.hex()
        self.npub = private_key_obj.public_key.bech32()
        print(f"Posting as npub {self.npub}")

        # Initialize the relay manager
        self.relay_manager = RelayManager(timeout=5)
        for relay in RELAYS:
            self.relay_manager.add_relay(relay)

        self.event_kind = int(os.getenv("NOSTR_EVENT_KIND"))

    def post(self, ride_record: HitchhikingRecord, tags: list = None) -> str:
        """Post a ride in the standardized format to Nostr and return the d tag.
        
        Args:
            ride_record (HitchhikingRecord): The ride record to post.
            tags (list | None): A list of tags to include in the post.
                Used when updating an existing post where tags stay the same.

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

        d_tag = f"{ride_record.source}-{uuid.uuid4()}"

        event = Event(
            kind=self.event_kind,
            created_at=unix_timestamp_now,
            content=content,
            pubkey=self.npub,
            id=None, # ID will be computed when signing
            sig=None,  # Signature will be added later
            tags=[
                ["d", d_tag],
                *geohash_tags,
                ["published_at", str(unix_timestamp_now)],
            ] if tags is None else tags
        )

        event.sign(self.private_key_hex)

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
