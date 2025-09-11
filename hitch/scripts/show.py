import json
import logging
import math
import os
import traceback

import numpy as np
import pandas as pd

from hitch.helpers import e, get_bearing, get_db, get_dirs, haversine_np, write_json_file
from hitch.models import OsmHitchhikingSpot, HitchwikiArticleMap

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

dirs = get_dirs()

logger.info("Creating directories if they don't exist")
os.makedirs(dirs["dist"], exist_ok=True)

logger.info("Fetching rides")
rides_df = pd.read_sql("select * from ride_event", get_db())
logger.info(f"Got {len(rides_df)} rides")

rides_df["stops"] = rides_df["stops"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
rides_df["hitchhikers"] = rides_df["hitchhikers"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)


logger.info("Extracting start and end coordinates")
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


rides_df[["lat", "lon", "dest_lat", "dest_lon"]] = rides_df.apply(get_start_end_coords, axis=1)

# rides_df["user_id"] = rides_df["user_id"].astype(pd.Int64Dtype())

# logger.info("Fetching duplicates from database")
# duplicates = pd.read_sql("select * from duplicates where reviewed = accepted", get_db())

# try:
#     logger.info("Fetching users from database")
#     users = pd.read_sql("select * from user", get_db())
# except pd.errors.DatabaseError as err:
#     logger.error("Failed to fetch users from database")
#     raise Exception("Run server.py to create the user table") from err

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

# logger.info("Replacing duplicate rides_df")
# rides_df[["lat", "lon"]] = rides_df[["lat", "lon"]].apply(lambda x: replace_map.get(tuple(x), x), axis=1, raw=True)

# rides_df.loc[rides_df.id.isin(range(1000000, 1040000)), "comment"] = (
#     rides_df.loc[rides_df.id.isin(range(1000000, 1040000)), "comment"]
#     .str.encode("cp1252", errors="ignore")
#     .str.decode("utf-8", errors="ignore")
# )

rides_df["submission_time"] = pd.to_datetime(rides_df["submission_time"])


def get_ride_datetime(row):
    start_location = row["stops"][0]
    ride_datetime = start_location.get("departure_time", None)

    return ride_datetime


rides_df["ride_datetime"] = rides_df.apply(get_ride_datetime, axis=1)
rides_df["ride_datetime"] = pd.to_datetime(rides_df["ride_datetime"], errors="coerce")

rads = rides_df[["lon", "lat", "dest_lon", "dest_lat"]].values.T

logger.info("Calculating distances and directions")
rides_df["distance"] = haversine_np(*rads)
rides_df["direction"] = get_bearing(*rads)

logger.info("Cleaning where ride distance is unrealisticly short")
rides_df.loc[(rides_df.distance < 1), "dest_lat"] = None
rides_df.loc[(rides_df.distance < 1), "dest_lon"] = None
rides_df.loc[(rides_df.distance < 1), "direction"] = None
rides_df.loc[(rides_df.distance < 1), "distance"] = None

rounded_dir = 45 * np.round(rides_df.direction / 45)
rides_df["arrows"] = rounded_dir.replace(
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
rating_text = "rating: " + rides_df["rating"].astype(str) + "/5"
destination_text = (
    ", ride: " + np.round(rides_df["distance"]).astype(str).str.replace(".0", "", regex=False) + " km " + rides_df["arrows"]
)


logger.info("Calculating wait times")
def get_wait(row):
    start_location = row["stops"][0]
    wait = start_location.get("waiting_duration", None)

    if wait is not None:
        # Convert ISO 8601 duration to minutes
        # TODO: first verify that it is proper iso format
        wait = int(wait.replace("PT", "").replace("M", ""))

    return wait


rides_df["wait"] = rides_df.apply(get_wait, axis=1)


logger.info("Determining signals")
def get_signals(approaches):
    if approaches is None or not isinstance(approaches, list):
        return None # No signals available
    
    signals = []

    for approach in approaches:
        signals.extend(approach.get("methods", []))

    symbol_map = {"asking": "💬", "sign": "🪧", "thumb": "👍"}
    symbols = ",".join(symbol_map.get(sig, sig) for sig in set(signals))

    return symbols

rides_df["signal"] = rides_df["signals"].apply(get_signals)

logger.info("Generating info texts")
rides_df["wait_text"] = None
has_accurate_wait = ~rides_df["wait"].isnull() & rides_df["source"] != "liftershalte.info"
rides_df.loc[has_accurate_wait, "wait_text"] = (
    ", wait: "
    + rides_df["wait"][has_accurate_wait].astype(str)
    + " min"
    + (" " + rides_df["signal"][has_accurate_wait]).fillna("")
)

rides_df["extra_text"] = rating_text + rides_df.wait_text.fillna("") + destination_text.fillna("")

comment_nl = rides_df["comment"] + "\n\n"

comment_nl.loc[(rides_df["submission_time"].dt.year > 2021) & rides_df.comment.isnull()] = ""

review_submit_datetime = rides_df["submission_time"].dt.strftime(", %B %Y").fillna("")

# rides_df["username"] = pd.merge(
#     left=rides_df[["user_id"]],
#     right=users[["id", "username"]],
#     left_on="user_id",
#     right_on="id",
#     how="left",
# )["username"]


logger.info("Generating user links")
def get_hitchhiker_name(row):
    if "hitchhikers" in row and isinstance(row["hitchhikers"], list) and len(row["hitchhikers"]) > 0:
        first_hitchhiker = row["hitchhikers"][0]
        if (
            "nickname" in first_hitchhiker
            and first_hitchhiker["nickname"].strip() != ""
            and pd.notna(first_hitchhiker["nickname"])
        ):
            return first_hitchhiker["nickname"]
    return "Anonymous"


rides_df["hitchhiker_name"] = rides_df["hitchhikers"].apply(get_hitchhiker_name)

rides_df["user_link"] = (
    "<a href='/?user=" + e(rides_df["hitchhiker_name"]) + "#filters'>" + e(rides_df["hitchhiker_name"]) + "</a>"
).fillna(
    "Anonymous  "
    + '<i class="icon-button fa fa-hand" title="Claim this review as yours." onclick="confirmClaimReview(\'/claim-review/'
    + rides_df["id"].astype(str)
    + "')\"></i>"
)

rides_df["text"] = (
    e(comment_nl)
    + "<i>"
    + e(rides_df["extra_text"])
    + "</i><br><br>―"
    + rides_df["user_link"]
    + rides_df.ride_datetime.dt.strftime(", %a %d %b %Y, %H:%M").fillna(review_submit_datetime)
)

oldies = rides_df["submission_time"].dt.year <= 2021
rides_df.loc[oldies, "text"] = (
    e(comment_nl[oldies])
    + "―"
    + rides_df.loc[oldies, "user_link"]
    + rides_df[oldies]["submission_time"].dt.strftime(", %B %Y").fillna("")
)

groups = rides_df.groupby(["lat", "lon"])

places = groups[["source"]].first()  # TODO: this is a trick for now
places["rating"] = groups.rating.mean().round()
places["wait"] = rides_df[~rides_df.wait.isnull()].groupby(["lat", "lon"]).wait.mean()
places["distance"] = rides_df[~rides_df.distance.isnull()].groupby(["lat", "lon"]).distance.mean()
places["text"] = groups.text.apply(lambda t: "<hr>".join(t.dropna()))

places["review_users"] = (
    rides_df.dropna(subset=["text", "hitchhiker_name"]).groupby(["lat", "lon"])["hitchhiker_name"].unique().apply(list)
)

places["dest_lats"] = rides_df.dropna(subset=["dest_lat", "dest_lon"]).groupby(["lat", "lon"]).dest_lat.apply(list)
places["dest_lons"] = rides_df.dropna(subset=["dest_lat", "dest_lon"]).groupby(["lat", "lon"]).dest_lon.apply(list)

places.reset_index(inplace=True)
places.sort_values("rating", inplace=True, ascending=False)

def generate_spot_id(lat, lon):
    """Generate coordinate-based spot ID."""
    return f"{lat:.4f}_{lon:.4f}"

logger.info("Fetching OSM hitchhiking spots")
osm_spots_df = pd.read_sql("select id, latitude, longitude from osm_hitchhiking_spot", get_db())

def find_nearby_osm_spot(lat, lon, osm_spots, max_distance_km=0.1) -> int | None:
    """Find the nearest OSM hitchhiking spot within max_distance_km (default 100m)."""
    if osm_spots.empty:
        return None
    
    # Calculate distances using haversine formula
    distances = haversine_np(
        np.array([lon] * len(osm_spots)),
        np.array([lat] * len(osm_spots)), 
        osm_spots['longitude'].values,
        osm_spots['latitude'].values
    )
    
    # Find spots within the maximum distance
    nearby_mask = distances <= max_distance_km
    if not nearby_mask.any():
        return None
    
    # Return the ID of the closest spot
    nearby_spots = osm_spots[nearby_mask]
    nearby_distances = distances[nearby_mask]
    closest_idx = nearby_distances.argmin()
    return nearby_spots.iloc[closest_idx]['id']

hitchwiki_df = pd.read_sql(
    "select id, title, heading, latitude, longitude, hitchwiki_url from hitchwiki_article_location",
    get_db()
)

logger.info("Loading Hitchwiki map data")
hitchwiki_maps_df = pd.read_sql(
    "select id, title, latitude, longitude, zoom, hitchwiki_url from hitchwiki_article_map",
    get_db()
)

def find_nearby_hitchwiki_article(lat, lon, hitchwiki_articles, max_distance_km=0.1) -> str | None:
    """Find the nearest Hitchwiki article location within max_distance_km (default 100m)."""
    if hitchwiki_articles.empty:
        return None

    distances = haversine_np(
        np.array([lon] * len(hitchwiki_articles)),
        np.array([lat] * len(hitchwiki_articles)),
        hitchwiki_articles['longitude'].values,
        hitchwiki_articles['latitude'].values
    )

    nearby_mask = distances <= max_distance_km
    if not nearby_mask.any():
        return None

    # Return the link of the closest article
    nearby_articles = hitchwiki_articles[nearby_mask]
    nearby_distances = distances[nearby_mask]
    closest_idx = nearby_distances.argmin()
    return nearby_articles.iloc[closest_idx]['hitchwiki_url']


def get_map_bounds(center_lat, center_lng, zoom=11, map_width=300, map_height=300):
    scale = 2 ** zoom
    world_width = 256 * scale

    # Convert center to world coordinates
    center_x = (center_lng + 180) * world_width / 360
    center_y = world_width / 2 - math.log(math.tan((center_lat + 90) * math.pi / 360)) * world_width / (2 * math.pi)

    # Calculate bounds in world coordinates
    half_width = map_width / 2
    half_height = map_height / 2

    west_x = center_x - half_width
    east_x = center_x + half_width
    north_y = center_y - half_height
    south_y = center_y + half_height

    # Convert back to lat/lng
    west = (west_x * 360 / world_width) - 180
    east = (east_x * 360 / world_width) - 180
    north = (math.atan(math.exp((world_width / 2 - north_y) * 2 * math.pi / world_width)) * 360 / math.pi) - 90
    south = (math.atan(math.exp((world_width / 2 - south_y) * 2 * math.pi / world_width)) * 360 / math.pi) - 90

    return {'north': north, 'south': south, 'east': east, 'west': west}


def find_hitchwiki_map_for_spot(lat, lon, hitchwiki_maps, map_width=300, map_height=300) -> str | None:
    """Find the Hitchwiki article map with highest zoom where the spot is visible."""
    if hitchwiki_maps.empty:
        return None
    
    visible_maps = []
    
    for _, map_row in hitchwiki_maps.iterrows():
        bounds = get_map_bounds(
            center_lat=map_row['latitude'], 
            center_lng=map_row['longitude'], 
            zoom=map_row['zoom'], 
            map_width=map_width, 
            map_height=map_height
        )
        
        # Check if spot is within map bounds
        if (bounds['south'] <= lat <= bounds['north'] and 
            bounds['west'] <= lon <= bounds['east']):
            visible_maps.append({
                'zoom': map_row['zoom'],
                'url': map_row['hitchwiki_url']
            })
    
    if not visible_maps:
        return None
    
    # Return the URL of the map with the highest zoom level
    highest_zoom_map = max(visible_maps, key=lambda x: x['zoom'])
    return highest_zoom_map['url']


logger.info("Finding nearby OSM spots")
places["nearby_osm_id"] = places.apply(
    lambda row: find_nearby_osm_spot(row["lat"], row["lon"], osm_spots_df), axis=1
)
logger.info(f"Found {places['nearby_osm_id'].notnull().sum()} places with nearby OSM spots")

logger.info("Finding nearby Hitchwiki articles")
places["nearby_hitchwiki_link"] = places.apply(
    lambda row: find_nearby_hitchwiki_article(row["lat"], row["lon"], hitchwiki_df), axis=1
)
logger.info(f"Found {places['nearby_hitchwiki_link'].notnull().sum()} places with nearby Hitchwiki articles")

logger.info("Finding Hitchwiki maps covering spots")
places["hitchwiki_map_link"] = places.apply(
    lambda row: find_hitchwiki_map_for_spot(row["lat"], row["lon"], hitchwiki_maps_df), axis=1
)
logger.info(f"Found {places['hitchwiki_map_link'].notnull().sum()} places visible in Hitchwiki maps")
    
logger.info("Generating JSON data files")
# Generate spots data with coordinate-based IDs and OSM spot matching
spots_data = []
for _, place in places.iterrows():   
    spot_data = {
        "id": generate_spot_id(place["lat"], place["lon"]),
        "lat": place["lat"],
        "lon": place["lon"],
        "rating": place["rating"],
        "wait": place["wait"],
        "distance": place["distance"],
        "ride_count": len(rides_df[(rides_df["lat"] == place["lat"]) & (rides_df["lon"] == place["lon"])]),
        "review_users": place["review_users"],
        "dest_lats": place["dest_lats"],
        "dest_lons": place["dest_lons"],
        "osm_id": place["nearby_osm_id"],
        "hitchwiki_article": place["nearby_hitchwiki_link"],
        "hitchwiki_map": place["hitchwiki_map_link"],
    }
    spots_data.append(spot_data)

write_json_file(spots_data, "spots.json")

# Generate individual rides data
rides_data = []
for _, ride in rides_df.iterrows():
    # Handle submission_time - check if it's already a datetime or string
    submission_time = None
    if pd.notna(ride["submission_time"]):
        if hasattr(ride["submission_time"], 'isoformat'):
            submission_time = ride["submission_time"].isoformat()
        else:
            submission_time = str(ride["submission_time"])
    
    # Handle ride_datetime similarly
    ride_datetime = None
    if pd.notna(ride.get("ride_datetime")):
        if hasattr(ride["ride_datetime"], 'isoformat'):
            ride_datetime = ride["ride_datetime"].isoformat()
        else:
            ride_datetime = str(ride["ride_datetime"])
    
    ride_data = {
        "id": ride["d"] if pd.notna(ride.get("d")) else f"ride_{ride.name}",  # Fallback to index if no d_tag
        "spot_id": generate_spot_id(ride["lat"], ride["lon"]),
        "lat": ride["lat"],
        "lon": ride["lon"],
        "dest_lat": ride["dest_lat"] if pd.notna(ride["dest_lat"]) else None,
        "dest_lon": ride["dest_lon"] if pd.notna(ride["dest_lon"]) else None,
        "rating": int(ride["rating"]) if pd.notna(ride["rating"]) else None,
        "wait": int(ride["wait"]) if pd.notna(ride["wait"]) else None,
        "comment": ride["comment"] if pd.notna(ride.get("comment")) else None,
        "hitchhiker_name": ride["hitchhiker_name"] if pd.notna(ride.get("hitchhiker_name")) else "Anonymous",
        "submission_time": submission_time,
        "ride_datetime": ride_datetime,
        "source": ride["source"] if pd.notna(ride.get("source")) else None,
        "text": ride["text"] if pd.notna(ride.get("text")) else ""  # Formatted text for sidebar display
    }
    rides_data.append(ride_data)

write_json_file(rides_data, "rides.json")

# TODO: Remove spots_with_destination.json - replaced by spots.json with ride filtering
# places_with_destination = places[~places.distance.isnull()]
# write_json_file(places_with_destination[point_columns], "spots_with_destination.json")

recent = rides_df.dropna(subset=["submission_time"]).sort_values("submission_time", ascending=False).iloc[:1000]
recent["url"] = "#" + recent.lat.astype(str) + "," + recent.lon.astype(str)
recent["text"] = rides_df.comment.fillna("") + " " + rides_df.extra_text.fillna("")
recent["hitchhiker_name"] = recent["hitchhiker_name"].str.replace("://", "", regex=False)
recent["distance"] = recent["distance"].round(1)
recent["submission_time"] = recent["submission_time"].astype(str)
recent["submission_time"] += np.where(~recent.ride_datetime.isnull(), " 🕒", "")
write_json_file(recent[["url", "submission_time", "hitchhiker_name", "rating", "distance", "text"]], "spots_recent.json")

# duplicates["from_url"] = "#" + duplicates.from_lat.astype(str) + "," + duplicates.from_lon.astype(str)
# duplicates["to_url"] = "#" + duplicates.to_lat.astype(str) + "," + duplicates.to_lon.astype(str)
# duplicates_data = duplicates[["id", "from_url", "to_url", "distance", "reviewed", "accepted"]].to_dict(orient="records")
# write_json_file(duplicates[["id", "from_url", "to_url", "distance", "reviewed", "accepted"]], "rides_df_duplicates.json")

logger.info("Data preparation completed")

def generate_heatmap_data():
    """Generate heatmap data and return the image overlay data."""
    import matplotlib.colors as colors
    import numpy as np
    from heatchmap.gpmap import GPMap
    from heatchmap.map_based_model import BOUNDARIES, BUCKETS
    
    # Use truncated buckets and boundaries as in hitchhiking.py
    BUCKETS = BUCKETS[:-1]
    BOUNDARIES = BOUNDARIES[:-1]
    
    cmap = colors.ListedColormap(BUCKETS)
    norm = colors.BoundaryNorm(BOUNDARIES, cmap.N, clip=True)
    cmap.set_bad(color="#000000", alpha=0.0)  # opaque for NaN values (sea)
    
    gpmap = GPMap()
    gpmap.get_map_grid()
    gpmap.get_landmass_raster()
    
    image = gpmap.raw_raster
    image = np.where(gpmap.landmass_raster, image, np.nan)
    image = norm(image).data
    # Apply the colormap to scalars
    colors_data = cmap(image)
    
    uncertainties = gpmap.uncertainties
    # no uncertainties for sea -> becomes fully transparent
    uncertainties = np.where(gpmap.landmass_raster, uncertainties, uncertainties.max())
    # Normalize uncertainties
    uncertainties = (uncertainties - uncertainties.min()) / (uncertainties.max() - uncertainties.min())
    uncertainties = 1 - uncertainties
    
    # Combine RGB values with the opacity
    rgba_array = np.empty_like(colors_data)
    rgba_array[:, :, :3] = colors_data[:, :, :3]  # RGB
    rgba_array[:, :, 3] = uncertainties
    
    # Create legend data
    legend_data = {
        'colors': BUCKETS.tolist() if hasattr(BUCKETS, 'tolist') else list(BUCKETS),
        'boundaries': BOUNDARIES[:-1].tolist() if hasattr(BOUNDARIES[:-1], 'tolist') else list(BOUNDARIES[:-1]),
        'vmin': float(BOUNDARIES[0]),
        'vmax': float(BOUNDARIES[-1]),
        'caption': "Waiting time to catch a ride by hitchhiking (minutes)"
    }
    
    return {
        'image_data': rgba_array.tolist(),  # Convert to list for JSON serialization
        'bounds': [[-56, -180], [80, 180]],
        'legend': legend_data
    }

# Generate heatmap data file
logger.info("Generating heatmap data")
try:
    heatmap_data = generate_heatmap_data()
    write_json_file(heatmap_data, "heatmap.json")
    logger.info("Heatmap data generated successfully")
except Exception as e:
    logger.error(f"Failed to generate heatmap data: {e}")
    logger.info("Continuing without heatmap data")

logger.info("All data preparation completed")
