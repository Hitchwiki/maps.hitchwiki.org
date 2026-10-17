"""Build dist/route_demand.json: publishable corridor counts from the route-request log."""

from hitch.blueprints.utils.route_demand import read_route_requests, summarise_route_demand
from hitch.blueprints.utils.route_request_log import ROUTE_REQUEST_LOG_PATH
from hitch.helpers import write_json_file

write_json_file(summarise_route_demand(read_route_requests(ROUTE_REQUEST_LOG_PATH)), "route_demand.json")
