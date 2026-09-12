"""
USGS Earthquake Catalog integration — real, free, no API key required.
Docs: https://earthquake.usgs.gov/fdsnws/event/1/
"""
from datetime import datetime, timedelta, timezone

import requests

from config import Config

TIMEOUT_S = 15


def get_nearby_earthquakes(lat, lon, radius_km=100, days=90, min_magnitude=3.0):
    """
    Returns a dict:
      {
        "source": "usgs" | "error",
        "count": int,                # quakes >= min_magnitude within radius/window
        "max_magnitude": float|None,
        "events": [ {mag, place, time, distance_km-ish via radius filter}, ... ] (capped)
        "window_days": days,
        "radius_km": radius_km,
      }
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    params = {
        "format": "geojson",
        "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": end.strftime("%Y-%m-%dT%H:%M:%S"),
        "latitude": lat,
        "longitude": lon,
        "maxradiuskm": radius_km,
        "minmagnitude": min_magnitude,
        "orderby": "time",
    }

    try:
        resp = requests.get(Config.USGS_QUAKE_URL, params=params, timeout=TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        events = []
        max_mag = None
        for feat in features:
            props = feat.get("properties", {})
            mag = props.get("mag")
            if mag is not None and (max_mag is None or mag > max_mag):
                max_mag = mag
            events.append(
                {
                    "magnitude": mag,
                    "place": props.get("place"),
                    "time": props.get("time"),
                }
            )
        return {
            "source": "usgs",
            "count": len(events),
            "max_magnitude": max_mag,
            "events": events[:10],
            "window_days": days,
            "radius_km": radius_km,
        }
    except (requests.RequestException, ValueError) as exc:
        return {
            "source": "error",
            "error": str(exc),
            "count": 0,
            "max_magnitude": None,
            "events": [],
            "window_days": days,
            "radius_km": radius_km,
        }
