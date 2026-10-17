"""Resolve a free-text US location to coordinates with Nominatim."""
import hashlib
import re
import threading
import time
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

from .errors import ExternalServiceError, LocationNotFound

COORDINATES = re.compile(
    r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$"
)

# (south, west, north, east) for the contiguous US, Alaska and Hawaii.
US_BOUNDS = [
    (24.4, -125.0, 49.5, -66.9),
    (51.2, -180.0, 71.5, -129.9),
    (18.9, -160.3, 22.3, -154.8),
]

# Nominatim's usage policy allows at most one request per second.
_rate_lock = threading.Lock()
_last_request_at = 0.0

_session = requests.Session()


@dataclass(frozen=True)
class Location:
    label: str
    latitude: float
    longitude: float


def in_usa(latitude, longitude):
    return any(
        south <= latitude <= north and west <= longitude <= east
        for south, west, north, east in US_BOUNDS
    )


def geocode(query):
    """
    Return (Location, made_external_call).

    "lat, lon" input is used as-is, which saves the external call.
    """
    query = query.strip()
    match = COORDINATES.match(query)

    if match:
        latitude, longitude = float(match[1]), float(match[2])
        if not in_usa(latitude, longitude):
            raise LocationNotFound(f"{query} is not inside the USA.")
        return Location(query, latitude, longitude), False

    normalized = " ".join(query.casefold().split())
    cache_key = "geocode:v2:" + hashlib.sha1(normalized.encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached:
        return Location(**cached), False

    hit = _search(query)
    location = Location(
        label=hit["display_name"],
        latitude=float(hit["lat"]),
        longitude=float(hit["lon"]),
    )
    cache.set(cache_key, location.__dict__)
    return location, True


def _search(query):
    global _last_request_at
    engine = settings.FUEL_ENGINE

    with _rate_lock:
        wait = 1.0 - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)

        try:
            response = _session.get(
                f"{engine['NOMINATIM_URL']}/search",
                # Searching worldwide (not countrycodes=us) lets "Toronto, ON"
                # resolve to Canada and be rejected, instead of matching
                # some "Toronto Court" in the US.
                params={
                    "q": query,
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "limit": 5,
                },
                headers={"User-Agent": engine["USER_AGENT"]},
                timeout=engine["HTTP_TIMEOUT_SECONDS"],
            )
            response.raise_for_status()
            results = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ExternalServiceError(
                f"Geocoding service unavailable: {exc}"
            ) from exc
        finally:
            _last_request_at = time.monotonic()

    if not results:
        raise LocationNotFound(
            f"Could not find '{query}'. "
            "Try a city and state, e.g. 'Dallas, TX'."
        )

    for result in results:
        if result.get("address", {}).get("country_code") == "us":
            return result

    raise LocationNotFound(f"'{query}' is not in the USA.")
