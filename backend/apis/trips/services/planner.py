"""Plan a trip: geocode, route once, pick fuel stops, total the cost."""
import time

import numpy as np
import shapely
from django.conf import settings

from .fuel_optimizer import FuelOption, plan_purchases
from .geocoding import geocode
from .routing import get_route
from .station_search import (
    find_stations_near_route,
    get_station_index,
    stations_within,
)

# ~30 m; keeps the drawn route faithful while shrinking the payload.
DISPLAY_SIMPLIFY_DEGREES = 0.0003


def plan_trip(origin, destination):
    started = time.perf_counter()
    engine = settings.FUEL_ENGINE
    max_range = engine["MAX_RANGE_MILES"]
    mpg = engine["MPG"]

    start, start_called = geocode(origin)
    end, end_called = geocode(destination)
    route, route_called = get_route(start, end)

    index = get_station_index()
    candidates = find_stations_near_route(
        index, route.coordinates, route.distance_miles,
        engine["CORRIDOR_MILES"],
    )

    options = [
        FuelOption(candidate.route_mile, candidate.price, candidate)
        for candidate in candidates
    ]

    # The tank starts empty: the first purchase is the cheapest station
    # close to the origin, so every gallon burned is paid for.
    near_origin = stations_within(
        index, start.latitude, start.longitude,
        engine["ORIGIN_RADIUS_MILES"],
    )
    if near_origin:
        station, distance = min(
            near_origin, key=lambda pair: (pair[0]["retail_price"], pair[1])
        )
        options.append(
            FuelOption(0.0, station["retail_price"], ("origin", station, distance))
        )

    plan = plan_purchases(
        options, route.distance_miles, max_range, mpg,
        stop_penalty=engine["STOP_PENALTY_DOLLARS"],
    )

    message = plan.message
    if not near_origin:
        message = (
            f"No fuel station within {engine['ORIGIN_RADIUS_MILES']} "
            "miles of the origin to start the trip from."
        )

    return {
        "origin": _location(start),
        "destination": _location(end),
        "route": {
            "distance_miles": round(route.distance_miles, 1),
            "duration_seconds": round(route.duration_seconds),
            "geometry": {
                "type": "LineString",
                "coordinates": _display_coordinates(route.coordinates),
            },
        },
        "vehicle": {
            "max_range_miles": max_range,
            "mpg": mpg,
            "tank_gallons": max_range / mpg,
        },
        "fuel_plan": {
            "feasible": plan.feasible and bool(near_origin),
            "message": message,
            "stops": [
                _stop(order, purchase)
                for order, purchase in enumerate(plan.purchases, start=1)
            ],
            "total_gallons": round(plan.total_gallons, 2),
            "total_cost": round(plan.total_cost, 2),
            "currency": "USD",
            "price_source": "supplied fuel price dataset",
        },
        "corridor_stations": [
            {
                **_station(candidate.station),
                "route_mile": round(candidate.route_mile, 1),
            }
            for candidate in candidates
        ],
        "assumptions": {
            "start_fuel": (
                "Tank starts empty and is filled at the cheapest station "
                f"within {engine['ORIGIN_RADIUS_MILES']} miles of the origin."
            ),
            "corridor_miles": engine["CORRIDOR_MILES"],
            "refuelling": (
                "Buy only the fuel needed to reach the next cheaper "
                "station; fill up when the next stations are pricier. "
                f"Stops saving less than ${engine['STOP_PENALTY_DOLLARS']} "
                "are skipped."
            ),
            "detours": "Driving to stations off the route is not costed.",
        },
        "meta": {
            "external_calls": {
                "geocoding": int(start_called) + int(end_called),
                "routing": int(route_called),
            },
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        },
    }


def _location(location):
    return {
        "label": location.label,
        "latitude": location.latitude,
        "longitude": location.longitude,
    }


def _station(station):
    return {
        "id": station["id"],
        "opis_truckstop_id": station["opis_truckstop_id"],
        "name": station["name"],
        "address": station["address"],
        "city": station["city"],
        "state": station["state"],
        "price_per_gallon": station["retail_price"],
        "latitude": station["latitude"],
        "longitude": station["longitude"],
        "location_precision": (
            "city" if station["geocode_status"] == "approximate"
            else "address"
        ),
    }


def _stop(order, purchase):
    option = purchase.option

    if isinstance(option.ref, tuple):
        _, station, distance = option.ref
        kind, offset = "origin", {"distance_from_origin_miles": round(distance, 1)}
    else:
        station = option.ref.station
        kind = "en_route"
        offset = {
            "distance_from_route_miles": round(
                option.ref.distance_from_route_miles, 1
            )
        }

    return {
        "order": order,
        "type": kind,
        "station": _station(station),
        "route_mile": round(option.route_mile, 1),
        **offset,
        "fuel_on_arrival_gallons": round(purchase.fuel_on_arrival_gallons, 2),
        "gallons": round(purchase.gallons, 2),
        "cost": round(purchase.cost, 2),
    }


def _display_coordinates(coordinates):
    if len(coordinates) < 2:
        return coordinates
    line = shapely.LineString(np.asarray(coordinates)).simplify(
        DISPLAY_SIMPLIFY_DEGREES, preserve_topology=False
    )
    return np.round(shapely.get_coordinates(line), 5).tolist()
