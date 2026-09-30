"""LLM-dependent paths, exercised offline with a scripted fake LLM."""
from app.schemas import (
    ActivitySchedule,
    ActivitySearchResult,
    FlightSearchResult,
    HotelSearchResult,
    ParsedTravelQuery,
)
from app.tools import activity_tools, flight_tools, hotel_tools
from tests.conftest import future_date


class FakeLLM:
    enabled = True

    def __init__(self, responses: dict):
        self.responses = responses
        self.prompts: list[str] = []

    async def generate_structured(self, prompt, schema):
        self.prompts.append(prompt)
        return self.responses.get(schema)

    async def generate_text(self, prompt):
        self.prompts.append(prompt)
        return "LLM summary grounded in the plan data."


def test_free_text_request_is_parsed_by_planner(run_trip):
    llm = FakeLLM({ParsedTravelQuery: ParsedTravelQuery(
        destination="Rome", travel_date=future_date(), duration_days=3, origin="Cairo")})
    result = run_trip("3 days in Rome from Cairo", llm=llm)

    assert result.state["request_valid"]
    assert result.state["destination"] == "Rome"
    assert result.state["budget"] is None
    assert "LLM summary grounded in the plan data." in result.plan.markdown


def test_llm_schedule_is_validated_and_hallucinated_names_ignored(run_trip, paris_request):
    llm = FakeLLM({ActivitySchedule: ActivitySchedule(assignments=[
        {"name": "Palace of Versailles", "day": 2},
        {"name": "Totally Made Up Attraction", "day": 1},
        {"name": "Louvre Museum", "day": 99},
    ])})
    result = run_trip(paris_request, llm=llm)
    activities = {a["name"]: a for a in result.blackboard.read("activities")["options"]}

    assert activities["Palace of Versailles"]["day"] == 2
    assert activities["Louvre Museum"]["day"] is None
    assert "Totally Made Up Attraction" not in activities
    assert "Totally Made Up Attraction" not in result.plan.markdown


def test_web_search_results_are_extracted_and_incomplete_items_dropped(run_trip, paris_request, cfg, monkeypatch):
    cfg.TRAVEL_DATA_PROVIDER = "tavily"
    cfg.TAVILY_API_KEY = "test-key"

    async def fake_search(query, cfg=None, max_results=6):
        return [{"title": "result", "url": "https://example.com/r", "content": "..."}]

    for module in (flight_tools, hotel_tools, activity_tools):
        monkeypatch.setattr(module, "tavily_search", fake_search)

    llm = FakeLLM({
        FlightSearchResult: FlightSearchResult(flights=[
            {"airline": "EgyptAir", "direction": "outbound", "departure": "Cairo", "arrival": "Paris",
             "departure_time": "09:45", "arrival_time": "13:55", "duration": "5h 10m", "price": 350,
             "currency": "USD", "source": "https://example.com/r"},
        ]),
        HotelSearchResult: HotelSearchResult(hotels=[
            {"name": "Web Hotel", "location": "Paris", "rating": 4.2, "price_per_night": 150,
             "total_price": 750, "currency": "USD", "source": "https://example.com/r"},
        ]),
        ActivitySearchResult: ActivitySearchResult(activities=[]),
    })
    result = run_trip(paris_request, llm=llm)

    assert result.state["flight_status"] == "ok"
    assert result.state["hotel_status"] == "ok"
    assert result.state["activity_status"] == "empty"
    assert result.blackboard.read("hotels")["source"] == "tavily_web_search"
    budget = result.state["budget_result"]
    assert "return flight" in budget["unavailable_components"]
    assert budget["selected"]["hotel"]["name"] == "Web Hotel"
    assert "demo catalog" not in result.plan.markdown
