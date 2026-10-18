# Strata Fuel Engine

## Project Documentation

**Project type:** Backend Django Engineer assessment\
**Repository:** `strata-fuel-engine`\
**Stack:** Django 6.1 + Django REST Framework + SQLite (backend), React + Vite +
Leaflet (frontend)\
**Data:** 6,967 truck-stop fuel prices; 6,848 of the 6,855 US stations have
coordinates

**What it does:** you enter a start and a finish anywhere in the USA. The app
returns the driving route on a map, where to fuel up so the trip costs as little
as possible, how much fuel to buy at each stop, and the total fuel cost. The
vehicle has a 500-mile range and does 10 miles per gallon.

------------------------------------------------------------------------

## 1. Key Points for the Presentation

If you only remember six things, remember these:

1. **One routing call per trip.** Each new trip makes 1 call to OSRM (routing)
   and at most 2 calls to Nominatim (turning the start and finish into
   coordinates). Results are cached, so a repeated trip makes **zero** external
   calls and answers in about 150 ms.
2. **The supplied data had no coordinates, and the addresses are hard to
   geocode.** The original CSV only had names, addresses, cities, states and
   prices. Addresses look like `I-44, EXIT 283 & US-69`, which free geocoders
   cannot place reliably. An earlier attempt with the `geopy` library (Nominatim)
   found coordinates for only 480 stations, and 16 of those were wrong by
   hundreds of kilometres. We placed each station at the centre of its town
   using the free **US Census Gazetteer** (explained in section 4.2). Coverage
   went from 480 to 6,848 stations.
3. **The optimiser is exact, not a guess.** A proven result for this problem
   says that at every stop the best plan either fills the tank or buys just
   enough to reach the next stop. A dynamic program checks every such plan and
   picks the cheapest. It was cross-checked against the textbook algorithm on 300
   random routes.
4. **The cheapest plan is not the most practical one, so each stop "costs" $10.**
   The cheapest plan makes 12–22 stops on long trips, some to buy one gallon and
   save a few cents. Counting each stop as $10 brings that down to 5–8 stops for
   about 1% more fuel cost.
5. **Every gallon is paid for.** The tank starts empty and is filled at the
   cheapest station within 30 miles of the start. Total gallons always equal
   route miles ÷ 10. Short trips are not shown as free.
6. **Same response shape on every API.**
   `{"status": true/false, "message": "...", "data": {...}}`. Every API has its
   own `try`/`except`, and errors carry a clear `code`.

**Example results:**

| Trip | Distance | Fuel stops | Total fuel cost |
|---|---|---|---|
| Chicago, IL → Denver, CO | 1,004 mi | 3 | $292.90 |
| New York, NY → Los Angeles, CA | 2,794 mi | 7 | $863.66 |
| Miami, FL → Seattle, WA | 3,303 mi | 8 | $1,022.22 |
| Chicago, IL → Indianapolis, IN | 181 mi | 1 (start only) | $55.29 |

The stop count includes the fill-up at the start. Prices and routes come from the
supplied dataset and the public OSRM server, so results may change slightly if
either changes.

**Why the optimiser matters.** Results for Columbia, NJ → Montrose, CO (2,026
miles):

| Strategy | Stops | Fuel cost |
|---|---|---|
| Old notebook rule: "drive to the cheapest station within 500 miles" | 9 | $613.41 |
| Absolute cheapest plan | 12 | $599.23 |
| **What the API returns** (cheapest + $10 per stop) | **5** | **$603.20** |

------------------------------------------------------------------------

## 2. Assessment Requirements and How They Are Met

