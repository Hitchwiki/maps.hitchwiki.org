"""Create separate HTML pages for major cities mentioned in hitchhiking reviews. Also for SEO purposes."""
import io
import logging
import os
import zipfile

import pandas as pd
import requests

from hitch.helpers import get_dirs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DIRS = get_dirs()


# TODO: build up on show.py

# TODO: needs attribution: https://simplemaps.com/data/world-cities
if not os.path.exists(os.path.join(DIRS["dist"], "cities.csv")):
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