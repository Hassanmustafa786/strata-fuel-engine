# Strata Fuel Engine

## Backend and Frontend Project Documentation

**Project type:** Backend Django Engineer assessment\
**Repository:** `strata-fuel-engine`\
**Current data:** 6,967 fuel-station records in SQLite\
**Primary goal:** Given a US origin and destination, return a road
route, cost-effective fuel stops, and an estimated total fuel cost.

------------------------------------------------------------------------

## 1. Assessment Requirements

The application should:

1.  Accept a starting location and destination in the United States.
2.  Calculate a driving route and return route geometry suitable for a
    map.
3.  Recommend fuel stops along or near the route.
4.  Respect the vehicle's maximum range of **500 miles** and fuel
    economy of **10 miles per gallon (MPG)**.
5.  Calculate expected fuel usage and fuel cost using the supplied
    retail fuel prices.
6.  Minimize external API calls, with one routing request as the target
    and two or three calls acceptable if needed.
7.  Provide a working frontend map and a short Postman/Loom
    demonstration.

### Important assumptions to make explicit

- Fuel prices come from the supplied dataset; they may not reflect live
  prices.
- A vehicle can travel at most 500 miles on a full tank. The
  implementation should include a safety reserve if the assessment
  permits it, and document the chosen reserve.
- A station's cheapest price alone does not make it the best stop. The
  algorithm must ensure the vehicle can reach the next stop and
  ultimately the destination.
- The station dataset currently has addresses but no coordinates. Route
  proximity cannot be calculated accurately until coordinates are
  populated.
- Treat the OPIS Truckstop ID as a source identifier, not necessarily a
  unique database key. The source has duplicate IDs with differing
  station records.

------------------------------------------------------------------------

## 2. Recommended Technical Approach

For an assessment, prefer a simple, testable, explainable design over a
complex routing platform.

### 2.1 Geocode the station dataset once

Use a separate seeding/enrichment script to add latitude and longitude
to station records. Since all records are in the United States and there
are 6,967 rows, the US Census Geocoder's batch endpoint is a practical
option to evaluate. It supports batches of up to 10,000 addresses. The
source requires a unique row ID and structured address fields; address
quality affects match quality.

Official documentation:
<https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html>

Recommended workflow:

1.  Export records without coordinates to a batch CSV with columns for a
    stable row ID, street address, city, state, and ZIP code if
    available.
2.  Submit the batch to the geocoder.
3.  Match returned results back to the exact station records using the
    submitted row ID.
4.  Store valid coordinates in SQLite.
5.  Record unmatched/ambiguous addresses in a report rather than
    silently assigning coordinates.
6.  Re-run the process safely: skip already-geocoded records unless
    explicitly asked to refresh them.

The Census Geocoder returns coordinates based on address ranges, so
coordinates may be interpolated rather than an exact truck-stop
entrance. Validate a sample manually. If the input data has incomplete
or poor street addresses, compare an alternative geocoder for the
unmatched subset.

Avoid geocoding all 6,967 records on every trip request. Avoid relying
on bulk use of a public Nominatim instance for this task.

### 2.2 Route calculation

Use a driving routing service such as OSRM to calculate a route between
the resolved origin and destination. Request GeoJSON geometry so the
frontend can draw the route.

- Routing documentation: <https://project-osrm.org/docs/>
- Public OSRM demo server: <https://router.project-osrm.org/>

The public demo service is best-effort and has usage restrictions, so it
is suitable for a controlled assessment demo, not a production
reliability guarantee. Add a clear timeout and error response. Display
OpenStreetMap/OSRM attribution as required.

Target **one route request per trip**. Geocoding origin/destination may
require separate calls unless the selected routing provider also offers
geocoding. Cache geocoding results where possible. Do not call the
routing API once per station.

### 2.3 Candidate station selection

Once route geometry and station coordinates exist:

1.  Calculate or sample the route's path.
2.  Filter stations within a configurable corridor around the route.
3.  Estimate each candidate station's position along the route.
4.  Sort candidates by distance along the route.
5.  Choose feasible stops using the fuel prices and vehicle constraints.

For a first assessment version, a straightforward distance-to-route
calculation is sufficient for 6,967 rows. If performance requires it,
add PostGIS or another spatial index later rather than starting with
unnecessary infrastructure.

### 2.4 Fuel-stop optimization

Use constants/configuration rather than scattering assumptions
throughout the code:

- `VEHICLE_MAX_RANGE_MILES = 500`
- `VEHICLE_MPG = 10`
- Optional safety reserve, documented and configurable
- Maximum detour/corridor distance, configurable

At 10 MPG, 500 miles represents 50 gallons of usable range if the tank
starts full and the entire rated range is available. The actual fuel
purchase at a stop depends on the previous leg and the tank model.

