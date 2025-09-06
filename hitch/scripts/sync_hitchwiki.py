
import pandas as pd
import pywikibot
from pywikibot import pagegenerators
from scipy.spatial import cKDTree
from tqdm import tqdm

from hitch.extensions import db
from hitch.helpers import haversine
from hitch.models import HitchwikiArticleLocation, RideEvent
from hitch.scripts.hitchwiki.coords_extraction import find_coords_and_headings

articles = {}

# TODO: relies on user-password.py better from env var
lang_wiki = pywikibot.Site(code='en', fam='hitchwiki')
if not lang_wiki.user():
    lang_wiki.login()

pages = list(pagegenerators.AllpagesPageGenerator(site=lang_wiki))
for page in tqdm(pages, desc="Processing pages"):
    try:
        if any(s in page.text for s in ["{{Coords"]):
            articles[page.title()] = {"text": page.text}
    except Exception as e:
        print(f"Error processing page: {e}")
        continue

coords = []

for article, items in tqdm(articles.items()):
    coords_results = find_coords_and_headings(raw_wiki_page=items["text"], title=article)

    coords.extend(coords_results)

coords_df = pd.DataFrame(coords)

coords_df["lat"] = coords_df["coords"].apply(lambda x: float(x.split("|")[1].strip()))
coords_df["lon"] = coords_df["coords"].apply(lambda x: float(x.split("|")[2].strip().rstrip("}")))

# TODO: get real spot aggregated from RideEvents
spots = db.session.query(RideEvent).all()
tree = cKDTree(spots[['lat', 'lon']].values)

distances, indices = tree.query(coords_df[['lat', 'lon']].values)

# Add nearest node info to spots DataFrame
coords_df['nearest_node_id'] = spots.iloc[indices]['id'].values
coords_df['nearest_node_lat'] = spots.iloc[indices]['lat'].values
coords_df['nearest_node_lon'] = spots.iloc[indices]['lon'].values
coords_df['distance'] = distances

coords_df['haversine_distance_in_m'] = coords_df.apply(lambda row: haversine(row['lat'], row['lon'], row['nearest_node_lat'], row['nearest_node_lon']) * 1000, axis=1)

coords_df = coords_df.sort_values(by='haversine_distance_in_m')

# Remove all existing HitchwikiArticleLocation entries for a fresh start
db.session.query(HitchwikiArticleLocation).delete()
db.session.commit()

for _, row in coords_df.iterrows():
    location = HitchwikiArticleLocation(
        article_title=row['title'],
        latitude=row['lat'],
        longitude=row['lon'],
        nearest_node_id=row['nearest_node_id'],
        nearest_node_lat=row['nearest_node_lat'],
        nearest_node_lon=row['nearest_node_lon'],
        distance=row['distance'],
        haversine_distance_in_m=row['haversine_distance_in_m'],
    )
    db.session.add(location)
db.session.commit()