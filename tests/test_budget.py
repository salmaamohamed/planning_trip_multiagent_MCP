from app.agents.budget_agent import plan_budget


def flight(direction, price, airline="A", currency="USD"):
    return {"airline": airline, "direction": direction, "departure": "X", "arrival": "Y",
            "departure_time": "t", "arrival_time": "t", "duration": "1h", "price": price, "currency": currency}


def hotel(name, total, rating, currency="USD"):
    return {"name": name, "location": "L", "rating": rating, "price_per_night": total / 5,
            "total_price": total, "currency": currency}


def activity(name, price, day=1):
    return {"name": name, "category": "c", "duration_hours": 1, "price": price, "currency": "USD", "day": day}


FLIGHTS = [flight("outbound", 300), flight("outbound", 200), flight("return", 250)]
HOTELS = [hotel("Cheap", 400, 3.5), hotel("Nice", 700, 4.5), hotel("Luxury", 1500, 5.0)]
ACTIVITIES = [activity("Museum", 20), activity("Tour", 80, day=2), activity("Park", 0, day=2)]


def test_no_budget_selects_lowest_cost_and_does_not_invent_budget():
    plan = plan_budget(FLIGHTS, HOTELS, ACTIVITIES, currency="USD", budget=None)
    assert plan.status == "ok"
    assert plan.budget is None and plan.budget_remaining is None
    assert plan.selected.hotel.name == "Cheap"
    assert plan.selected.flight_cost == 450
    assert plan.selected.estimated_total == 450 + 400 + 100
    assert plan.combinations_evaluated == 2 * 1 * 3
    assert any(alt.label == "Top-rated hotel" for alt in plan.alternatives)


def test_budget_selects_best_rated_hotel_that_fits():
    plan = plan_budget(FLIGHTS, HOTELS, ACTIVITIES, currency="USD", budget=1300)
    assert plan.selected.hotel.name == "Nice"
    assert plan.selected.within_budget
    assert plan.selected.estimated_total <= 1300
    assert plan.budget_remaining == 1300 - plan.selected.estimated_total


def test_budget_drops_expensive_activities_to_fit():
    plan = plan_budget(FLIGHTS, HOTELS, ACTIVITIES, currency="USD", budget=1200)
    names = {a.name for a in plan.selected.activities}
    assert plan.selected.within_budget
    assert "Tour" not in names and "Park" in names


def test_budget_too_small_returns_cheapest_flagged_over_budget():
    plan = plan_budget(FLIGHTS, HOTELS, ACTIVITIES, currency="USD", budget=100)
    assert plan.selected.within_budget is False
    assert plan.selected.hotel.name == "Cheap"
    assert plan.budget_remaining < 0
    assert any("exceeds it by" in line for line in plan.explanation)


def test_missing_flights_marks_partial_and_excludes_flight_cost():
    plan = plan_budget([], HOTELS, ACTIVITIES, currency="USD", budget=None)
    assert plan.status == "partial"
    assert "flights" in plan.unavailable_components
    assert plan.selected.flight_cost is None
    assert plan.selected.estimated_total == 400 + 100


def test_missing_return_flight_is_reported():
    plan = plan_budget([flight("outbound", 200)], HOTELS, [], currency="USD", budget=None)
    assert "return flight" in plan.unavailable_components
    assert "activities" in plan.unavailable_components


def test_nothing_available_is_unavailable():
    plan = plan_budget([], [], [], currency="USD", budget=1000)
    assert plan.status == "unavailable"
    assert plan.selected is None


def test_other_currencies_are_excluded_not_converted():
    plan = plan_budget(FLIGHTS, [hotel("Euro", 100, 5.0, currency="EUR"), *HOTELS], [], currency="USD", budget=None)
    assert plan.selected.hotel.name == "Cheap"
    assert any("another currency" in line for line in plan.explanation)
