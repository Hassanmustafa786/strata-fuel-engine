"""Driving routes from OSRM: one request per trip, cached."""
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

from .errors import ExternalServiceError, RouteNotFound

METERS_PER_MILE = 1609.344

_session = requests.Session()


@dataclass(frozen=True)
class Route:
    distance_miles: float
    duration_seconds: float
    # GeoJSON order: [longitude, latitude]
    coordinates: list


def get_route(start, end):
    """Return (Route, made_external_call) for two Locations."""
    points = f"{start.longitude:.5f},{start.latitude:.5f};" \
             f"{end.longitude:.5f},{end.latitude:.5f}"
    cache_key = "route:v1:" + points.replace(",", "_").replace(";", "__")

    cached = cache.get(cache_key)
    if cached:
        return Route(**cached), False

    engine = settings.FUEL_ENGINE

    try:
        response = _session.get(
            f"{engine['OSRM_URL']}/route/v1/driving/{points}",
            params={"overview": "full", "geometries": "geojson"},
            headers={"User-Agent": engine["USER_AGENT"]},
            timeout=engine["HTTP_TIMEOUT_SECONDS"],
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ExternalServiceError(
            f"Routing service unavailable: {exc}"
        ) from exc

    if data.get("code") in {"NoRoute", "NoSegment"}:
        raise RouteNotFound("No drivable route between these locations.")

    if data.get("code") != "Ok" or not data.get("routes"):
        raise ExternalServiceError(
            f"Routing failed: {data.get('message') or data.get('code')}"
        )

    best = data["routes"][0]
    route = Route(
        distance_miles=best["distance"] / METERS_PER_MILE,
        duration_seconds=best["duration"],
        coordinates=best["geometry"]["coordinates"],
    )
    cache.set(cache_key, route.__dict__)
    return route, True
