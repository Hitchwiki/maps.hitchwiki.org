import io
import json
import logging
import os
import zipfile

import networkx
import numpy as np
import pandas as pd
import requests

from hitch.helpers import e, get_bearing, get_db, get_dirs, haversine_np, write_json_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dirs = get_dirs()

logger.info("Creating directories if they don't exist")
os.makedirs(dirs["dist"], exist_ok=True)


def get_rides():
    """Rides where previously fetched from Nostr and stored in a CSV file."""
    rides_df = pd.read_csv(os.path.join(dirs["dist"], "allPosts.csv"))
    # 2 times json loads? why?
    rides_df["content"] = rides_df["content"].apply(json.loads)
    rides_df["json_col"] = rides_df["content"].apply(json.loads)

    # Step 2: Normalize (unpack) into separate columns
    json_df = pd.json_normalize(rides_df["json_col"])

    # Step 3: Concatenate with original DataFrame
    rides_df = pd.concat([rides_df.drop(columns=["json_col"]), json_df], axis=1)
    return rides_df


logger.info("Fetching rides")
points = get_rides()
logger.info(f"Got {len(points)} rides")


def get_start_end_coords(row):
    start_location = row["stops"][0]["location"]

    start_lat = start_location["latitude"]
    start_lon = start_location["longitude"]

    if len(row["stops"]) > 1:
        end_location = row["stops"][-1]["location"]
        dest_lat = end_location["latitude"]
        dest_lon = end_location["longitude"]
    else:
        dest_lat = None
        dest_lon = None

    return pd.Series({"start_lat": start_lat, "start_lon": start_lon, "dest_lat": dest_lat, "dest_lon": dest_lon})


points[["lat", "lon", "dest_lat", "dest_lon"]] = points.apply(get_start_end_coords, axis=1)

# points["user_id"] = points["user_id"].astype(pd.Int64Dtype())

# logger.info("Fetching duplicates from database")
# duplicates = pd.read_sql("select * from duplicates where reviewed = accepted", get_db())

# try:
#     logger.info("Fetching users from database")
#     users = pd.read_sql("select * from user", get_db())
# except pd.errors.DatabaseError as err:
#     logger.error("Failed to fetch users from database")
#     raise Exception("Run server.py to create the user table") from err

logger.info(f"{len(points)} points currently")

# merging and transforming data
# dup_rads = duplicates[["from_lon", "from_lat", "to_lon", "to_lat"]].values.T

# duplicates["distance"] = haversine_np(*dup_rads)
# duplicates["from"] = duplicates[["from_lat", "from_lon"]].apply(tuple, axis=1)
# duplicates["to"] = duplicates[["to_lat", "to_lon"]].apply(tuple, axis=1)

# duplicates = duplicates[duplicates.distance < 1.25]

# dups = networkx.from_pandas_edgelist(duplicates, "from", "to")
# islands = networkx.connected_components(dups)

# replace_map = {}

# logger.info("Processing duplicates")
# for island in islands:
#     parents = [node for node in island if node not in duplicates["from"].tolist()]

#     if len(parents) == 1:
#         for node in island:
#             if node != parents[0]:
#                 replace_map[node] = parents[0]

# logger.info(f"Currently recorded duplicate spots are represented by: ${dups}")

# logger.info("Replacing duplicate points")
# points[["lat", "lon"]] = points[["lat", "lon"]].apply(lambda x: replace_map.get(tuple(x), x), axis=1, raw=True)

# points.loc[points.id.isin(range(1000000, 1040000)), "comment"] = (
#     points.loc[points.id.isin(range(1000000, 1040000)), "comment"]
#     .str.encode("cp1252", errors="ignore")
#     .str.decode("utf-8", errors="ignore")
# )

points["submission_time"] = pd.to_datetime(points["submission_time"])


def get_ride_datetime(row):
    start_location = row["stops"][0]
    ride_datetime = start_location.get("departure_time", None)

    return ride_datetime


points["ride_datetime"] = points.apply(get_ride_datetime, axis=1)
points["ride_datetime"] = pd.to_datetime(points["ride_datetime"], errors="coerce")

