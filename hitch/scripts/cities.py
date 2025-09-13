"""Create separate HTML pages for major cities mentioned in hitchhiking reviews. Also for SEO purposes."""
import io
import json
import logging
import os
import zipfile

import pandas as pd
import requests
from jinja2 import Environment, FileSystemLoader

from hitch.helpers import get_dirs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dirs = get_dirs()
dist_dir = dirs["dist"]

# Load template environment
env = Environment(loader=FileSystemLoader('hitch/templates'))
city_template = env.get_template('city_template.html')
city_index = env.get_template('city_index.html')

# Load rides data from rides.json created by show.py
logger.info("Loading rides data from rides.json")
with open(os.path.join(dist_dir, "rides.json")) as f:
    rides_data = json.load(f)

# Convert to DataFrame for easier processing
rides = pd.DataFrame(rides_data)
logger.info(f"Loaded {len(rides)} rides")

# TODO: needs attribution: https://simplemaps.com/data/world-cities
cities_csv_path = os.path.join(dist_dir, "cities.csv")
if not os.path.exists(cities_csv_path):
    zip_path = os.path.join(dist_dir, "worldcities.zip")
    
    logger.info("Extracting worldcities.csv...")
    # Unzip and extract worldcities.csv
    with zipfile.ZipFile(zip_path) as z, z.open("worldcities.csv") as f:
        cities_df = pd.read_csv(f)
    
    # Filter for major cities (population > 50000)
    major_cities = cities_df[cities_df["population"] > 50000]
    logger.info(f"Found {len(major_cities)} major cities with population > 50,000")
    
    # Save to dist/cities.csv
    major_cities.to_csv(cities_csv_path, index=False)
    logger.info(f"Saved cities data to {cities_csv_path}")

# Sort rides by datetime (most recent first)
rides.sort_values("ride_datetime", inplace=True, ascending=False)

# Load cities data
cities = pd.read_csv(cities_csv_path).drop_duplicates().sort_values("city")
rendered_cities = []

logger.info(f"Processing {len(cities)} cities")

for city in cities.itertuples():
    country_folder = os.path.join(dist_dir, "city", city.country)
    os.makedirs(country_folder, exist_ok=True)
    pattern = rf"\b{city.city}\b"
    
    # Find rides that mention this city in their text
    city_rides = rides[
        rides.text.str.contains(pattern, case=False, regex=True, na=False)
    ].dropna(subset=["text"]).iloc[:20]
    
    rendered_cities.append(len(city_rides) >= 3)
    if rendered_cities[-1]:
        logger.info(f"Rendering city page for {city.city}, {city.country} ({len(city_rides)} rides)")
        rendered = city_template.render(city=city, title=city.city, reviews=city_rides)
        # Replace "/" with "-" to avoid filesystem issues
        safe_filename = city.city.replace("/", "-")
        with open(os.path.join(country_folder, f"{safe_filename}.html"), "w") as f:
            f.write(rendered)

logger.info(f"Rendered {sum(rendered_cities)} city pages out of {len(cities)} cities")

# Create city index page
os.makedirs(os.path.join(dist_dir, "city"), exist_ok=True)
index_rendered = city_index.render(grouped_cities=cities[rendered_cities].groupby("country"))
with open(os.path.join(dist_dir, "city", "index.html"), "w") as f:
    f.write(index_rendered)

logger.info("CITIES SCRIPT FINISHED")