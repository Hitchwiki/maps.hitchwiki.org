import gzip
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


KM_PER_MILE = 1.609344


def current_distance_unit():
    """The logged-in user's display unit ("metric" | "imperial"), "metric" for anonymous.

    Everything we store and compute is in km; this only decides how a number is rendered,
    so it is safe to fall back to metric whenever there is no user (crawlers, logged-out
    visitors, generated pages).
    """
    try:
        from flask_security import current_user

        if current_user and not current_user.is_anonymous:
            return current_user.distance_unit or "metric"
    except Exception:
        pass
    return "metric"


def convert_km(km, unit=None):
    """km in the given (or current user's) display unit, as a float."""
    if km is None:
        return None
    return km / KM_PER_MILE if (unit or current_distance_unit()) == "imperial" else km


def distance_unit_label(unit=None):
    return "mi" if (unit or current_distance_unit()) == "imperial" else "km"


def format_distance(km, decimals=0, unit=None):
    """Render a km value as e.g. "412 km" / "256 mi" in the user's chosen unit.

    Returns "" for None so templates can drop it into text without a guard.
    """
    if km is None:
        return ""
    unit = unit or current_distance_unit()
    return f"{convert_km(km, unit):,.{decimals}f} {distance_unit_label(unit)}"


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


def haversine_np(lat1, lon1, lat2, lon2, factor=1.25):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)

    All args must be of equal length.

    Args:
        lat1: Latitude of point 1
        lon1: Longitude of point 1
        lat2: Latitude of point 2
        lon2: Longitude of point 2
        factor: Multiplication factor to adjust the distance
            (default is 1.25 to account for road distance compared to straight line distance)

    Returns:
        Distance in kilometers between the two points, adjusted by the factor.
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
    json_data = data.to_dict(orient="records") if hasattr(data, "to_dict") else data
    payload = simplejson.dumps(json_data, ignore_nan=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(payload)

    # Precompress once at generation time. The catch_all route serves the .gz
    # sidecar with Content-Encoding: gzip, so the reverse proxy doesn't have to
    # recompress these multi-MB files on every request. Written after the plain
    # file so the sidecar's mtime is never older than the data it encodes (the
    # route refuses sidecars older than the plain file).
    with gzip.open(filepath + ".gz", "wb", compresslevel=9) as f:
        f.write(payload.encode("utf-8"))

    logger.info(f"Wrote json of length {len(data)} to: {filepath} (+ .gz sidecar)")
