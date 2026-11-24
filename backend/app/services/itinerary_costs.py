"""Shared estimates for generated and revised itineraries."""


def traveler_count(request: dict) -> int:
    travelers = request.get("travelers") or {}
    return max(1, sum(travelers.get(key, 0) for key in ("adults", "children", "elderly")))


def estimate_day_cost(day: dict, people: int) -> float:
    tickets = sum(a.get("ticket_price_cny", 0) for a in day.get("attractions") or [])
    meals = sum((day.get(meal) or {}).get("avg_price_per_person_cny", 0) for meal in ("lunch", "dinner"))
    transport = sum(t.get("price_cny", 0) for t in day.get("transport") or [])
    hotel = (day.get("hotel") or {}).get("price_per_night_cny", 0)
    return (tickets + meals + transport) * people + hotel
