import random
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from apis.fuel_stations.models import FuelStation

from .services import station_search
from .services.errors import LocationNotFound
from .services.fuel_optimizer import FuelOption, plan_purchases
from .services.geocoding import Location
from .services.routing import Route

RANGE = 500
MPG = 10


def plan(stations, route_miles, start_fuel_miles=0.0, stop_penalty=0.0):
    options = [FuelOption(mile, price, name) for name, mile, price in stations]
    return plan_purchases(
        options, route_miles, RANGE, MPG, start_fuel_miles, stop_penalty
    )


def bought(result):
    return [(p.option.ref, round(p.gallons, 6)) for p in result.purchases]


class FuelOptimizerTests(SimpleTestCase):
    def test_short_trip_buys_only_what_it_needs_at_start(self):
        result = plan([("origin", 0, 3.0)], 300)
        self.assertTrue(result.feasible)
        self.assertEqual(bought(result), [("origin", 30)])
        self.assertAlmostEqual(result.total_cost, 90.0)

    def test_buys_just_enough_to_reach_a_cheaper_station(self):
        result = plan([("origin", 0, 4.0), ("cheap", 100, 3.0)], 400)
        self.assertEqual(bought(result), [("origin", 10), ("cheap", 30)])
        self.assertAlmostEqual(result.total_cost, 40 + 90)

    def test_fills_up_when_everything_ahead_is_pricier(self):
        # Cheapest fuel is at the start: fill up, then buy what is still
        # needed (700 - 480 - 20 miles left in the tank) at the cheaper
        # of the two later stations.
        stations = [
            ("origin", 0, 3.0), ("pricey", 450, 5.0), ("mid", 480, 4.0),
        ]
        result = plan(stations, 700)
        self.assertEqual(bought(result), [("origin", 50), ("mid", 20)])
        self.assertAlmostEqual(result.total_cost, 150 + 80)

    # Stations from the original notebook run, which stopped at Fremont,
    # Bradner and Ottawa Lake within 40 miles of each other.
    NOTEBOOK_STATIONS = [
        ("origin", 0, 3.6), ("fremont", 459, 3.382),
        ("bradner", 470.8, 3.407), ("ottawa", 497.7, 3.499),
        ("wanatah", 670.8, 3.499), ("des_moines", 1032.4, 3.027),
    ]

    def test_cheapest_plan_tops_up_at_bradner(self):
        result = plan(self.NOTEBOOK_STATIONS, 1400)
        self.assertEqual(
            [ref for ref, _ in bought(result)],
            ["origin", "fremont", "bradner", "wanatah", "des_moines"],
        )
        self.assertAlmostEqual(bought(result)[2][1], 1.18)

    def test_stop_penalty_drops_stops_that_save_cents(self):
        cheapest = plan(self.NOTEBOOK_STATIONS, 1400)
        result = plan(self.NOTEBOOK_STATIONS, 1400, stop_penalty=5)
        self.assertEqual(
            [ref for ref, _ in bought(result)],
            ["origin", "fremont", "wanatah", "des_moines"],
        )
        self.assertLess(result.total_cost - cheapest.total_cost, 5)

    def test_stop_penalty_keeps_stops_that_save_money(self):
        stations = [("origin", 0, 4.0), ("cheap", 100, 3.0)]
        result = plan(stations, 400, stop_penalty=5)
        self.assertEqual(len(result.purchases), 2)

    def test_total_gallons_cover_the_whole_trip(self):
        stations = [
            ("origin", 0, 3.5), ("a", 300, 3.2), ("b", 650, 3.9),
            ("c", 900, 3.1), ("d", 1300, 3.6),
        ]
        result = plan(stations, 1600)
        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.total_gallons, 160)

    def test_reports_gap_longer_than_range(self):
        result = plan([("origin", 0, 3.0), ("far", 600, 3.0)], 900)
        self.assertFalse(result.feasible)
        self.assertIn("after route mile 0", result.message)

    def test_needs_fuel_at_start_when_tank_is_empty(self):
        result = plan([("later", 50, 3.0)], 300)
        self.assertFalse(result.feasible)

    def test_starting_fuel_is_used_first(self):
        result = plan([("later", 50, 3.0)], 300, start_fuel_miles=100)
        self.assertEqual(bought(result), [("later", 20)])

    def test_matches_greedy_reference_on_random_routes(self):
        rng = random.Random(7)
        for _ in range(300):
            route_miles = rng.uniform(100, 2500)
            stations = [("origin", 0, rng.uniform(2.5, 4.5))] + [
                (f"s{i}", rng.uniform(1, route_miles), rng.uniform(2.5, 4.5))
                for i in range(rng.randint(0, 40))
            ]
            expected = greedy_cost(stations, route_miles)
            result = plan(stations, route_miles)
            if expected is None:
                self.assertFalse(result.feasible)
            else:
                self.assertTrue(result.feasible)
                self.assertAlmostEqual(result.total_cost, expected, places=4)
                self.assertAlmostEqual(
                    result.total_gallons, route_miles / MPG, places=6
                )

    def test_penalty_never_makes_more_stops(self):
        rng = random.Random(11)
        for _ in range(100):
            route_miles = rng.uniform(500, 2500)
            stations = [("origin", 0, 3.5)] + [
                (f"s{i}", rng.uniform(1, route_miles), rng.uniform(2.5, 4.5))
                for i in range(40)
            ]
            cheapest = plan(stations, route_miles)
            fewer = plan(stations, route_miles, stop_penalty=10)
            if cheapest.feasible:
                self.assertLessEqual(len(fewer.purchases), len(cheapest.purchases))
                self.assertGreaterEqual(fewer.total_cost, cheapest.total_cost - 1e-6)