| Requirement | How it is met |
|---|---|
| Start and finish locations, both within the USA | Free text (`"Dallas, TX"`) or `"latitude, longitude"`. Locations outside the USA are rejected with a clear error. |
| Return a map of the route with the fuel stops | The API returns the route as GeoJSON plus the coordinates of every stop. The React frontend draws them on an OpenStreetMap map. |
| Optimal (cost-effective) fuel stops | An exact dynamic-programming optimiser (section 5.4). |
| 500-mile range, possibly several stops | The tank holds 500 miles of fuel (50 gallons). No leg in a plan exceeds it. |
| Total money spent at 10 mpg | `fuel_plan.total_cost` = Σ gallons bought × price at that station. |
| Use the supplied fuel prices | Imported into SQLite by `seed_fuel_stations.py`. |
| Free map and routing API | OSRM (routing), Nominatim (geocoding) and OpenStreetMap tiles (map). All free, no API key needed. |
| Latest stable Django | Django 6.1.2 with Django REST Framework 3.18. |
| Fast responses | About 150–400 ms for a cached trip, usually 1–3 s for a new one. |
| Few calls to the routing API (1 ideal, 2–3 acceptable) | Exactly 1 routing call per new trip, 0 when cached. |

------------------------------------------------------------------------

## 3. Architecture

```text
 Browser (React + Leaflet)                       Free external services
 ┌───────────────────────┐                       ┌──────────────────────────┐
 │ Trip form, map,       │  POST /trips/plan/    │ Nominatim: place → lat/lon│
 │ cost summary,         │ ────────────────────▶ │ OSRM: driving route       │
 │ stop list             │ ◀──────────────────── │ OSM tiles: map background │
 └───────────────────────┘    JSON plan          └──────────────────────────┘
                                   │                        ▲
                                   ▼                        │ max 3 calls, cached
 Django REST API ──────────────────────────────────────────┘
   trips/views.py        validate input, build the response
   services/planner.py   runs the steps below in order
     1. geocoding.py       start/finish → coordinates          (cached 30 days)
     2. routing.py         one OSRM request for the full route  (cached)
     3. station_search.py  stations within 10 miles of the route
     4. fuel_optimizer.py  where to stop and how much to buy
   SQLite                  6,967 stations with price + coordinates
```

The external calls and the optimiser live in `services/`, not in the views, so
each part can be tested on its own. The optimiser is plain Python with no Django
dependency, which is why the notebook can use it directly.

### Request flow for one trip

1. The frontend sends `{"origin": "...", "destination": "..."}` once.
2. **Geocode** the start and finish with Nominatim. Results outside the USA are
   rejected. Coordinates typed by the user skip this step.
3. **Route:** one OSRM request returns the full road geometry, the distance and
   the drive time.
4. **Find stations along the route.** All geocoded stations are kept in memory.
   Stations more than 10 miles from the road are dropped, and the rest are
   ordered by how far along the route they are.
5. **Starting fuel:** pick the cheapest station within 30 miles of the start.
6. **Optimise:** decide where to stop and how much to buy at each stop.
7. **Respond** with the route, the stops, the totals, the stations considered,
   the assumptions, and how many external calls were made.

------------------------------------------------------------------------

## 4. Data

### 4.1 The fuel price dataset

`backend/data/fuel_prices.csv`: 8,151 rows, which reduce to **6,967 distinct
stations**. Prices range from $2.69 to $6.40 per gallon, averaging $3.44.

**As supplied**, the file has 7 columns and **no coordinates**: OPIS Truckstop
ID, Truckstop Name, Address, City, State, Rack ID, Retail Price.

**Columns added during the project:** `latitude`, `longitude` and
`geocode_status` were added to the CSV by hand, as part of a first attempt to
find coordinates with the `geopy` library (notebook
`notebooks/geopy_practice.ipynb`, using the Nominatim geocoder). That attempt is
described in section 4.2. The import script treats these three columns as
optional, so both the original 7-column file and the extended file can be
imported.

- **Station identity** is name + address + city + state + rack ID. The OPIS ID
  alone is not unique: the source has the same ID on different station records.
- **Duplicate rows** for the same station: the last row in the file wins.
- **112 stations are in Canada** (provinces like ON, AB, BC). The planner is
  US-only, so they are not geocoded and never appear in plans.

### 4.2 What is the Gazetteer, and why do we need it?

**The problem.** To know which stations are near a route, every station needs
coordinates (latitude and longitude). But the addresses are highway descriptions
like `I-44, EXIT 283 & US-69, Big Cabin, OK`, not street addresses.

**First attempt: `geopy` with Nominatim.** Each address was sent to the free
Nominatim geocoder through the `geopy` library, and the result was stored in the
new `latitude`, `longitude` and `geocode_status` columns (`success` or
`not_found`). This showed the limits of the approach:

