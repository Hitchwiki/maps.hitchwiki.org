"""Build the weekly ride-collection aggregate used by /statistics/ride-collection."""

from hitch.blueprints.utils.ride_collection_statistics import summarise_collection
from hitch.helpers import get_db, write_json_file

rows = get_db().execute(
    "select submission_time, source, content from ride_event where submission_time is not null"
).fetchall()
write_json_file(summarise_collection(rows), "ride_collection_statistics.json")