def greedy_cost(stations, route_miles):
    """Textbook greedy, known to be cost-optimal; used as a reference."""
    nodes = sorted(stations, key=lambda s: s[1]) + [("end", route_miles, 0)]
    i, fuel, cost = 0, 0.0, 0.0
    if nodes[0][1] != 0:
        return None
    while nodes[i][0] != "end":
        _, here, price = nodes[i]
        ahead = [k for k in range(i + 1, len(nodes)) if nodes[k][1] - here <= RANGE]
        if not ahead:
            return None
        cheaper = next((k for k in ahead if nodes[k][2] < price), None)
        if cheaper is not None:
            leg = nodes[cheaper][1] - here
            cost += max(0.0, leg - fuel) / MPG * price
            fuel = max(fuel, leg) - leg
            i = cheaper
        else:
            nxt = min(ahead, key=lambda k: nodes[k][2])
            cost += (RANGE - fuel) / MPG * price
            fuel = RANGE - (nodes[nxt][1] - here)
            i = nxt
    return cost


def make_station(name, latitude, longitude, price, **extra):
    return FuelStation.objects.create(
        opis_truckstop_id=1, name=name, address="I-80", city=name,
        state="IA", rack_id=1, retail_price=Decimal(price),
        latitude=latitude, longitude=longitude,
        geocode_status="success", **extra,
    )


# Straight east-west route along latitude 41 from -96 to -90.
ROUTE = Route(
    distance_miles=313.0,
    duration_seconds=18000,
    coordinates=[[-96 + i * 0.1, 41.0] for i in range(61)],
)


class StationSearchTests(TestCase):
    def setUp(self):
        station_search._index = None

    def test_finds_corridor_stations_in_route_order(self):
        make_station("east", 41.02, -90.5, "3.1")
        make_station("west", 41.05, -95.5, "3.2")
        make_station("far", 42.5, -93.0, "2.0")

        index = station_search.get_station_index()
        found = station_search.find_stations_near_route(
            index, ROUTE.coordinates, ROUTE.distance_miles, 10
        )

        self.assertEqual([c.station["name"] for c in found], ["west", "east"])
        self.assertAlmostEqual(found[0].route_mile, 26, delta=2)
        self.assertLess(found[0].distance_from_route_miles, 5)

    def test_keeps_cheapest_station_per_location(self):
        make_station("dear", 41.0, -93.0, "3.9")
        make_station("cheap", 41.0, -93.0, "3.1")

        index = station_search.get_station_index()
        self.assertEqual([s["name"] for s in index.stations], ["cheap"])

    def test_index_refreshes_when_data_changes(self):
        make_station("one", 41.0, -93.0, "3.1")
        self.assertEqual(len(station_search.get_station_index().stations), 1)
        make_station("two", 41.0, -92.0, "3.1")
        self.assertEqual(len(station_search.get_station_index().stations), 2)


@override_settings(CACHES={
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
})
class TripPlanApiTests(TestCase):
    url = "/api/v1/trips/plan/"

    def setUp(self):
        cache.clear()
        station_search._index = None
        self.client = APIClient()
        make_station("start", 41.0, -95.95, "3.50")
        # Saves ~$24 over buying everything at the start: worth a stop.
        make_station("cheap", 41.0, -93.0, "2.00")

        self.locations = {
            "Omaha, NE": Location("Omaha", 41.0, -96.0),
            "Davenport, IA": Location("Davenport", 41.0, -90.0),
        }
        geocode = mock.patch(
            "apis.trips.services.planner.geocode",
            side_effect=lambda q: (self.locations[q], True),
        )
        route = mock.patch(
            "apis.trips.services.planner.get_route",
            return_value=(ROUTE, True),
        )
        geocode.start()
        route.start()
        self.addCleanup(mock.patch.stopall)

    def test_returns_route_stops_and_cost(self):
        response = self.client.post(
            self.url,
            {"origin": "Omaha, NE", "destination": "Davenport, IA"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        fuel = body["fuel_plan"]
        self.assertTrue(fuel["feasible"])
        self.assertEqual(
            [s["station"]["name"] for s in fuel["stops"]], ["start", "cheap"]
        )
        self.assertEqual(fuel["stops"][0]["type"], "origin")
        self.assertAlmostEqual(fuel["total_gallons"], 31.3, places=1)
        self.assertEqual(body["route"]["geometry"]["type"], "LineString")
        self.assertEqual(
            body["meta"]["external_calls"], {"geocoding": 2, "routing": 1}
        )

    def test_validates_input(self):
        response = self.client.post(self.url, {"origin": "X"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("destination", response.json())

    def test_unknown_location_is_a_client_error(self):
        with mock.patch(
            "apis.trips.services.planner.geocode",
            side_effect=LocationNotFound("Could not find 'Atlantis'"),
        ):
            response = self.client.post(
                self.url,
                {"origin": "Atlantis", "destination": "Davenport, IA"},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "location_not_found")

    def test_map_page_renders(self):
        response = self.client.get(
            "/api/v1/trips/map/",
            {"origin": "Omaha, NE", "destination": "Davenport, IA"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "plan-data")


class GeocodingTests(SimpleTestCase):
    def test_coordinates_skip_external_call(self):
        from .services.geocoding import geocode

        location, called = geocode("39.74, -104.99")
        self.assertFalse(called)
        self.assertEqual((location.latitude, location.longitude), (39.74, -104.99))

    def test_coordinates_outside_usa_are_rejected(self):
        from .services.geocoding import geocode

        with self.assertRaises(LocationNotFound):
            geocode("51.5, -0.12")
