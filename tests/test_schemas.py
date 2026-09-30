import pytest
from pydantic import ValidationError

from app.schemas.travel import TravelRequest, TripConstraints
from tests.conftest import future_date


def test_valid_request_derives_dates():
    req = TravelRequest(destination=" Paris ", travel_date="2030-10-15", duration_days=5, currency="usd")
    assert req.destination == "Paris"
    assert req.currency == "USD"
    c = TripConstraints.from_request(req)
    assert (c.start_date, c.return_date, c.nights) == ("2030-10-15", "2030-10-20", 5)


def test_accepts_date_with_time():
    assert TravelRequest(destination="Rome", travel_date=f"{future_date()}T09:30", duration_days=2)


@pytest.mark.parametrize("fields", [
    {"travel_date": "2030-10-15", "duration_days": 5},
    {"destination": "  ", "travel_date": "2030-10-15", "duration_days": 5},
    {"destination": "Paris", "duration_days": 5},
    {"destination": "Paris", "travel_date": "15/10/2030", "duration_days": 5},
    {"destination": "Paris", "travel_date": "2020-01-01", "duration_days": 5},
    {"destination": "Paris", "travel_date": "2030-10-15", "duration_days": 0},
    {"destination": "Paris", "travel_date": "2030-10-15", "duration_days": 90},
    {"destination": "Paris", "travel_date": "2030-10-15", "duration_days": 5, "budget": -10},
], ids=["no-destination", "blank-destination", "no-date", "malformed-date", "past-date",
        "zero-duration", "too-long", "negative-budget"])
def test_invalid_requests_are_rejected(fields):
    with pytest.raises(ValidationError):
        TravelRequest.model_validate(fields)