- Most highway-exit addresses could not be found. Only **480** stations got
  coordinates, while hundreds were marked `not_found` and the rest were never
  reached.
- Some of the "successful" answers were badly wrong. For example, "I-70, EXIT
  438, Burlington, CO" was placed 2,366 km away. A check against town centres
  found **16** such wrong matches.
- It is slow. Nominatim allows 1 request per second, so all 6,967 addresses
  would take about 2 hours, and its usage policy discourages bulk jobs like
  this.

**The solution: the US Census Gazetteer.**

- A *gazetteer* is simply a geographical dictionary: a list of place names with
  their coordinates.
- The **US Census Bureau** publishes official, free Gazetteer files every year.
  They list every US city, town, village and township, with the coordinates of
  its centre.
- We use two of the 2024 files:

  | File | What it contains |
  |---|---|
  | `2024_Gaz_place_national.zip` | Cities, towns, villages and "census designated places", about 32,000 places |
  | `2024_Gaz_cousubs_national.zip` | County subdivisions, such as townships, about 36,000 entries. Used when a town is not in the places file. |

- For each station we look up its **city + state** in these files and use the
  town's centre as the station's location. This happens offline, takes seconds,
  and covers about 96% of the towns.

**Why the town centre is good enough.** Truck stops are at highway exits, usually
within a few miles of the town they are listed under. The planner looks for
stations within **10 miles** of the route, so a station placed at its town centre
is still matched to the right stretch of road. The API reports this honestly:
each station has `location_precision` set to `"city"` or `"address"`.

**The geocoding process** (`seeder/geocode_stations.py`):

1. Look up each station's town in the Gazetteer (places first, then townships).
   Names are normalised so that `St. Louis` matches `Saint Louis` and `Du Bois`
   matches `DuBois`.
2. For the ~140 towns not in the Gazetteer, ask Nominatim **once per town**, not
   once per station. It is rate-limited to 1 request per second, and the answers
   are saved so this never needs repeating.
3. Keep the coordinates found in the `geopy` attempt (`success`) only if they
   are within 40 km of the station's town. Otherwise replace them with the town
   centre. This fixed the 16 wrong matches and kept the other 464.

### 4.3 What is in the `backend/data/` folder?

| Path | What it is | Where it comes from |
|---|---|---|
| `fuel_prices.csv` | The fuel price dataset | Provided with the assessment (7 columns). `latitude`, `longitude` and `geocode_status` were added later during the `geopy` attempt. |
| `gazetteer/2024_Gaz_place_national.zip` | Census list of US cities/towns with coordinates | Downloaded automatically by `geocode_stations.py` the first time it runs |
| `gazetteer/2024_Gaz_cousubs_national.zip` | Census list of US townships with coordinates | Same as above |
| `gazetteer/nominatim_cache.json` | Saved Nominatim answers for the ~140 towns not in the Gazetteer | Written by `geocode_stations.py`, so re-runs are instant and make no calls |
| `.gitkeep` | Empty file that keeps the folder in Git | — |

Everything in `backend/data/` except `.gitkeep` is ignored by Git (see
`.gitignore`). The CSV is a private dataset, and the other files can be
regenerated at any time by running the seeders.

### 4.4 Geocoding results

| `geocode_status` | Stations | Meaning |
|---|---|---|
| `approximate` | 6,384 | Placed at the town centre from the Gazetteer/Nominatim |
| `success` | 464 | Address-level coordinates from the earlier `geopy` attempt, checked to be within 40 km of the town |
| `not_found` | 17 | 7 US stations whose town could not be found, plus 10 Canadian ones marked `not_found` in the `geopy` attempt |
| *(empty)* | 102 | Canadian stations, not geocoded |

**Result: 6,848 of 6,855 US stations (99.9%) can be used for planning.**

### 4.5 FuelStation model

Table `fuel_stations` (`apis/fuel_stations/models.py`):

