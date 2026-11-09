"""Build dist/route_demand.json and dist/filter_demand.json: publishable aggregates of the request logs."""

import json
import os

from hitch.blueprints.utils.filter_request_log import FILTER_REQUEST_LOG_PATH
from hitch.blueprints.utils.route_demand import (
    read_route_requests,
    summarise_filter_demand,
    summarise_route_demand,
    summarise_route_feedback,
    summarise_search_gaps,
)
from hitch.blueprints.utils.route_feedback_log import ROUTE_FEEDBACK_LOG_PATH
from hitch.blueprints.utils.route_request_log import ROUTE_REQUEST_LOG_PATH
from hitch.blueprints.utils.search_request_log import SEARCH_REQUEST_LOG_PATH
from hitch.helpers import dirs, logger, write_json_file

write_json_file(summarise_route_demand(read_route_requests(ROUTE_REQUEST_LOG_PATH)), "route_demand.json")
write_json_file(summarise_filter_demand(read_route_requests(FILTER_REQUEST_LOG_PATH)), "filter_demand.json")
write_json_file(summarise_route_feedback(read_route_requests(ROUTE_FEEDBACK_LOG_PATH)), "route_feedback.json")

try:
    # The legacy `points` table is gone (rides live in ride_event); spots.json, written by `generate show`,
    # carries every spot's lat/lon.
    with open(os.path.join(dirs["dist"], "spots.json"), encoding="utf-8") as _f:
        _spots = [(r["lat"], r["lon"]) for r in json.load(_f)]
    write_json_file(summarise_search_gaps(read_route_requests(SEARCH_REQUEST_LOG_PATH), _spots), "search_gaps.json")
except Exception as exc:  # the cron wrapper only prints to an unread log; leave a visible trace instead of no file
    logger.exception("search_gaps failed")
    write_json_file({"error": type(exc).__name__, "gaps": []}, "search_gaps.json")
