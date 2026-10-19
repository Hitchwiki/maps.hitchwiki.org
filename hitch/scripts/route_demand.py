"""Build dist/route_demand.json and dist/filter_demand.json: publishable aggregates of the request logs."""

from hitch.blueprints.utils.filter_request_log import FILTER_REQUEST_LOG_PATH
from hitch.blueprints.utils.route_demand import (
    read_route_requests,
    summarise_filter_demand,
    summarise_route_demand,
)
from hitch.blueprints.utils.route_request_log import ROUTE_REQUEST_LOG_PATH
from hitch.helpers import write_json_file

write_json_file(summarise_route_demand(read_route_requests(ROUTE_REQUEST_LOG_PATH)), "route_demand.json")
write_json_file(summarise_filter_demand(read_route_requests(FILTER_REQUEST_LOG_PATH)), "filter_demand.json")