A reasonable initial algorithm:

1.  Treat the origin as the initial position and assume a full tank,
    unless the request specifies otherwise.
2.  Identify candidate stations along the route, including their
    route-progress distance and price per gallon.
3.  At each step, consider only stations reachable within the remaining
    range.
4.  Prefer a lower-cost reachable station when doing so does not make
    the next leg or destination unreachable.
5.  Continue until the destination is reachable.
6.  If no feasible station is available, return a clear "no feasible
    fuel-stop plan" result rather than an invalid plan.
7.  Calculate gallons purchased and estimated cost consistently. If the
    API does not model tank capacity or initial fuel level, state that
    the estimate assumes a full tank at the start and document the
    simplified refuelling model.

A greedy "always choose the cheapest station within 500 miles" rule can
fail if it skips a necessary station. Keep the algorithm separate from
the API view so it can be unit-tested.

### 2.5 Cost calculations

At 10 MPG:

`estimated gallons consumed = route distance in miles / 10`

A simple trip fuel-cost estimate is:

`estimated trip cost = gallons consumed × selected/assumed price per gallon`

For a stop-by-stop plan, calculate cost from the gallons actually
purchased at each recommended station instead. Do not mix these two
methods. Explain the chosen method in API documentation and the demo.

------------------------------------------------------------------------

## 3. Repository Directory Structure

The following represents the intended project layout. Files marked
"planned" may not exist yet; update this document as implementation
progresses.

``` text
strata-fuel-engine/
├── backend/
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── asgi.py
│   │   └── wsgi.py
│   ├── apis/
│   │   ├── users/
│   │   │   ├── apps.py
│   │   │   ├── models.py
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   ├── urls.py
│   │   │   └── tests.py
│   │   ├── fuel_stations/
│   │   │   ├── apps.py
│   │   │   ├── models.py
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   ├── urls.py
│   │   │   └── tests.py
│   │   └── trips/
│   │       ├── apps.py
│   │       ├── models.py
│   │       ├── serializers.py
│   │       ├── views.py
│   │       ├── urls.py
│   │       ├── tests.py
│   │       └── services/
│   │           ├── __init__.py
│   │           ├── geocoding.py       # planned
│   │           ├── routing.py         # planned
│   │           ├── station_search.py  # planned
│   │           └── fuel_optimizer.py  # planned
│   ├── seeder/
│   │   ├── seed_fuel_stations.py
│   │   ├── validate_fuel_data.py
│   │   └── README.md
│   ├── data/
│   │   └── fuel_prices.csv
│   ├── manage.py
│   ├── requirements.txt
│   └── .env                    # local secrets; never commit
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/         # planned: map, form, stop cards
│   │   ├── pages/              # planned: trip planner page
│   │   ├── services/           # planned: API client
│   │   ├── hooks/              # optional
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── .gitignore
└── README.md
```

Keep the tree aligned with the actual repository. Django app files can
be added when needed; do not create empty modules merely to match this
diagram.

------------------------------------------------------------------------

## 4. Backend Details

### 4.1 Technology

