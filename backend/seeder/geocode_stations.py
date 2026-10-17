"""
Populate latitude/longitude for fuel stations.

Most station addresses are highway exits ("I-44, EXIT 283 & US-69"),
which street geocoders match poorly or wrongly. Stations are therefore
located at their city's centroid from the US Census Gazetteer files
(offline, no rate limits). Cities missing from the gazetteer fall back
to one rate-limited Nominatim lookup per distinct city.

Existing address-level coordinates are kept unless they are implausibly
far from the station's city, which indicates a wrong match.

Usage:
    python seeder/geocode_stations.py
    python seeder/geocode_stations.py --skip-nominatim
"""
import argparse
import json
import math
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import django
import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from apis.fuel_stations.models import FuelStation  # noqa: E402


GAZETTEER_DIR = BASE_DIR / "data" / "gazetteer"
GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2024_Gazetteer/2024_Gaz_{kind}_national.zip"
)
# Places (cities, towns, CDPs) win over county subdivisions (townships).
GAZETTEER_KINDS = ["place", "cousubs"]
NOMINATIM_CACHE = GAZETTEER_DIR / "nominatim_cache.json"

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA",
    "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX",
    "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}

# Existing coordinates further than this from the city are wrong matches.
MAX_CITY_DISTANCE_KM = 40

# Census names end with a lowercase legal descriptor, e.g.
# "Oklahoma City city", "Abanda CDP", "Nashville-Davidson
# metropolitan government (balance)".
NAME_SUFFIX = re.compile(r"(\s+(?:[a-z]+|CDP|CCD))+(\s*\(.*\))?$")

ABBREVIATIONS = {
    "st": "saint", "ste": "sainte", "ft": "fort",
    "mt": "mount", "pt": "point",
}

Status = FuelStation.GeocodeStatus


def city_key(name):
    """Normalize a city name so 'St. Louis' == 'Saint Louis' and
    'Du Bois' == 'DuBois'."""
    text = re.sub(r"[.'\-]", " ", str(name).casefold())
    return "".join(ABBREVIATIONS.get(word, word) for word in text.split())


def load_gazetteer():
    GAZETTEER_DIR.mkdir(parents=True, exist_ok=True)
    frames = []

    for priority, kind in enumerate(GAZETTEER_KINDS):
        path = GAZETTEER_DIR / f"2024_Gaz_{kind}_national.zip"

        if not path.is_file():
            print(f"Downloading Census gazetteer: {kind}")
            response = requests.get(
                GAZETTEER_URL.format(kind=kind), timeout=120
            )
            response.raise_for_status()
            path.write_bytes(response.content)

        with zipfile.ZipFile(path) as archive:
            with archive.open(archive.namelist()[0]) as handle:
                df = pd.read_csv(
                    handle, sep="\t", dtype=str, encoding="latin1"
                )

        df.columns = [column.strip() for column in df.columns]
        df["key"] = (
            df["NAME"].str.replace(NAME_SUFFIX, "", regex=True)
            .map(city_key)
        )
        df["priority"] = priority
        df["ALAND"] = pd.to_numeric(df["ALAND"], errors="coerce")
        frames.append(df)

    gazetteer = pd.concat(frames)
    # Same name twice in a state: prefer places, then the larger area.
    gazetteer = gazetteer.sort_values(
        ["priority", "ALAND"], ascending=[True, False]
    ).drop_duplicates(["USPS", "key"])

    return {
        (row.USPS, row.key): (float(row.INTPTLAT), float(row.INTPTLONG))
        for row in gazetteer.itertuples()
    }


def nominatim_lookup(cities):
    """Geocode (city, state) pairs, one request per second, cached."""
    cache = {}
    if NOMINATIM_CACHE.is_file():
        cache = json.loads(NOMINATIM_CACHE.read_text())

    engine = settings.FUEL_ENGINE
    session = requests.Session()
    session.headers["User-Agent"] = engine["USER_AGENT"]
    results = {}

    for number, (city, state) in enumerate(sorted(cities), start=1):
        key = f"{city}|{state}"

        if key not in cache:
            time.sleep(1.1)
            try:
                response = session.get(
                    f"{engine['NOMINATIM_URL']}/search",
                    params={
                        "city": city, "state": state,
                        "country": "us", "format": "jsonv2", "limit": 1,
                    },
                    timeout=engine["HTTP_TIMEOUT_SECONDS"],
                )
                response.raise_for_status()
                hits = response.json()
                cache[key] = (
                    [float(hits[0]["lat"]), float(hits[0]["lon"])]
                    if hits else None
                )
            except (requests.RequestException, ValueError) as exc:
                print(f"  {city}, {state}: {exc}")
                continue

            NOMINATIM_CACHE.write_text(json.dumps(cache, indent=1))
            print(f"  [{number}/{len(cities)}] {city}, {state}: "
                  f"{'found' if cache[key] else 'not found'}")

        results[(city, state)] = cache[key]

    return results


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2)
        * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371 * math.asin(math.sqrt(a))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--skip-nominatim", action="store_true",
        help="Only use the offline Census gazetteer.",
    )
    args = parser.parse_args()

    gazetteer = load_gazetteer()
    stations = list(FuelStation.objects.filter(state__in=US_STATES))

    unmatched = {
        (station.city, station.state)
        for station in stations
        if (station.state, city_key(station.city)) not in gazetteer
    }
    print(f"US stations: {len(stations)}")
    print(f"Cities missing from gazetteer: {len(unmatched)}")

    fallback = {}
    if unmatched and not args.skip_nominatim:
        print("Looking up missing cities with Nominatim...")
        fallback = nominatim_lookup(unmatched)

    counts = {"kept": 0, "corrected": 0, "approximate": 0, "not_found": 0}
    changed = []
    now = timezone.now()

    for station in stations:
        centroid = gazetteer.get((station.state, city_key(station.city)))
        if centroid is None:
            centroid = fallback.get((station.city, station.state))

        has_exact = (
            station.geocode_status == Status.SUCCESS
            and station.latitude is not None
        )

        if has_exact and (
            centroid is None
            or haversine_km(station.latitude, station.longitude, *centroid)
            <= MAX_CITY_DISTANCE_KM
        ):
            counts["kept"] += 1
            continue

        if centroid is None:
            values = (None, None, Status.NOT_FOUND)
            counts["not_found"] += 1
        else:
            values = (centroid[0], centroid[1], Status.APPROXIMATE)
            counts["corrected" if has_exact else "approximate"] += 1

        current = (station.latitude, station.longitude, station.geocode_status)
        if current != values:
            station.latitude, station.longitude, station.geocode_status = values
            station.updated_at = now
            changed.append(station)

    with transaction.atomic():
        FuelStation.objects.bulk_update(
            changed,
            ["latitude", "longitude", "geocode_status", "updated_at"],
            batch_size=500,
        )

    print(f"Kept address-level coordinates: {counts['kept']}")
    print(f"Replaced wrong address matches: {counts['corrected']}")
    print(f"Located at city centroid: {counts['approximate']}")
    print(f"Still not found: {counts['not_found']}")
    print(f"Rows updated: {len(changed)}")


if __name__ == "__main__":
    main()
