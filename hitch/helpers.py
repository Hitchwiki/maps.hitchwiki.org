import html
import logging
import os
import sqlite3

import numpy as np
import pandas as pd
import simplejson  # WHY not json?
from flask import current_app, g

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db():
    # db = getattr(g, "_database", None)
    # if db is None:
    logger.info(f"Connecting to database on {current_app.config['DATABASE_URI']}")
    db = g._database = sqlite3.connect(database=current_app.config["DATABASE_URI"])
    return db


def get_dirs():
    scripts_dir = os.path.dirname(__file__)
    root_dir = os.path.abspath(os.path.join(scripts_dir, ".."))
    base_dir = os.path.join(root_dir, "hitch")
    dist_dir = os.path.join(root_dir, "dist")
    template_dir = os.path.join(base_dir, "templates")
    db_dir = os.path.abspath(os.path.join(root_dir, "db"))

    return {
        "scripts": scripts_dir,
        "root": root_dir,
        "base": base_dir,
        "dist": dist_dir,
        "templates": template_dir,
        "db": db_dir,
    }


def haversine_np(lon1, lat1, lon2, lat2, factor=1.25):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)

    All args must be of equal length.

    Args:
        lon1: Longitude of point 1
        lat1: Latitude of point 1
        lon2: Longitude of point 2
        lat2: Latitude of point 2
        factor: Multiplication factor to adjust the distance
            (default is 1.25 to account for road distance compared to straight line distance)

    """
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2

    c = 2 * np.arcsin(np.sqrt(a))
    km = 6367 * c
    return factor * km


def get_bearing(lon1, lat1, lon2, lat2):
    dLon = lon2 - lon1
    x = np.cos(np.radians(lat2)) * np.sin(np.radians(dLon))
    y = np.cos(np.radians(lat1)) * np.sin(np.radians(lat2)) - np.sin(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.cos(
        np.radians(dLon)
    )
    brng = np.arctan2(x, y)
    brng = np.degrees(brng)

    return brng


def e(s):
    s2 = s.copy()
    s2.loc[~s2.isnull()] = s2.loc[~s2.isnull()].map(lambda x: html.escape(x).replace("\n", "<br>"))
    return s2


dirs = get_dirs()
def write_json_file(data:pd.DataFrame | dict, filename):
    """Writes a JSON file into the dist folder containing data for the map

    Args:
        data: The data to be converted to JSON
        filename: The filename to be stored into
    """
    filepath = os.path.join(dirs["dist"], filename)
    logger.info(f"Writing: {filepath}")
    with open(filepath, "w", encoding="utf-8") as f:
        json_data = data.to_dict(orient="records") if hasattr(data, "to_dict") else data
        f.write(simplejson.dumps(json_data, ignore_nan=True))

    logger.info(f"Wrote json of length {len(data)} to: {filepath}")
