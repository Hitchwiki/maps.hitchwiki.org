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
    A = (13.7373, 51.0504) # Antwerp
    B = (4.9041, 52.3676) # Amsterdam
    """
    rides_path = os.path.join(get_dirs()["dist"], "rides.json")
    rides_df = pd.read_json(rides_path)
    df = rides_df[~rides_df["dest_lon"].isna()]

    min_lon = A[0] - 0.5 if A[0] < B[0] else B[0] - 0.5
    max_lon = A[0] + 0.5 if A[0] > B[0] else B[0] + 0.5
    min_lat = A[1] - 0.5 if A[1] < B[1] else B[1] - 0.5
    max_lat = A[1] + 0.5 if A[1] > B[1] else B[1] + 0.5
    df = df[df["lon"] > min_lon]
    df = df[df["lon"] < max_lon]
    df = df[df["lat"] < max_lat]
    df = df[df["lat"] > min_lat]
    df = df[df["dest_lon"] > min_lon]
    df = df[df["dest_lon"] < max_lon]
    df = df[df["dest_lat"] < max_lat]
    df = df[df["dest_lat"] > min_lat]

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

    # TODO: this takes too long
    # make it fully connected with walking paths
    for n1 in g.nodes:
        for n2 in g.nodes:
            if n1 != n2 and not g.has_edge(n1, n2):
                dist = haversine_np(n1[0], n1[1], n2[0], n2[1])
                if dist < MAX_WALKING_DISTANCE:
                    g.add_edge(
                        n1,
                        n2,
                        weight=dist * WALKING_FACTOR,
                    )

    g, route, length = find_route(g, A, B)

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