| Field | Purpose |
|---|---|
| `opis_truckstop_id` | Source OPIS identifier (not unique) |
| `name`, `address`, `city`, `state` | Station details; `state` is a 2-letter code |
| `rack_id` | Rack identifier from the dataset |
| `retail_price` | Price per gallon (decimal, 5 places) |
| `latitude`, `longitude` | Coordinates; empty until geocoded |
| `geocode_status` | `success`, `approximate`, `not_found`, `error`, or empty |
| `created_at`, `updated_at` | Timestamps |

There is a unique constraint on (name, address, city, state, rack_id), plus
indexes on (state, price), (latitude, longitude) and `geocode_status`.

### 4.6 Loading the data

Run these from `backend/`, in this order:

```bash
python seeder/seed_fuel_stations.py --file data/fuel_prices.csv --prune
python seeder/geocode_stations.py
```

- **`seed_fuel_stations.py`** imports or updates prices (CSV or Excel).
  - It validates every row and rejects the whole file if any row is invalid.
  - It updates existing stations instead of duplicating them.
  - `--prune` deletes stations that are no longer in the file.
  - It never wipes coordinates that the database already has.
- **`geocode_stations.py`** adds coordinates as described in 4.2. It is safe to
  run again at any time; always run it after an import.

------------------------------------------------------------------------

## 5. How a Trip Is Planned

### 5.1 Finding stations along the route

- **In memory:** all geocoded stations are loaded once into memory as arrays.
  They are reloaded only when the table changes (detected by row count and last
  update time).
- **Quick pre-filter:** stations outside a box around the route, plus a 10-mile
  margin, are skipped.
- **Exact distance:** for the rest, the distance to the road is computed for all
  stations in one operation using `shapely`. The calculation uses a map
  projection centred on the route, so distances in metres are accurate anywhere
  in the US.
- **Position along the route:** each nearby station also gets a "route mile",
  scaled to OSRM's total distance so it matches the trip length.
- **Duplicates:** stations at identical coordinates (for example, several
  stations at one town centre) are reduced to the cheapest one.

### 5.2 Starting fuel

The tank starts **empty** and is filled at the **cheapest station within 30
miles** of the start, treated as route mile 0. This means:

- every gallon of the trip is paid for, and
- a trip under 500 miles still has a cost (one fill-up at the start).

### 5.3 The fuel model

- Tank: 500 miles of range = 50 gallons at 10 mpg.
- Fuel can be bought in any amount up to a full tank.
- `gallons used = miles ÷ 10`; `cost at a stop = gallons bought × that station's price`.
- `total cost = Σ cost at each stop`; total gallons always equal route miles ÷ 10.

### 5.4 The optimiser (`services/fuel_optimizer.py`)

