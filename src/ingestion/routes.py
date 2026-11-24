"""Google Routes API: travel distance/time from the RSK office to each village.

Endpoint (Routes API reference, v2)::

    POST https://routes.googleapis.com/directions/v2:computeRoutes
    headers: X-Goog-Api-Key, X-Goog-FieldMask: routes.distanceMeters,routes.duration
    body:   {"origin": {...}, "destination": {...}, "travelMode": "DRIVE"}

Results are cached in ``data/derived/route_cache.json`` so repeated demo runs do not spend
quota. Without a key the simulated ``villages.road_distance_km`` values stay in use and the
UI labels them as simulated.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from src.config.settings import google_key, project_path

ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"
CACHE_PATH = project_path("data", "derived", "route_cache.json")
TIMEOUT = 20


def _load_cache() -> dict[str, Any]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(cache: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=1), encoding="utf-8")


def driving_distance_km(
    origin: tuple[float, float], destination: tuple[float, float], cache_key: str
) -> dict[str, Any] | None:
    """Return distance/duration, or ``None`` when no Routes API key is configured."""
    key = google_key("GOOGLE_ROUTES_API_KEY") or google_key("GOOGLE_MAPS_API_KEY")
    if not key:
        return None

    cache = _load_cache()
    if cache_key in cache:
        return {**cache[cache_key], "source": "cache"}

    response = requests.post(
        ENDPOINT,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": "routes.distanceMeters,routes.duration",
        },
        json={
            "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
            "destination": {
                "location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}
            },
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_UNAWARE",
        },
        timeout=TIMEOUT,
    )
    if response.status_code != 200:
        print(f"Routes API error HTTP {response.status_code}: {response.text[:200]}")
        return None
    routes = response.json().get("routes") or []
    if not routes:
        return None
    route = routes[0]
    seconds = float(str(route.get("duration", "0s")).rstrip("s") or 0)
    result = {
        "distance_km": round(float(route.get("distanceMeters", 0)) / 1000.0, 2),
        "duration_min": round(seconds / 60.0, 1),
        "source": "google_routes",
    }
    cache[cache_key] = {"distance_km": result["distance_km"], "duration_min": result["duration_min"]}
    _save_cache(cache)
    return result


def main() -> None:
    """CLI: resolve and cache distances from the RSK centre to every village."""
    import pandas as pd

    rsk = pd.read_csv(project_path("data", "cleaned", "rsk.csv")).iloc[0]
    villages = pd.read_csv(project_path("data", "cleaned", "villages.csv"))
    origin = (float(rsk.latitude), float(rsk.longitude))
    if google_key("GOOGLE_ROUTES_API_KEY") is None:
        print(
            "GOOGLE_ROUTES_API_KEY is not set, so no Routes API call was made. "
            "The app keeps using the simulated road_distance_km values."
        )
        return
    for village in villages.itertuples():
        print(
            f"  {village.village_name:22s} "
            f"{driving_distance_km(origin, (float(village.latitude), float(village.longitude)), f'{rsk.rsk_id}-{village.village_id}')}"
        )


if __name__ == "__main__":
    main()
