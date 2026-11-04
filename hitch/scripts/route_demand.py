"""Build dist/route_demand.json and dist/filter_demand.json: publishable aggregates of the request logs."""

from hitch.blueprints.utils.filter_request_log import FILTER_REQUEST_LOG_PATH
from hitch.blueprints.utils.route_demand import (
    read_route_requests,
    summarise_filter_demand,
    summarise_route_demand,
    summarise_search_gaps,
)
from hitch.blueprints.utils.search_request_log import SEARCH_REQUEST_LOG_PATH
from hitch.blueprints.utils.route_request_log import ROUTE_REQUEST_LOG_PATH
from hitch.helpers import get_db, write_json_file

write_json_file(summarise_route_demand(read_route_requests(ROUTE_REQUEST_LOG_PATH)), "route_demand.json")
write_json_file(summarise_filter_demand(read_route_requests(FILTER_REQUEST_LOG_PATH)), "filter_demand.json")


_spots = [(r[0], r[1]) for r in get_db().execute("select lat, lon from points where not banned").fetchall()]
write_json_file(summarise_search_gaps(read_route_requests(SEARCH_REQUEST_LOG_PATH), _spots), "search_gaps.json")
