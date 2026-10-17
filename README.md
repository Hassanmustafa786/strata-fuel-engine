# Strata Fuel Engine

Plan a road trip between two US locations and get the route on a map, the most
cost-effective places to fuel up, and the total fuel cost.

- Vehicle: **500-mile range**, **10 mpg** (a 50-gallon tank).
- Fuel prices: the supplied dataset (6,967 truck stops).
- Map tiles and geocoding: OpenStreetMap / Nominatim. Routing: OSRM. All free.
- **One routing call per trip**, plus up to two geocoding calls. Results are cached,
  so a repeated trip makes no external calls and answers in about 150 ms.

```
backend/   Django 6.1 + Django REST Framework API (SQLite)
frontend/  React + Vite + Leaflet map UI
```

## Running it

Requires Python 3.13 and Node 22.

```bash
# Backend: http://127.0.0.1:8000
cd backend
python -m venv ../.venv && ../.venv/Scripts/activate   # macOS/Linux: source ../.venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver

# Frontend: http://localhost:5173
cd frontend
npm install
npm run dev
```

Then load the stations (once). Put the supplied price file at
`backend/data/fuel_prices.csv` and run:

```bash
cd backend
python seeder/seed_fuel_stations.py --file data/fuel_prices.csv --prune
python seeder/geocode_stations.py
```

Both `backend/data/` and `*.sqlite3` are git-ignored, so the dataset and database are
not in the repository.

Without the frontend, open the server-rendered map:
<http://127.0.0.1:8000/api/v1/trips/map/?origin=Chicago,IL&destination=Denver,CO>

## API

### `POST /api/v1/trips/plan/`

```json
{ "origin": "New York, NY", "destination": "Los Angeles, CA" }
```

Locations are free text (city, address, landmark) or `"latitude, longitude"`.
Coordinates skip geocoding entirely. Both must be in the USA.

Response (abridged):

```json
{
  "origin":      { "label": "New York, United States", "latitude": 40.71, "longitude": -74.01 },
  "destination": { "label": "Los Angeles, ...", "latitude": 34.05, "longitude": -118.24 },
  "route": {
    "distance_miles": 2794.0,
    "duration_seconds": 179340,
    "geometry": { "type": "LineString", "coordinates": [[-74.01, 40.71], "..."] }
  },
  "vehicle": { "max_range_miles": 500, "mpg": 10, "tank_gallons": 50.0 },
  "fuel_plan": {
    "feasible": true,
    "message": "",
    "stops": [
      {
        "order": 1,
        "type": "origin",
        "station": { "id": 812, "name": "7-ELEVEN #40084", "city": "Palisades Park", "state": "NJ",
                     "price_per_gallon": 3.099, "latitude": 40.85, "longitude": -73.99,
                     "location_precision": "city", "...": "..." },
        "route_mile": 0.0,
        "distance_from_origin_miles": 9.3,
        "fuel_on_arrival_gallons": 0.0,
        "gallons": 38.7,
        "cost": 119.78
      }
    ],
    "total_gallons": 279.4,
    "total_cost": 863.66,
    "currency": "USD"
  },
  "corridor_stations": ["every station considered, for drawing on the map"],
  "assumptions": { "start_fuel": "...", "refuelling": "...", "detours": "..." },
  "meta": { "external_calls": { "geocoding": 2, "routing": 1 }, "elapsed_ms": 1840 }
}
```

`route.geometry` is GeoJSON (`[longitude, latitude]`), ready for any map library.

| Status | When |
|---|---|
| 200 | Plan returned. Check `fuel_plan.feasible`: `false` means the route has a stretch longer than 500 miles without a station. |
| 400 | Missing field, same origin and destination, location not found, or not in the USA. |
| 422 | No drivable route (e.g. Hawaii to the mainland). |
| 502 | Geocoding or routing service unavailable. |

### Other endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/trips/map/?origin=…&destination=…` | The same plan rendered as an HTML map page. |
| `GET /api/v1/fuel-stations/?state=TX&geocoded=true&ordering=retail_price` | Paginated station list. |
| `GET /api/v1/health/` | Station and geocoded counts. |

A Postman collection is in [docs/strata-fuel-engine.postman_collection.json](docs/strata-fuel-engine.postman_collection.json).

## How a trip is planned

1. **Geocode** origin and destination with Nominatim. Results outside the USA are
   rejected. Cached for 30 days.
2. **Route** with a single OSRM request for the full road geometry. Cached.
3. **Find stations along the route.** Stations are held in memory as numpy arrays
   (reloaded only when the table changes). A bounding-box filter, then a vectorised
   distance-to-route check on a projection centred on the route, keeps every station
   within 10 miles of the road and records how far along the route it is.
4. **Starting fuel.** The tank starts empty and is filled at the cheapest station
   within 30 miles of the origin, so every gallon of the trip is paid for and short
   trips are not reported as free.
5. **Choose stops** with an exact dynamic program
   ([fuel_optimizer.py](backend/apis/trips/services/fuel_optimizer.py)). An optimal plan
   only ever fills the tank (when the next stop is pricier) or buys just enough to
   reach the next stop (when it is cheaper) (Khuller, Malekian & Mestre, *To fill or not
   to fill*, 2007). The program minimises **fuel cost + $10 per stop**, because the
   absolutely cheapest plan makes 12–22 stops on long trips, some to buy one gallon and
   save cents. The $10 penalty cuts that to 5–8 stops for about 1% more fuel cost.
6. **Total cost** = Σ gallons bought × that station's price. Total gallons always equal
   route miles ÷ 10.

Typical timings: about 150–400 ms when the trip is cached. A new trip usually takes
1–3 s more, almost all of it the external calls. It can take over 10 s when the public
OSRM server is busy.

### Assumptions and limits

- Prices are the supplied dataset, not live prices.
- Fuel can be bought in any amount. A station counts as "on the route" up to 10 miles
  away; the detour itself is not costed.
- Most station addresses are highway exits ("I-44, EXIT 283 & US-69"), which free
  geocoders match poorly or wrongly. Stations are therefore placed at their **city's
  centre** (US Census Gazetteer). 464 have verified address-level coordinates. The API
  marks each station's `location_precision` as `city` or `address`.
- Canadian stations in the dataset (102) are excluded; the planner is US-only.
- The public OSRM and Nominatim servers are best-effort demo services. Set `OSRM_URL` /
  `NOMINATIM_URL` to self-hosted instances for production.

Tunable values live in `FUEL_ENGINE` in [settings.py](backend/config/settings.py).

## Data pipeline

```bash
cd backend
python seeder/seed_fuel_stations.py --file data/fuel_prices.csv --prune   # import / sync prices
python seeder/geocode_stations.py                                        # add coordinates
```

See [backend/seeder/README.md](backend/seeder/README.md) for details.

## Tests

```bash
cd backend && python manage.py test apis
```

These cover the optimiser (including a randomised cross-check against the textbook
greedy algorithm on 300 routes), station search, the API (with external services
mocked), and input validation.

The notebook [backend/notebooks/geopy_practice_sqlite3.ipynb](backend/notebooks/geopy_practice_sqlite3.ipynb)
walks through each step with the real data and compares the optimiser with the naive
"cheapest station within range" rule.
