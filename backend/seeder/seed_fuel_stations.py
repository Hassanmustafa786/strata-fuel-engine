
import argparse
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import django
import pandas as pd
from django.db import transaction

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apis.fuel_stations.models import FuelStation  # noqa: E402


COLUMN_MAP = {
    "OPIS Truckstop ID": "opis_truckstop_id",
    "Truckstop Name": "name",
    "Address": "address",
    "City": "city",
    "State": "state",
    "Rack ID": "rack_id",
    "Retail Price": "retail_price",
}

GEOCODE_COLUMNS = ["latitude", "longitude", "geocode_status"]

GEOCODE_STATUSES = set(FuelStation.GeocodeStatus.values)

# Stay well under SQLite's limit on bound parameters per query.
DELETE_CHUNK_SIZE = 500

IDENTITY_FIELDS = [
    "name", "address", "city", "state", "rack_id"
]


def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def parse_integer(value, field, row_number, nullable=False):
    if pd.isna(value) or clean_text(value) == "":
        if nullable:
            return None
        raise ValueError(f"Row {row_number}: missing {field}")

    number = Decimal(str(value))
    if number != number.to_integral_value():
        raise ValueError(f"Row {row_number}: invalid {field}: {value}")

    return int(number)


def parse_coordinate(value, field, limit):
    if pd.isna(value) or clean_text(value) == "":
        return None

    number = float(value)
    if not -limit <= number <= limit:
        raise ValueError(f"{field} out of range: {value}")

    return number


def parse_geocode_status(value):
    status = clean_text(value).lower()
    if not status:
        return None

    if status not in GEOCODE_STATUSES:
        raise ValueError(f"Invalid geocode_status: {value}")

    return status


def load_dataframe(file_path):
    suffix = file_path.suffix.lower()

    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)

    if suffix == ".csv":
        return pd.read_csv(file_path)

    raise ValueError("Supported formats: .xlsx, .xls, .csv")


def main():
    parser = argparse.ArgumentParser(
        description="Import fuel stations from Excel or CSV."
    )
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete stations that are no longer present in the file.",
    )
    args = parser.parse_args()

    if not args.file.is_file():
        parser.error(f"Dataset not found: {args.file}")

    if args.batch_size < 1:
        parser.error("--batch-size must be greater than zero")

    df = load_dataframe(args.file)
    missing = set(COLUMN_MAP) - set(df.columns)

    if missing:
        parser.error(f"Missing required columns: {sorted(missing)}")

    # Geocode columns are optional so older datasets can still be imported.
    for column in GEOCODE_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA

    columns = list(COLUMN_MAP) + GEOCODE_COLUMNS
    df = df[columns].copy()
    df = df.drop_duplicates(subset=columns)

    stations = []
    errors = []

    for index, row in df.iterrows():
        row_number = index + 2

        try:
            name = clean_text(row["Truckstop Name"])
            address = clean_text(row["Address"])
            city = clean_text(row["City"])
            state = clean_text(row["State"]).upper()

            if not all([name, address, city]) or len(state) != 2:
                raise ValueError("Invalid station name, address, city or state")

            price = Decimal(str(row["Retail Price"]))

            if not price.is_finite() or price <= 0:
                raise ValueError("Retail Price must be positive and finite")

            latitude = parse_coordinate(row["latitude"], "latitude", 90)
            longitude = parse_coordinate(row["longitude"], "longitude", 180)
            geocode_status = parse_geocode_status(row["geocode_status"])

            if (latitude is None) != (longitude is None):
                raise ValueError("latitude and longitude must both be set")

            if geocode_status == FuelStation.GeocodeStatus.SUCCESS and latitude is None:
                raise ValueError("geocode_status is success but coordinates are missing")

            stations.append(
                FuelStation(
                    opis_truckstop_id=parse_integer(
                        row["OPIS Truckstop ID"],
                        "OPIS Truckstop ID",
                        row_number,
                    ),
                    name=name,
                    address=address,
                    city=city,
                    state=state,
                    rack_id=parse_integer(
                        row["Rack ID"], "Rack ID", row_number,
                        nullable=True,
                    ),
                    retail_price=price,
                    latitude=latitude,
                    longitude=longitude,
                    geocode_status=geocode_status,
                )
            )
        except (ValueError, InvalidOperation, TypeError) as exc:
            errors.append(f"Row {row_number}: {exc}")

    if errors:
        raise ValueError(
            f"Import aborted: {len(errors)} invalid rows.\n"
            + "\n".join(errors[:20])
        )

    unique_stations = {}

    for station in stations:
        key = tuple(
            getattr(station, field) for field in IDENTITY_FIELDS
        )
        unique_stations[key] = station

    stations = list(unique_stations.values())

    # Rows without coordinates in the file keep whatever the database
    # already has (e.g. from seeder/geocode_stations.py), so a stale
    # "not_found" in the file never wipes coordinates found since.
    base_fields = ["opis_truckstop_id", "retail_price", "updated_at"]
    geocoded = [s for s in stations if s.latitude is not None]
    not_geocoded = [s for s in stations if s.latitude is None]

    with transaction.atomic():
        for group, update_fields in [
            (geocoded, base_fields + GEOCODE_COLUMNS),
            (not_geocoded, base_fields),
        ]:
            FuelStation.objects.bulk_create(
                group,
                batch_size=args.batch_size,
                update_conflicts=True,
                unique_fields=IDENTITY_FIELDS,
                update_fields=update_fields,
            )

        pruned = 0
        if args.prune:
            keep = set(unique_stations)
            stale_ids = [
                pk
                for pk, *key in FuelStation.objects.values_list(
                    "pk", *IDENTITY_FIELDS
                )
                if tuple(key) not in keep
            ]
            for start in range(0, len(stale_ids), DELETE_CHUNK_SIZE):
                chunk = stale_ids[start:start + DELETE_CHUNK_SIZE]
                deleted, _ = FuelStation.objects.filter(pk__in=chunk).delete()
                pruned += deleted

    print(f"Processed {len(stations)} distinct station records.")
    if args.prune:
        print(f"Removed {pruned} stations not present in the file.")
    print(f"Database station count: {FuelStation.objects.count()}")
    print(
        "Geocoded stations: "
        f"{FuelStation.objects.filter(geocode_status='success').count()}"
    )


if __name__ == "__main__":
    main()