- Python
- Django
- Django REST Framework
- SQLite (Python's built-in `sqlite3`)
- `python-dotenv` for local environment configuration
- `pandas` and `openpyxl` for importing CSV/XLSX source data
- `requests` for outbound HTTP calls to geocoding/routing services

### 4.2 Configuration and secrets

`backend/config/settings.py` loads environment values from
`backend/.env`.

Typical local variables:

``` dotenv
# Optional; defaults to backend/db.sqlite3
SQLITE_PATH=db.sqlite3
```

Use a separate environment variable for any provider configuration if
needed. Never commit real credentials, tokens, or local secrets. Provide
a `.env.example` with placeholder values for reviewers.

### 4.3 FuelStation model

The current model is intended to contain:

  -----------------------------------------------------------------------
  Field                               Purpose
  ----------------------------------- -----------------------------------
  `opis_truckstop_id`                 Source OPIS identifier; do not
                                      assume globally unique

  `name`                              Fuel station name

  `address`                           Street address

  `city`                              City

  `state`                             Two-character state code

  `rack_id`                           Optional rack identifier

  `retail_price`                      Retail price per gallon from the
                                      supplied dataset

  `latitude`                          Geocoded latitude; nullable until
                                      enriched

  `longitude`                         Geocoded longitude; nullable until
                                      enriched

  `created_at`                        Creation timestamp

  `updated_at`                        Last update timestamp
  -----------------------------------------------------------------------

The table uses `fuel_stations` as its database table name. Indexes on
state/price and coordinates are useful for filtering. A uniqueness rule
for station identity should match the seeder's `unique_fields` exactly;
otherwise SQLite upsert operations using `ON CONFLICT` will fail.
Review how nullable `rack_id` values behave under the chosen uniqueness
rule.

### 4.4 Seeder responsibilities

`backend/seeder/seed_fuel_stations.py` should:

- Accept the input path as a command-line argument.
- Support the agreed CSV/XLSX formats.
- Validate required columns and values.
- Normalize state codes and strings.
- Parse numeric IDs and decimal prices safely.
- Deduplicate records using a documented station-identity rule, not OPIS
  ID alone.
- Insert/update rows in a transaction and in batches.
- Print a summary of inserted/updated/skipped/invalid records.
- Be safe to rerun.

`backend/seeder/validate_fuel_data.py` should report missing required
values, invalid prices, invalid states, duplicates, and missing
coordinates. A separate coordinate-enrichment script can be added to the
seeder directory.

### 4.5 Suggested API contract

Use a versioned API prefix, for example `/api/v1/`.

#### `POST /api/v1/trips/plan/` --- planned

Example request:

``` json
{
  "origin": "Los Angeles, CA",
  "destination": "Phoenix, AZ"
}
```

Example response shape (illustrative, not a claim that the endpoint
already exists):

``` json
{
  "origin": {
    "label": "Los Angeles, CA",
    "latitude": 34.05,
    "longitude": -118.24
  },
  "destination": {
    "label": "Phoenix, AZ",
    "latitude": 33.45,
    "longitude": -112.07
  },
  "route": {
    "distance_miles": 372.0,
    "duration_seconds": 21000,
    "geometry": {
      "type": "LineString",
      "coordinates": []
    }
  },
  "vehicle": {
    "max_range_miles": 500,
    "mpg": 10
  },
  "fuel_plan": {
    "stops": [],
    "estimated_gallons_consumed": 37.2,
    "estimated_total_cost": 0.0,
    "currency": "USD",
    "price_source": "supplied dataset"
  }
}
```

The coordinates and numbers above are illustrative only. Actual route
values must come from the routing provider. Ensure GeoJSON coordinate
order is `[longitude, latitude]`, while Leaflet marker positions are
usually expressed as `[latitude, longitude]`.

#### Other useful endpoints

- `GET /api/v1/fuel-stations/` --- optional paginated station
  listing/filtering for debugging.
- `GET /api/v1/health/` --- optional lightweight health check.

Avoid implementing authentication or a user-management feature unless
the assessment explicitly requires it. The `users` app can remain
minimal or unused until there is a real requirement.

### 4.6 Backend module responsibilities

- `trips/views.py`: validate the HTTP request and return the response.
- `trips/serializers.py`: validate inputs and shape outputs.
- `trips/services/geocoding.py`: resolve origin/destination and cache
  where possible.
- `trips/services/routing.py`: call the routing provider and normalize
  distance/geometry.
- `trips/services/station_search.py`: find stations near the route and
  calculate route progress.
- `trips/services/fuel_optimizer.py`: produce a feasible, cost-conscious
  stop plan.
- `fuel_stations/models.py`: database representation of station data.
- `seeder/`: import, validate, and enrich source data.

Keep provider calls and optimization logic out of Django views. This
makes them easier to test and replace.

------------------------------------------------------------------------

## 5. Frontend Details

### 5.1 Technology

- React
- Vite
- Leaflet
- React Leaflet

### 5.2 Suggested UI components

  -----------------------------------------------------------------------
  Component                           Responsibility
  ----------------------------------- -----------------------------------
  `TripPlannerForm`                   Origin and destination inputs;
                                      submit action

  `RouteMap`                          Display route GeoJSON as a polyline

  `FuelStopMarker`                    Show each recommended station on
                                      the map

  `FuelStopList`                      List stop name, location, price,
                                      and route distance

  `TripSummary`                       Show total miles, estimated
                                      gallons, number of stops, and
                                      estimated cost

  `LoadingState` / `ErrorMessage`     Handle requests and show
                                      understandable errors
  -----------------------------------------------------------------------

### 5.3 Suggested request flow

1.  User enters origin and destination.
2.  React validates that both fields are present.
3.  Frontend sends one request to `POST /api/v1/trips/plan/`.
4.  Backend resolves locations, gets route geometry, filters stations,
    and optimizes stops.
5.  Frontend displays the returned route, stop markers, and cost
    summary.
6.  The UI shows loading and error states and allows the user to submit
    a new trip.

The frontend should not call the routing API for each fuel station. Keep
routing and optimization on the backend.

### 5.4 Map details

- Draw the returned route geometry on the map.
- Add markers for origin, destination, and recommended fuel stops.
- Show a popup with station name, address, price per gallon, and stop
  order.
- Fit map bounds to the route.
- Display distance units and currency clearly.
- Include appropriate OpenStreetMap/route-provider attribution.
- Remember GeoJSON uses longitude-first coordinates; Leaflet marker
  arrays normally use latitude-first coordinates.

### 5.5 Environment configuration

Use a Vite environment variable for the backend base URL, for example:

``` dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Vite exposes variables prefixed with `VITE_` to frontend code, so do not
put secrets in them.

------------------------------------------------------------------------

## 6. Implementation Order

Use this order to minimize rework:

1.  **Confirm data import:** verify the 6,967 records and validate
    prices/duplicates.
2.  **Add coordinate enrichment:** geocode once, save coordinates,
    report unmatched addresses.
3.  **Implement route service:** resolve origin/destination and retrieve
    route geometry.
4.  **Implement station search:** filter stations close to the route and
    calculate progress along it.
5.  **Implement optimizer:** enforce reachability and minimize estimated
    fuel spend.
6.  **Implement trip API:** validate inputs, compose services, and
    return a stable response schema.
7.  **Implement frontend:** form, map, station markers, cost summary,
    and error/loading states.
8.  **Add tests:** especially range limits, unreachable segments,
    missing coordinates, invalid prices, and no feasible stops.
9.  **Write run instructions:** document environment setup, migrations,
    data import, coordinate enrichment, backend startup, and frontend
    startup.
10. **Prepare demo:** show a successful trip, fuel-stop reasoning, cost
    calculation, and one error case.

------------------------------------------------------------------------

## 7. Testing Checklist

### Data and database

- [ ] Dataset imports successfully and repeat imports do not create
  unwanted duplicates.
- [ ] Prices are positive and stored as decimal values.
- [ ] Station identity and duplicate handling are documented.
- [ ] Coordinate enrichment can be rerun without unnecessary API
  requests.
- [ ] Unmatched addresses are reported.

### Route and optimizer

- [ ] Valid origin/destination produces route geometry.
- [ ] Invalid or unresolvable locations return a clear client error.
- [ ] Stations are filtered by proximity to the route.
- [ ] Every leg is within the vehicle's permitted range.
- [ ] The destination is reachable after the final stop.
- [ ] No feasible plan returns a clear error/result rather than an
  invalid route.
- [ ] Fuel cost calculations use consistent units and assumptions.
- [ ] External API timeout or failure is handled gracefully.

### Frontend

- [ ] Route line appears on the map.
- [ ] Start, destination, and fuel-stop markers appear in the correct
  locations.
- [ ] Stop list and map markers agree.
- [ ] Distance, gallons, and currency are labelled clearly.
- [ ] Loading and error states are visible.

### Assessment delivery

- [ ] `.env` and secrets are excluded from Git.
- [ ] README contains reproducible setup instructions.
- [ ] Postman collection includes a successful example and an error
  case.
- [ ] Loom demonstration is under five minutes.
- [ ] Any limitations and data assumptions are explained honestly.

------------------------------------------------------------------------

## 8. Demo Plan (under 5 minutes)

1.  **0:00--0:30:** Briefly explain the architecture and the 6,967-row
    station dataset.
2.  **0:30--1:30:** Send a trip-planning request in Postman and show the
    response.
3.  **1:30--2:45:** Show the frontend route, fuel stops, station prices,
    and estimated total cost.
4.  **2:45--3:45:** Explain how the 500-mile range and 10 MPG
    constraints affect stop selection.
5.  **3:45--4:30:** Show one validation/error case and briefly mention
    tests and limitations.

Use a route and dataset subset that have been verified in advance. Do
not claim live fuel prices if the app uses the supplied static file.

------------------------------------------------------------------------

## 9. Known Risks and Scope Control

- **Address quality:** incomplete addresses can fail geocoding or return
  approximate coordinates.
- **Public service availability:** free geocoding/routing endpoints may
  impose limits and do not guarantee uptime.
- **Fuel-price freshness:** the supplied data may be static or dated.
- **Fuel tank model:** range alone does not fully define tank capacity,
  starting fuel, or refuelling amounts. State the model used.
- **Route proximity:** a station near a route line may be on the wrong
  side of a highway or require a large detour. Use a corridor filter
  and, if time allows, calculate detour distance.
- **Spatial precision:** basic calculations may be sufficient for the
  assessment, but should be documented. Add a spatial index or PostGIS
  only if justified.
- **No feasible route:** the API should return a transparent result when
  the dataset cannot support a feasible stop plan.

### Final recommendation

Keep the first version modular but lean: Django REST Framework,
SQLite, a one-time batch geocoding process, one road-route request
per trip, a separately tested fuel optimizer, and a React Leaflet
interface. This demonstrates backend design, data handling, external API
integration, algorithmic reasoning, and frontend integration without
unnecessary infrastructure.