rads = points[["lon", "lat", "dest_lon", "dest_lat"]].values.T

logger.info("Calculating distances and directions")
points["distance"] = haversine_np(*rads)
points["direction"] = get_bearing(*rads)

logger.info("Cleaning where ride distance is unrealisticly short")
points.loc[(points.distance < 1), "dest_lat"] = None
points.loc[(points.distance < 1), "dest_lon"] = None
points.loc[(points.distance < 1), "direction"] = None
points.loc[(points.distance < 1), "distance"] = None

rounded_dir = 45 * np.round(points.direction / 45)
points["arrows"] = rounded_dir.replace(
    {
        -90: "←",
        90: "→",
        0: "↑",
        180: "↓",
        -180: "↓",
        -45: "↖",
        45: "↗",
        135: "↘",
        -135: "↙",
    }
)

logger.info("Generating texts")
rating_text = "rating: " + points["rating"].astype(str) + "/5"
destination_text = (
    ", ride: " + np.round(points["distance"]).astype(str).str.replace(".0", "", regex=False) + " km " + points["arrows"]
)


def get_wait(row):
    start_location = row["stops"][0]
    wait = start_location.get("wait_minutes", None)

    return wait


points["wait"] = points.apply(get_wait, axis=1)


def get_signals(signals):
    signals = []

    for approach in signals:
        signals.extend(approach.get("methods", []))

    symbol_map = {"asking": "💬", "sign": "🪧", "thumb": "👍"}
    return ",".join(symbol_map.get(sig, sig) for sig in set(signals))


points["signal"] = points["signals"].apply(get_signals)

points["wait_text"] = None
has_accurate_wait = ~points["wait"].isnull() & points["source"] != "liftershalte.info"
points.loc[has_accurate_wait, "wait_text"] = (
    ", wait: " + points["wait"][has_accurate_wait].astype(str) + " min" + (" " + points["signal"][has_accurate_wait]).fillna("")
)

points["extra_text"] = rating_text + points.wait_text.fillna("") + destination_text.fillna("")

comment_nl = points["comment"] + "\n\n"

comment_nl.loc[(points["submission_time"].dt.year > 2021) & points.comment.isnull()] = ""

review_submit_datetime = points["submission_time"].dt.strftime(", %B %Y").fillna("")

# points["username"] = pd.merge(
#     left=points[["user_id"]],
#     right=users[["id", "username"]],
#     left_on="user_id",
#     right_on="id",
#     how="left",
# )["username"]
points["hitchhiker_name"] = points["hitchhikers"].apply(lambda xs: xs[0]["nickname"])

points["user_link"] = (
    "<a href='/?user=" + e(points["hitchhiker_name"]) + "#filters'>" + e(points["hitchhiker_name"]) + "</a>"
).fillna(
    "Anonymous  "
    + '<i class="icon-button fa fa-hand" title="Claim this review as yours." onclick="confirmClaimReview(\'/claim-review/'
    + points["id"].astype(str)
    + "')\"></i>"
)

points["text"] = (
    e(comment_nl)
    + "<i>"
    + e(points["extra_text"])
    + "</i><br><br>―"
    + points["user_link"]
    + points.ride_datetime.dt.strftime(", %a %d %b %Y, %H:%M").fillna(review_submit_datetime)
)

oldies = points["submission_time"].dt.year <= 2021
points.loc[oldies, "text"] = (
    e(comment_nl[oldies])
    + "―"
    + points.loc[oldies, "user_link"]
    + points[oldies]["submission_time"].dt.strftime(", %B %Y").fillna("")
)

groups = points.groupby(["lat", "lon"])

places = groups[["source"]].first()  # TODO: this is a trick for now
places["rating"] = groups.rating.mean().round()
places["wait"] = points[~points.wait.isnull()].groupby(["lat", "lon"]).wait.mean()
places["distance"] = points[~points.distance.isnull()].groupby(["lat", "lon"]).distance.mean()
places["text"] = groups.text.apply(lambda t: "<hr>".join(t.dropna()))

places["review_users"] = (
    points.dropna(subset=["text", "hitchhiker_name"]).groupby(["lat", "lon"])["hitchhiker_name"].unique().apply(list)
)

