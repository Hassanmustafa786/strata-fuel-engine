# Seeders

Run from `backend/`, in this order.

## 1. Import prices: `seed_fuel_stations.py`

```bash
python seeder/seed_fuel_stations.py --file data/fuel_prices.csv --prune
```

- Reads `.csv`, `.xlsx` or `.xls`. Columns: `OPIS Truckstop ID`, `Truckstop Name`,
  `Address`, `City`, `State`, `Rack ID`, `Retail Price`, and optionally `latitude`,
  `longitude`, `geocode_status`.
- Upserts on station identity (name, address, city, state, rack ID). Duplicate rows
  for one station: the last row in the file wins.
- Rows **with** coordinates in the file overwrite the database's coordinates. Rows
  **without** them keep whatever the database already has, so re-importing prices
  never wipes geocoding.
- `--prune` deletes stations that are no longer in the file.
- Rejects the whole import if any row is invalid (bad price, state, coordinates…).

## 2. Add coordinates: `geocode_stations.py`

```bash
python seeder/geocode_stations.py                 # gazetteer + Nominatim fallback
python seeder/geocode_stations.py --skip-nominatim # offline only
```

Most addresses are highway exits, which street geocoders mis-match (480 earlier
address matches included 16 that were hundreds of km off). So:

1. Each station's city is matched to the **US Census Gazetteer** (places, then county
   subdivisions). The files are downloaded once to `data/gazetteer/`. This is offline
   and covers about 96% of cities.
2. Cities not in the gazetteer get one rate-limited **Nominatim** lookup each, cached
   in `data/gazetteer/nominatim_cache.json`. About 140 cities, roughly 3 minutes the
   first time and instant afterwards.
3. Existing address-level coordinates (`success`) are kept if they are within 40 km
   of the city, and replaced by the city centre otherwise.

`geocode_status` values: `success` (address-level, verified), `approximate` (city
centre), `not_found`, `error`, or empty (not attempted; Canadian stations).

Safe to re-run at any time; always run it after an import.
