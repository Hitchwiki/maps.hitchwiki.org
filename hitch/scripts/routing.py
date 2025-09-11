import os
import sqlite3

import folium
import networkx as nx
import numpy as np
import pandas as pd

from hitch.helpers import haversine_np, get_dirs


MAX_WALKING_DISTANCE = 10 # in km
WALKING_FACTOR = 20 # that is 5 km/h vs. 100 km/h

def find_route(G, departure, arrival):
    num_edges_before = len(G.edges)

    prev_nodes = list(G.nodes)
    for n in prev_nodes:
        dist = haversine_np(arrival[0], arrival[1], n[0], n[1])
        if dist < MAX_WALKING_DISTANCE:
            G.add_edge(
                n,
                arrival,
                weight=dist * WALKING_FACTOR,
            )

    # there is also the walking path from departure to arrival added here
    prev_nodes = list(G.nodes)
    for n in prev_nodes:
        dist = haversine_np(departure[0], departure[1], n[0], n[1])
        if dist < MAX_WALKING_DISTANCE:
            G.add_edge(
                departure,
                n,
                weight=dist * WALKING_FACTOR,
            )

    print(len(G.edges) - num_edges_before, "edges added")

    return (
        G,
        nx.dijkstra_path(G, departure, arrival, weight="weight"),
        nx.dijkstra_path_length(G, departure, arrival, weight="weight"),
    )


def routing(A, B):
    """
    Very simple dummy routing using Dijkstra's algorithm on a graph of rides and walking in between hitchhiking spots.

    Currently this is based on length of the route and waiting times are not yet considered.

    A = (13.7373, 51.0504) # Dresden
    B = (4.9041, 52.3676) # Amsterdam
    """
    rides_path = os.path.join(get_dirs()["dist"], "rides.json")
    rides_df = pd.read_json(rides_path)
    df = rides_df[~rides_df["dest_lon"].isna()]
    
    # Start with a smaller bounding box, expand if no data found
    for margin in [0.5, 1.0, 2.0, 5.0]:
        min_lon = A[0] - margin if A[0] < B[0] else B[0] - margin
        max_lon = A[0] + margin if A[0] > B[0] else B[0] + margin
        min_lat = A[1] - margin if A[1] < B[1] else B[1] - margin
        max_lat = A[1] + margin if A[1] > B[1] else B[1] + margin
        
        # Filter rides within the bounding box
        filtered_df = df[
            (df["lon"] > min_lon) & (df["lon"] < max_lon) &
            (df["lat"] > min_lat) & (df["lat"] < max_lat) &
            (df["dest_lon"] > min_lon) & (df["dest_lon"] < max_lon) &
            (df["dest_lat"] > min_lat) & (df["dest_lat"] < max_lat)
        ]
        
        if len(filtered_df) > 0:
            print(f"Found {len(filtered_df)} rides with margin {margin}°")
            break
    else:
        raise ValueError(f"No ride data found within {margin}° of the route coordinates. Try different start/end points.")
    
    df = filtered_df

    df["distance"] = df.apply(lambda row: haversine_np(row.lon, row.lat, row.dest_lon, row.dest_lat), axis=1)

    g = nx.DiGraph()
    for _, row in df.iterrows():
        if row["distance"]:
            # adding edges is suffient, nodes are created automatically
            g.add_edge(
                (row.lon, row.lat),
                (row.dest_lon, row.dest_lat),
                weight=row["distance"],
            )

    # Progressively increase walking distance until we find a solution
    for walking_distance in [MAX_WALKING_DISTANCE, 20, 50, 100]:  # 10km, 20km, 50km, 100km
        print(f"Trying with walking distance: {walking_distance} km")
        
        # Create a copy of the graph for this iteration
        g_copy = g.copy()
        
        # Add walking edges with current distance limit
        edges_added = 0
        for n1 in g_copy.nodes:
            for n2 in g_copy.nodes:
                if n1 != n2 and not g_copy.has_edge(n1, n2):
                    dist = haversine_np(n1[0], n1[1], n2[0], n2[1])
                    if dist < walking_distance:
                        g_copy.add_edge(
                            n1,
                            n2,
                            weight=dist * WALKING_FACTOR,
                        )
                        edges_added += 1
        
        print(f"Added {edges_added} walking edges")
        
        try:
            # Try to find a route with current walking distance
            g, route, length = find_route(g_copy, A, B)
            print(f"Route found with walking distance {walking_distance} km!")
            break
        except Exception as e:
            print(f"No route found with walking distance {walking_distance} km: {e}")
            if walking_distance == 100:  # Last attempt
                raise ValueError(f"No route found even with maximum walking distance of {walking_distance} km")
    
    return g, route, length

    # m = folium.Map([50.7, 4.2], zoom_start=6)

    # for p in route:
    #     folium.Marker(location=(p[1], p[0])).add_to(m)

    # for i, stop in enumerate(route[:-1]):
    #     folium.PolyLine(
    #         [[stop[1], stop[0]], [route[i + 1][1], route[i + 1][0]]],
    #         color="#FF0000",
    #         weight=5,
    #     ).add_to(m)

    #     folium.RegularPolygonMarker(
    #         location=[route[i + 1][1], route[i + 1][0]], fill_color="blue", number_of_sides=3, radius=10
    #     ).add_to(m)