from hitch.helpers import haversine_np

AVERAGE_SPEED = 60  # km/h rough estimate for straight-line time


def routing(
    A: tuple[float, float] = (51.0504, 13.7373), B: tuple[float, float] = (52.3676, 4.9041)
) -> tuple[None, list[tuple[float, float]], float]:
    """Return a straight line between A and B with a rough time estimate."""
    distance = haversine_np(lat1=A[0], lon1=A[1], lat2=B[0], lon2=B[1])
    total_time_minutes = distance / AVERAGE_SPEED * 60
    route = [A, B]
    return None, route, total_time_minutes


# --- Graph-based routing (commented out for now, draws straight line above instead) ---
#
# import logging
# import os
#
# import networkx as nx
# import pandas as pd
#
# from hitch.helpers import get_dirs
#
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)
#
#
# # Speed assumptions in km/h
# WALKING_SPEED = 5  # km/h
# RIDE_SPEED = 100  # km/h average including highways
#
# # Distance limits
# MAX_WALKING_DISTANCE = 10  # km
#
#
# def find_route(G, departure, arrival, walking_distance):
#     """Find route with walking connections to departure/arrival points."""
#     num_edges_before = len(G.edges)
#
#     # Add start and end points as nodes in the graph (using lat, lon, type format)
#     start_node = (departure[0], departure[1], "depart")
#     end_node = (arrival[0], arrival[1], "arrive")
#     G.add_node(start_node)
#     G.add_node(end_node)
#
#     departing_nodes = [n for n in G.nodes if isinstance(n, tuple) and len(n) == 3 and n[2] == "depart"]
#     arriving_nodes = [n for n in G.nodes if isinstance(n, tuple) and len(n) == 3 and n[2] == "arrive"]
#
#     # Add walking edges between all nearby nodes
#     for node1 in departing_nodes:
#         for node2 in arriving_nodes:  # Only connect departing to arriving nodes
#             if len(node1) != 3 or len(node2) != 3:  # Skip if not (lat,lon,type) format
#                 continue
#
#             distance = haversine_np(lat1=node1[0], lon1=node1[1], lat2=node2[0], lon2=node2[1])
#             if distance < walking_distance:
#                 walking_time = distance / WALKING_SPEED * 60  # in minutes
#
#                 G.add_edge(node1, node2, weight=walking_time, type="walking")
#
#     logger.info(f"{len(G.edges) - num_edges_before} walking edges added")
#
#     try:
#         route = nx.dijkstra_path(G, start_node, end_node, weight="weight")
#         total_time = nx.dijkstra_path_length(G, start_node, end_node, weight="weight")
#         return G, route, total_time
#     except nx.NetworkXNoPath:
#         raise ValueError(f"No path found from {departure} to {arrival}") from None
#
#
# def routing_graph_based(
#     A: tuple[float, float] = (51.0504, 13.7373), B: tuple[float, float] = (52.3676, 4.9041)
# ) -> tuple[nx.DiGraph, list[tuple[float, float]], float]:
#     """
#     Very simple dummy routing using Dijkstra's algorithm on a graph of rides and walking in between hitchhiking spots.
#
#     Currently this is based on length of the route and waiting times are not yet considered.
#
#     Example: Dresden -> Amsterdam
#
#     Args:
#         A (tuple): (lat, lon) of start point
#         B (tuple): (lat, lon) of end point
#
#     Returns:
#         g (nx.DiGraph): Graph with all rides and walking connections
#         route (list): List of (lat, lon) tuples representing the route
#         total_time (float): Total travel time in minutes
#
#     """
#     rides_path = os.path.join(get_dirs()["dist"], "rides.json")
#     rides_df = pd.read_json(rides_path)
#     df = rides_df[~rides_df["dest_lon"].isna()]
#
#     # Start with a smaller bounding box, expand if no data found
#     for margin in [0.5, 1.0, 2.0, 5.0]:
#         min_lat = A[0] - margin if A[0] < B[0] else B[0] - margin
#         max_lat = A[0] + margin if A[0] > B[0] else B[0] + margin
#         min_lon = A[1] - margin if A[1] < B[1] else B[1] - margin
#         max_lon = A[1] + margin if A[1] > B[1] else B[1] + margin
#
#         # Filter rides within the bounding box
#         filtered_df = df[
#             (df["lat"] > min_lat)
#             & (df["lat"] < max_lat)
#             & (df["lon"] > min_lon)
#             & (df["lon"] < max_lon)
#             & (df["dest_lat"] > min_lat)
#             & (df["dest_lat"] < max_lat)
#             & (df["dest_lon"] > min_lon)
#             & (df["dest_lon"] < max_lon)
#         ]
#
#         if len(filtered_df) > 0:
#             logger.info(f"Found {len(filtered_df)} rides with margin {margin}°")
#             break
#     else:
#         raise ValueError(f"No ride data found within {margin}° of the route coordinates. Try different start/end points.")
#
#     df = filtered_df
#
#     # Calculate distance and ride time for each ride
#     df["distance"] = df.apply(
#         lambda row: haversine_np(lat1=row.lat, lon1=row.lon, lat2=row.dest_lat, lon2=row.dest_lon),
#         axis=1,
#     )
#     df["ride_time"] = df["distance"] / RIDE_SPEED * 60  # in minutes
#
#     # Calculate waiting time at each spot (average wait time from the data)
#     spot_wait_times = df.groupby(["lat", "lon"])["wait"].mean().fillna(60.0)  # Default 1 hour if no data
#
#     g = nx.DiGraph()
#
#     # Separate pickup and destination spots
#     pickup_spots = set()
#     dest_spots = set()
#     for _, row in df.iterrows():
#         pickup_spots.add((row.lat, row.lon))
#         dest_spots.add((row.dest_lat, row.dest_lon))
#
#     # Create arrival and departure nodes for ALL pickup spots (with waiting time)
#     for lat, lon in pickup_spots:
#         arrive_node = (lat, lon, "arrive")
#         depart_node = (lat, lon, "depart")
#
#         # Add waiting edge from arrival to departure at pickup spots
#         wait_time = spot_wait_times.get((lat, lon), 60.0)
#         g.add_edge(arrive_node, depart_node, weight=wait_time, type="waiting")
#
#     # Create arrival nodes for destination spots that are NOT pickup spots
#     pure_dest_spots = dest_spots - pickup_spots
#     for lat, lon in pure_dest_spots:
#         arrive_node = (lat, lon, "arrive")
#         depart_node = (lat, lon, "depart")
#
#         # No waiting edge needed in destination-only spots
#         # hitchhikers can immediately leave walking after arriving
#         wait_time = 0.0
#         g.add_edge(arrive_node, depart_node, weight=wait_time, type="waiting")
#
#     # Add ride edges between departure and arrival nodes
#     for _, row in df.iterrows():
#         if row["distance"] > 0:  # Valid ride
#             pickup_depart = (row.lat, row.lon, "depart")
#             dest_arrive = (row.dest_lat, row.dest_lon, "arrive")
#
#             g.add_edge(pickup_depart, dest_arrive, weight=row["ride_time"], type="ride", distance=row["distance"])
#
#     # Progressively increase walking distance until we find a solution
#     for walking_distance in [MAX_WALKING_DISTANCE, 20, 50, 100]:  # 10km, 20km, 50km, 100km
#         logger.info(f"Trying with walking distance: {walking_distance} km")
#
#         # Create a copy of the graph for this iteration
#         g_copy = g.copy()
#
#         try:
#             # Try to find a route with current walking distance
#             g_result, route, total_time = find_route(G=g_copy, departure=A, arrival=B, walking_distance=walking_distance)
#             logger.info(f"Route found with walking distance {walking_distance} km!")
#             logger.info(f"Total travel time: {total_time:.2f} minutes")
#
#             # Convert route back to coordinate tuples for compatibility
#             route_coords = []
#             for node in route:
#                 location = node[0:2]
#                 # every spot was transformed into 2 nodes (arrive, depart)
#                 # only add unique locations to the route
#                 if len(route_coords) == 0 or location != route_coords[-1]:
#                     route_coords.append(location)  # (lat, lon)
#
#             return g_result, route_coords, total_time
#
#         except Exception as e:
#             logger.info(f"No route found with walking distance {walking_distance} km: {e}")
#             if walking_distance == 100:  # Last attempt
#                 raise ValueError(f"No route found even with maximum walking distance of {walking_distance} km") from None