**The key idea** (Khuller, Malekian & Mestre, *"To fill or not to fill: the gas
station problem"*, 2007): in the best plan, at every stop you do one of only two
things:

- **Fill the tank completely**, when the next stations are more expensive (buy
  cheap fuel while you can), or
- **Buy just enough to reach the next stop**, when it is cheaper (don't carry
  expensive fuel past a cheap station).

So when you arrive at a station, the fuel left in the tank is either zero or "a
full tank minus the drive from an earlier stop". That gives a small, fixed
number of situations at each station. A **dynamic program** walks the stations in
route order and keeps the cheapest way to reach each situation. At the
destination, the cheapest total wins.

**The $10 stop penalty.** On its own, the cheapest plan is impractical: it might
stop to buy 1 gallon because that station is 2 cents cheaper. So the program
minimises **fuel cost + $10 for every stop**. A stop is only made if it saves
more than $10. The reported cost is still the real fuel cost; the $10 only
affects which plan is chosen.

**If no plan is possible** (a stretch longer than 500 miles without a station),
the API still returns the route, with `fuel_plan.feasible = false` and a message
saying where the gap is.

**Correctness checks** (`apis/trips/tests.py`):

- Hand-made cases: short trips, cheaper station ahead, fill up, gaps that are too
  long.
- A randomised test on 300 routes comparing the cost with the textbook greedy
  algorithm, which is known to be optimal.
- A test that the stop penalty never increases the number of stops.

### 5.5 Assumptions and limits (say these openly)

- Prices are from the supplied dataset, not live.
- Most stations are located at their town centre, not the exact exit.
- Stations up to 10 miles from the road count as "on the route". The detour to
  reach them is not added to the cost.
- The start fill-up is treated as happening at route mile 0, even if that station
  is a few miles away.
- The public OSRM and Nominatim servers are free demo services with no uptime
  guarantee. Their URLs can be changed to self-hosted servers in `.env`.

------------------------------------------------------------------------

## 6. API

Base URL: `http://127.0.0.1:8000/api/v1`

### 6.1 Response format (all APIs)

Every API has its own `try`/`except` and returns the same shape:

```json
{ "status": true, "message": "Trip planned successfully.", "data": { } }
```

```json
{
  "status": false,
  "message": "Location not found.",
  "data": { "detail": "'Toronto, ON' is not in the USA.", "code": "location_not_found" }
}
```

On errors, `message` is a short summary and `data.detail` is the specific reason.
For validation errors, `data.detail` holds the field errors, e.g.
`{"destination": ["This field is required."]}`. A wrong HTTP method gets a 405 in
the same shape.

### 6.2 `POST /api/v1/trips/plan/`

Request:

```json
{ "origin": "Chicago, IL", "destination": "Denver, CO" }
```

`data` in the response (shortened):

```json
{
  "origin":      { "label": "Chicago, South Chicago Township, Cook County, Illinois, United States", "latitude": 41.88, "longitude": -87.63 },
  "destination": { "label": "Denver, Colorado, United States", "latitude": 39.74, "longitude": -104.99 },
  "route": {
    "distance_miles": 1004.3,
    "duration_seconds": 64152,
    "geometry": { "type": "LineString", "coordinates": [[-87.63, 41.88], "..."] }
  },
  "vehicle": { "max_range_miles": 500, "mpg": 10, "tank_gallons": 50.0 },
  "fuel_plan": {
    "feasible": true,
    "message": "",
    "stops": [
      {
        "order": 1,
        "type": "origin",
        "station": {
          "id": 123, "name": "Gulf", "address": "...", "city": "Bensenville", "state": "IL",
          "price_per_gallon": 3.059, "latitude": 41.95, "longitude": -87.94,
          "location_precision": "city"
        },
        "route_mile": 0.0,
        "distance_from_origin_miles": 17.4,
        "fuel_on_arrival_gallons": 0.0,
        "gallons": 19.92,
        "cost": 60.92
      }
    ],
    "total_gallons": 100.43,
    "total_cost": 292.90,
    "currency": "USD",
    "price_source": "supplied fuel price dataset"
  },
  "corridor_stations": ["every station considered, for drawing grey dots on the map"],
  "assumptions": { "start_fuel": "...", "corridor_miles": 10, "refuelling": "...", "detours": "..." },
  "meta": { "external_calls": { "geocoding": 2, "routing": 1 }, "elapsed_ms": 1840 }
}
```

- `route.geometry` is GeoJSON, which puts **longitude first**. Leaflet markers
  put latitude first, and the frontend swaps them.
- `stops[].type` is `"origin"` for the starting fill-up and `"en_route"` for the
  others.
- `meta.external_calls` shows how many calls this request made. It is 0 when
  cached, which is useful to show in the demo.

Errors:

| HTTP | `data.code` | When |
|---|---|---|
| 400 | `validation_error` | Missing field, or start and finish are the same |
| 400 | `parse_error` | Request body is not valid JSON |
| 400 | `location_not_found` | Location not found, or not in the USA |
| 422 | `route_not_found` | No drivable route (e.g. Honolulu → Denver) |
| 502 | `upstream_error` | Nominatim or OSRM unavailable |
| 405 | `method_not_allowed` | Wrong HTTP method (use POST) |
| 500 | `server_error` | Unexpected error (details go to the server log only) |

### 6.3 Other endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/fuel-stations/` | Paginated station list. Filters: `?state=TX`, `?geocoded=true`, `?ordering=retail_price`, `?page_size=100`. A page past the end returns 404 `not_found`. |
| `GET /api/v1/health/` | Station count and geocoded count. |

A Postman collection with success and error examples is in
`docs/strata-fuel-engine.postman_collection.json`.

------------------------------------------------------------------------

## 7. Performance and External Calls

| Situation | External calls | Typical time |
|---|---|---|
| Same trip again (cached) | 0 | ~150–400 ms |
| New trip, places seen before | 1 (routing) | ~1 s |
| Brand-new trip | 3 (2 geocoding + 1 routing) | ~1–3 s; >10 s when the public OSRM server is busy |
| Start/finish given as coordinates | 1 (routing) | ~1 s |

How it stays fast:

- Results are cached in a file-based Django cache (`backend/.cache/`), so they
  survive server restarts.
- The station list is kept in memory, so no database scan happens per request.
- Station distances are computed for all stations at once with `numpy`/`shapely`,
  not one row at a time.
- The route line is simplified before the distance check and before it is sent
  to the browser. This reduces the payload from about 35,000 points to about
  3,000 for a cross-country route.
- Nominatim requests are spaced at least 1 second apart to respect its usage
  policy.

------------------------------------------------------------------------

## 8. Frontend

React + Vite + React Leaflet, in `frontend/src/`:

| File | Responsibility |
|---|---|
| `App.jsx` | Page layout, state, calling the API, reading a trip from the URL |
| `api.js` | `POST /trips/plan/`; reads `data` and turns errors into readable messages |
| `components/TripPlannerForm.jsx` | Start/finish inputs, swap button, example trips |
| `components/RouteMap.jsx` | Map: route line, start (A) and finish (B) pins, numbered stop pins, grey dots for stations considered |
| `components/TripSummary.jsx` | Total cost, distance, drive time, gallons, stop count, API time and call count |
| `components/FuelStopList.jsx` | List of stops; clicking one zooms the map to it |
| `format.js` | Money, number and duration formatting |

Other features:

- Trips can be shared as links: `http://localhost:5173/?origin=Chicago,IL&destination=Denver,CO`.
- The layout works on mobile: the map is on top and the panel below.
- In development, Vite forwards `/api` to Django (`vite.config.js`), so no CORS
  setup is needed. To use a backend elsewhere, set `VITE_API_BASE_URL` (see
  `frontend/.env.example`).

------------------------------------------------------------------------

## 9. Project Structure

```text
strata-fuel-engine/
├── README.md                          setup and API summary
├── docs/
│   └── strata-fuel-engine.postman_collection.json
├── backend/
│   ├── config/settings.py             settings, incl. FUEL_ENGINE values
│   ├── config/urls.py                 /api/v1/ routes
│   ├── apis/
│   │   ├── fuel_stations/             FuelStation model, station list + health APIs
│   │   ├── trips/
│   │   │   ├── views.py               POST /trips/plan/
│   │   │   ├── serializers.py         input validation
│   │   │   ├── tests.py               26 tests
│   │   │   └── services/
│   │   │       ├── planner.py         runs the whole planning process
│   │   │       ├── geocoding.py       Nominatim + cache + USA check
│   │   │       ├── routing.py         OSRM + cache
│   │   │       ├── station_search.py  stations near the route
│   │   │       ├── fuel_optimizer.py  the optimiser (pure Python)
│   │   │       └── errors.py          error types shown to API clients
│   │   └── users/                     unused (from project setup)
│   ├── seeder/
│   │   ├── seed_fuel_stations.py      import prices
│   │   ├── geocode_stations.py        add coordinates (Gazetteer + Nominatim)
│   │   └── README.md
│   ├── data/                          see section 4.3 (git-ignored)
│   ├── notebooks/
│   │   └── geopy_practice_sqlite3.ipynb   step-by-step walkthrough of a trip
│   ├── db.sqlite3                     the database (git-ignored)
│   └── requirements.txt
└── frontend/
    ├── src/                           see section 8
    └── vite.config.js
```

The other notebooks in `notebooks/` are earlier experiments.
`geopy_practice_sqlite3.ipynb` is the up-to-date one: it runs each step with the
real services and compares the old stop rule with the optimiser.

------------------------------------------------------------------------

## 10. Configuration

Planner values live in `FUEL_ENGINE` in `backend/config/settings.py`:

| Setting | Value | Meaning |
|---|---|---|
| `MAX_RANGE_MILES` | 500 | Range on a full tank |
| `MPG` | 10 | Miles per gallon |
| `CORRIDOR_MILES` | 10 | Maximum distance from the road for a station to count |
| `ORIGIN_RADIUS_MILES` | 30 | Search radius for the starting fill-up |
| `STOP_PENALTY_DOLLARS` | 10 | A stop must save at least this much |
| `HTTP_TIMEOUT_SECONDS` | 30 | Timeout for Nominatim/OSRM |

Optional `backend/.env` values:

| Variable | Default |
|---|---|
| `SQLITE_PATH` | `db.sqlite3` (relative paths are resolved from `backend/`) |
| `OSRM_URL` | `https://router.project-osrm.org` |
| `NOMINATIM_URL` | `https://nominatim.openstreetmap.org` |
| `GEOCODER_USER_AGENT` | `strata-fuel-engine/1.0 (assessment demo)` |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |

------------------------------------------------------------------------

## 11. Running the Project

```bash
# Backend: http://127.0.0.1:8000
cd backend
pip install -r requirements.txt
python manage.py migrate
python seeder/seed_fuel_stations.py --file data/fuel_prices.csv --prune   # first time only
python seeder/geocode_stations.py                                        # first time only
python manage.py runserver

# Frontend: http://localhost:5173
cd frontend
npm install
npm run dev
```

Run the tests with `python manage.py test apis` from `backend/`.

------------------------------------------------------------------------

## 12. Demo Plan (under 5 minutes)

1. **0:00–0:30 — The problem.** "Given two US locations, find the cheapest
   places to refuel for a 500-mile-range truck at 10 mpg." Show the dataset:
   6,967 stations with prices but highway-exit addresses.
2. **0:30–1:30 — The app.** In the frontend, plan **New York → Los Angeles**.
   Show the route, the 7 numbered stops, the total cost, and the gallons per
   stop. Click a stop to zoom in.
3. **1:30–2:15 — Speed and API calls.** Plan the same trip again and point at
   "0 geocoding and 0 routing calls" and the time in milliseconds. Then show the
   same request in Postman, with the `status`/`message`/`data` shape.
4. **2:15–3:30 — How stops are chosen.** Explain "fill up or buy just enough",
   the $10 stop penalty, and the comparison table from section 1 (9 → 5 stops,
   $10 cheaper than the old rule).
5. **3:30–4:15 — Data problem and the Gazetteer.** The supplied file had no
   coordinates. The first attempt with `geopy` found only 480, some of them
   wrong. Town centres from the Census Gazetteer took coverage to 6,848
   stations.
6. **4:15–4:45 — Errors and tests.** Show `Toronto, ON` (not in the USA) or a
   missing field in Postman. Mention the 26 tests and the randomised optimiser
   check.
7. **4:45–5:00 — Limits.** Static prices, town-centre locations, free public
   servers.

Plan the demo trips once before presenting so they are cached and instant.

### Likely questions and short answers

- **"Why not geocode every address?"** Highway-exit addresses don't geocode
  reliably. The ones that did included matches hundreds of km off. Town centres
  are consistent, and they are accurate enough for a 10-mile corridor.
- **"Is it really optimal?"** Yes, for fuel cost plus $10 per stop, given the
  stations within 10 miles of the route. With the penalty set to $0 it gives the
  exact cheapest plan. It matched the textbook algorithm on 300 random routes.
- **"Why does the trip start with an empty tank?"** So that the total is the
  real cost of all fuel used on the trip. Otherwise any trip under 500 miles
  would cost $0.
- **"Why a $10 penalty?"** Without it the cheapest plan makes 12–22 stops on long
  trips to save cents. With $10, long trips need 5–8 stops at about 1% extra
  cost. It is one setting and easy to change.
- **"What happens if a stretch has no stations?"** The API returns the route
  with `feasible: false` and says after which mile there is no station within
  500 miles.
- **"How do you limit calls to the free APIs?"** One OSRM call per trip, at most
  two Nominatim calls, everything cached, and Nominatim calls spaced 1 second
  apart. A repeated trip makes no calls at all.
- **"Why SQLite and not PostGIS?"** Under 7,000 stations fit easily in memory.
  The distance check takes milliseconds with `shapely`, so a spatial database
  would add setup without making it noticeably faster.
