"""
Minimum-cost refuelling along a fixed route.

Pure Python with no Django dependency, so it can be unit-tested and
reused from notebooks.
"""
from dataclasses import dataclass, field

EPSILON = 1e-6


@dataclass(frozen=True)
class FuelOption:
    """A place on the route where fuel can be bought."""
    route_mile: float
    price: float
    ref: object = field(default=None, compare=False)


@dataclass(frozen=True)
class Purchase:
    option: FuelOption
    gallons: float
    cost: float
    fuel_on_arrival_gallons: float


@dataclass(frozen=True)
class FuelPlan:
    feasible: bool
    purchases: list
    total_gallons: float
    total_cost: float
    message: str = ""


def plan_purchases(
    options, route_miles, max_range_miles, mpg,
    start_fuel_miles=0.0, stop_penalty=0.0,
):
    """
    Choose where to buy fuel and how much.

    Minimises fuel cost + `stop_penalty` dollars per stop, so a stop is
    only made when it saves more than the penalty. With no penalty the
    plan is the cheapest possible.

    Fuel can be bought in any amount up to a full tank (`max_range_miles`
    of driving). An optimal plan only ever does one of two things at a
    stop (Khuller, Malekian & Mestre, "To fill or not to fill", 2007):

    - fill the tank, when the next stop is more expensive, or
    - buy just enough to reach the next stop, arriving empty.

    So the fuel left on arrival at a station is either zero or "a full
    tank minus the drive from an earlier stop". Dynamic programming over
    those (station, fuel on arrival) states finds the optimal plan.
    Fuel is tracked in miles of range throughout.
    """
    stations = sorted(
        (o for o in options if 0 <= o.route_mile < route_miles),
        key=lambda option: option.route_mile,
    )
    count = len(stations)
    destination = count  # node index of the end of the route
    positions = [s.route_mile for s in stations] + [route_miles]
    prices = [s.price for s in stations]

    # best[(node, fuel_on_arrival)] =
    #     (score, cost, parent_state, miles_bought_at_parent)
    best = {}
    states_at = [[] for _ in range(count + 1)]

    def relax(node, fuel, score, cost, parent, bought):
        key = (node, round(fuel, 6))
        current = best.get(key)
        if current is None:
            states_at[node].append(key)
        elif score >= current[0] - EPSILON:
            return
        best[key] = (score, cost, parent, bought)

    # Leaving the start with whatever is already in the tank.
    for node in range(count + 1):
        if positions[node] > start_fuel_miles + EPSILON:
            break
        relax(node, start_fuel_miles - positions[node], 0, 0, None, 0)

    for node in range(count):
        here_mile, here_price = positions[node], prices[node]
        cost_per_mile = here_price / mpg

        for state in states_at[node]:
            score, cost, _, _ = best[state]
            fuel = state[1]

            for nxt in range(node + 1, count + 1):
                distance = positions[nxt] - here_mile
                if distance > max_range_miles + EPSILON:
                    break

                if nxt != destination and prices[nxt] > here_price:
                    bought = max_range_miles - fuel
                    arrival = max_range_miles - distance
                elif fuel <= distance + EPSILON:
                    bought = distance - fuel
                    arrival = 0.0
                else:
                    continue

                spent = bought * cost_per_mile
                penalty = stop_penalty if bought > EPSILON else 0.0
                relax(nxt, arrival, score + spent + penalty, cost + spent,
                      state, bought)

    finish = min(
        (state for state in best if state[0] == destination),
        key=lambda state: best[state][0],
        default=None,
    )

    if finish is None:
        furthest = max(
            (positions[state[0]] for state in best), default=0.0
        )
        return FuelPlan(
            feasible=False,
            purchases=[],
            total_gallons=0.0,
            total_cost=0.0,
            message=(
                f"No fuel station within {max_range_miles:.0f} miles "
                f"after route mile {furthest:.0f}."
            ),
        )

    purchases = []
    state = finish
    while True:
        _, _, parent, bought = best[state]
        if parent is None:
            break
        if bought > EPSILON:
            option = stations[parent[0]]
            gallons = bought / mpg
            purchases.append(
                Purchase(
                    option=option,
                    gallons=gallons,
                    cost=gallons * option.price,
                    fuel_on_arrival_gallons=parent[1] / mpg,
                )
            )
        state = parent

    purchases.reverse()
    return FuelPlan(
        feasible=True,
        purchases=purchases,
        total_gallons=sum(p.gallons for p in purchases),
        total_cost=sum(p.cost for p in purchases),
    )