places["dest_lats"] = points.dropna(subset=["dest_lat", "dest_lon"]).groupby(["lat", "lon"]).dest_lat.apply(list)
places["dest_lons"] = points.dropna(subset=["dest_lat", "dest_lon"]).groupby(["lat", "lon"]).dest_lon.apply(list)

places.reset_index(inplace=True)
places.sort_values("rating", inplace=True, ascending=False)

point_columns = [
    "lat",
    "lon",
    "rating",
    "text",
    "wait",
    "distance",
    "review_users",
    "dest_lats",
    "dest_lons",
]

logger.info("Generating JSON data files")
write_json_file(places[point_columns], "points.json")

# TODO: saving them separately does not seem good
places_with_destination = places[~places.distance.isnull()]
write_json_file(places_with_destination[point_columns], "points_with_destination.json")

recent = points.dropna(subset=["submission_time"]).sort_values("submission_time", ascending=False).iloc[:1000]
recent["url"] = "#" + recent.lat.astype(str) + "," + recent.lon.astype(str)
recent["text"] = points.comment.fillna("") + " " + points.extra_text.fillna("")
recent["hitchhiker_name"] = recent["hitchhiker_name"].str.replace("://", "", regex=False)
recent["distance"] = recent["distance"].round(1)
recent["submission_time"] = recent["submission_time"].astype(str)
recent["submission_time"] += np.where(~recent.ride_datetime.isnull(), " 🕒", "")
write_json_file(recent[["url", "submission_time", "hitchhiker_name", "rating", "distance", "text"]], "points_recent.json")

# duplicates["from_url"] = "#" + duplicates.from_lat.astype(str) + "," + duplicates.from_lon.astype(str)
# duplicates["to_url"] = "#" + duplicates.to_lat.astype(str) + "," + duplicates.to_lon.astype(str)
# duplicates_data = duplicates[["id", "from_url", "to_url", "distance", "reviewed", "accepted"]].to_dict(orient="records")
# write_json_file(duplicates[["id", "from_url", "to_url", "distance", "reviewed", "accepted"]], "points_duplicates.json")

logger.info("Data preparation completed")


CITIES = False
if CITIES:
    # TODO: needs attribution: https://simplemaps.com/data/world-cities
    if not os.path.exists(os.path.join(dirs["dist"], "cities.csv")):
        logger.info("Fetching major cities data")
        # Download the zip file
        url = "https://simplemaps.com/static/data/world-cities/basic/simplemaps_worldcities_basicv1.901.zip"
        response = requests.get(url)
        zip_bytes = io.BytesIO(response.content)
        # Unzip and extract worldcities.csv
        with zipfile.ZipFile(zip_bytes) as z, z.open("worldcities.csv") as f:
            cities_df = pd.read_csv(f)
        # Filter for major cities (population > 50000)
        major_cities = cities_df[cities_df["population"] > 50000]
        # Save to dist/cities.csv
        major_cities.to_csv(os.path.join(dirs["dist"], "cities.csv"), index=False)

    points.sort_values("datetime", inplace=True, ascending=False)
    cities = pd.read_csv(os.path.join(db_dir, "cities.csv")).drop_duplicates().sort_values("city")
    rendered_cities = []

    for city in cities.itertuples():
        country_folder = os.path.join(dist_dir, "city", city.country)
        os.makedirs(country_folder, exist_ok=True)
        pattern = rf"\b{city.city}\b"
        city_reviews = (
            points[points.text.str.contains(pattern, case=False, regex=True).astype(bool)].dropna(subset="comment").iloc[:20]
        )
        rendered_cities.append(len(city_reviews) >= 3)
        if rendered_cities[-1]:
            rendered = city_template.render(city=city, title=city.city, reviews=city_reviews)
            with open(os.path.join(country_folder, f"{city.city}.html"), "w") as f:
                f.write(rendered)

    print(rendered_cities)

    index_rendered = city_index.render(grouped_cities=cities[rendered_cities].groupby("country"))
    with open(os.path.join(os.path.join(dist_dir, "city"), "index.html"), "w") as f:
        f.write(index_rendered)