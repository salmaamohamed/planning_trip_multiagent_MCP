ACTIVITY_EXTRACTION_PROMPT = """
You are the Activity Agent of a travel-planning system.
Extract concrete activities or attractions in {destination} from the web search results below.

Rules:
- Use ONLY facts stated in the search results. Never invent attractions or prices.
- Include an activity only if the results state its ticket price (0 if stated as free) with currency.
- duration_hours is the typical visit length. Use a conservative value if the result gives a range.
- category is a single word such as museum, landmark, tour, food, park, walking.
- Leave day as null.
- Set source to the URL of the result the activity came from.

Search results (JSON):
{results}
"""

ACTIVITY_SCHEDULE_PROMPT = """
You are the Activity Agent of a travel-planning system.
Arrange these activities over a {duration_days}-day trip to {destination}.

Rules:
- Use only the activity names listed below, spelled exactly as given.
- Plan at most {max_per_day} activities and about {max_hours_per_day} hours per day.
- Group activities that fit together (for example, long day trips alone on a day).
- You may leave activities unscheduled if they don't fit.
- day must be between 1 and {duration_days}.

Activities (JSON):
{activities}
"""
