"""Find fuel stations near a route and how far along it they are."""
import threading
from dataclasses import dataclass

import numpy as np
import shapely
from django.db.models import Count, Max
from pyproj import Transformer

from apis.fuel_stations.models import FuelStation

METERS_PER_MILE = 1609.344
MILES_PER_DEGREE_LAT = 69.0
EARTH_RADIUS_MILES = 3958.8

# Route detail finer than this changes station distances by under a
# kilometre, which is negligible against a corridor measured in miles.
SIMPLIFY_METERS = 500

STATION_FIELDS = [
    "id", "opis_truckstop_id", "name", "address", "city", "state",
    "retail_price", "latitude", "longitude", "geocode_status",
]


@dataclass(frozen=True)
class StationIndex:
    signature: tuple
    latitude: np.ndarray
    longitude: np.ndarray
    stations: list  # dicts, aligned with the arrays


@dataclass(frozen=True)
class Candidate:
    station: dict
    route_mile: float
    distance_from_route_miles: float

    @property
    def price(self):
        return self.station["retail_price"]


_index = None
_index_lock = threading.Lock()


def get_station_index():
    """Geocoded stations, cached in memory until the table changes."""
    global _index
    queryset = FuelStation.objects.filter(
        latitude__isnull=False, longitude__isnull=False
    )
    signature = tuple(
        queryset.aggregate(n=Count("id"), updated=Max("updated_at")).values()
    )

    with _index_lock:
        if _index is None or _index.signature != signature:
            _index = _build_index(queryset, signature)
        return _index


def _build_index(queryset, signature):
    # Duplicate listings and stations placed at the same city centroid
    # share coordinates; only the cheapest of them can be worth a stop.
    seen = set()
    stations = []

    for row in queryset.order_by("retail_price", "id").values(*STATION_FIELDS):
        key = (round(row["latitude"], 5), round(row["longitude"], 5))
        if key in seen:
            continue
        seen.add(key)
        row["retail_price"] = float(row["retail_price"])
        stations.append(row)

    return StationIndex(
        signature=signature,
        latitude=np.array([s["latitude"] for s in stations], dtype=float),
        longitude=np.array([s["longitude"] for s in stations], dtype=float),
        stations=stations,
    )


def find_stations_near_route(index, coordinates, route_miles, corridor_miles):
    """
    Stations within `corridor_miles` of the route, sorted by route mile.

    Positions along the route are scaled to the router's distance so they
    are consistent with the trip length used for fuel calculations.
    """
    route = np.asarray(coordinates, dtype=float)
    if len(route) < 2 or not index.stations:
        return []

    # Cheap bounding-box filter before any geometry work.
    max_abs_lat = min(np.abs(route[:, 1]).max(), 80)
    lat_margin = corridor_miles / MILES_PER_DEGREE_LAT
    lon_margin = lat_margin / np.cos(np.radians(max_abs_lat))
    in_box = (
        (index.longitude >= route[:, 0].min() - lon_margin)
        & (index.longitude <= route[:, 0].max() + lon_margin)
        & (index.latitude >= route[:, 1].min() - lat_margin)
        & (index.latitude <= route[:, 1].max() + lat_margin)
    )
    positions = np.flatnonzero(in_box)
    if positions.size == 0:
        return []

    # Azimuthal equidistant projection centred on the route keeps
    # distances in metres accurate for any US trip, including AK/HI.
    to_xy = _projection_for(route)
    route_x, route_y = to_xy.transform(route[:, 0], route[:, 1])
    line = shapely.LineString(np.column_stack([route_x, route_y]))
    line = line.simplify(SIMPLIFY_METERS, preserve_topology=False)

    station_x, station_y = to_xy.transform(
        index.longitude[positions], index.latitude[positions]
    )
    points = shapely.points(station_x, station_y)
    distances = shapely.distance(line, points)
    near = distances <= corridor_miles * METERS_PER_MILE

    along = shapely.line_locate_point(line, points[near])
    scale = route_miles / (line.length / METERS_PER_MILE)

    candidates = [
        Candidate(
            station=index.stations[position],
            route_mile=float(meters / METERS_PER_MILE * scale),
            distance_from_route_miles=float(distance / METERS_PER_MILE),
        )
        for position, meters, distance in zip(
            positions[near], along, distances[near]
        )
    ]
    candidates.sort(key=lambda candidate: candidate.route_mile)
    return candidates


def stations_within(index, latitude, longitude, radius_miles):
    """(station, distance_miles) pairs within a straight-line radius."""
    if not index.stations:
        return []

    lat1, lon1 = np.radians(latitude), np.radians(longitude)
    lat2, lon2 = np.radians(index.latitude), np.radians(index.longitude)
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    distances = 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))

    return [
        (index.stations[position], float(distances[position]))
        for position in np.flatnonzero(distances <= radius_miles)
    ]


def _projection_for(route):
    lon0 = (route[:, 0].min() + route[:, 0].max()) / 2
    lat0 = (route[:, 1].min() + route[:, 1].max()) / 2
    return Transformer.from_crs(
        "EPSG:4326",
        f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m",
        always_xy=True,
    )
