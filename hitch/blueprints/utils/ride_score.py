"""Python mirror of hitch/static/ride_score.js. Reads the SAME canonical weights
file so the two can never disagree on point values. Used by later phases to compute
per-user aggregates from stored ride content."""

import json
import pathlib

# hitch/blueprints/utils/ride_score.py -> parents[2] == hitch/ ; weights live in hitch/static/.
_WEIGHTS_PATH = pathlib.Path(__file__).resolve().parents[2] / "static" / "ride_score_weights.json"
WEIGHTS = json.loads(_WEIGHTS_PATH.read_text())
PASSENGER_KINDS = set(WEIGHTS["passenger_kinds"])


def _is_filled(field: str, value) -> bool:
    # Mirrors isFilled() in ride_score.js.
    if isinstance(value, (list, tuple)):
        return len(value) > 0
    if field == "driver_age":
        return value is not None and str(value).strip() != ""
    return isinstance(value, str) and value.strip() != ""


def _score_group(fields: dict, weight_map: dict):
    earned = 0
    max_pts = 0
    missing = []
    for field, pts in weight_map.items():
        max_pts += pts
        if _is_filled(field, fields.get(field)):
            earned += pts
        else:
            missing.append({"field": field, "pts": pts})
    return earned, max_pts, missing


def score_fields(fields: dict) -> dict:
    fields = fields or {}
    d_earned, d_max, d_missing = _score_group(fields, WEIGHTS["driver"])
    d_pct = round(d_earned / d_max * 100) if d_max else 0

    b_earned, b_max, b_missing = _score_group(fields, WEIGHTS["vehicle_base"])
    bonus_eligible = fields.get("vehicle_kind") in PASSENGER_KINDS
    v_earned, v_max, v_missing = b_earned, b_max, list(b_missing)
    if bonus_eligible:
        x_earned, x_max, x_missing = _score_group(fields, WEIGHTS["vehicle_bonus"])
        v_earned += x_earned
        v_max += x_max
        v_missing.extend(x_missing)
    v_missing.sort(key=lambda m: m["pts"], reverse=True)
    d_missing.sort(key=lambda m: m["pts"], reverse=True)
    v_pct = round(v_earned / v_max * 100) if v_max else 0

    # Combined completeness over the whole (driver + vehicle) pool — the UI shows only this;
    # driver/vehicle stay for backend aggregates.
    max_total = d_max + v_max
    total = d_earned + v_earned
    pct = round(total / max_total * 100) if max_total else 0

    return {
        "driver": {"earned": d_earned, "max": d_max, "pct": d_pct, "missing": d_missing},
        "vehicle": {"earned": v_earned, "max": v_max, "pct": v_pct, "missing": v_missing, "bonus_eligible": bonus_eligible},
        "total": total,
        "max_total": max_total,
        "pct": pct,
    }
