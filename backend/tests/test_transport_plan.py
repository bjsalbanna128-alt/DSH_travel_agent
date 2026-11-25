"""Intraday transport is built by code; intercity legs are ranged estimates."""

from app.services.transport_plan import (
    build_intraday_transports,
    intercity_median_total,
    parse_intercity_estimates,
    segment_fare,
)

HOTEL = {"name": "全季酒店", "location": {"lat": 30.65, "lng": 104.06}}
A1 = {"name": "宽窄巷子", "location": {"lat": 30.66, "lng": 104.05}}
A2 = {"name": "杜甫草堂", "location": {"lat": 30.66, "lng": 104.03}}
A3 = {"name": "武侯祠", "location": {"lat": 30.64, "lng": 104.04}}

VALID_INTERCITY = [
    {"type": "train", "from_location": "北京", "to_location": "上海",
     "duration_hours_min": 4.5, "duration_hours_max": 5.5,
     "price_cny_min": 553, "price_cny_max": 662},
    {"type": "flight", "from_location": "北京", "to_location": "上海",
     "duration_hours_min": 2, "duration_hours_max": 2.5,
     "price_cny_min": 700, "price_cny_max": 1200},
]


def test_intraday_transport_follows_attraction_order():
    legs = build_intraday_transports([A1, A2, A3], HOTEL, "metro")

    assert [(leg.from_location, leg.to_location) for leg in legs] == [
        ("全季酒店", "宽窄巷子"),
        ("宽窄巷子", "杜甫草堂"),
        ("杜甫草堂", "武侯祠"),
        ("武侯祠", "全季酒店"),
    ]


def test_intraday_transport_has_no_departure_times():
    legs = build_intraday_transports([A1, A2], HOTEL, "metro")

    assert all(leg.departure_time == "" and leg.arrival_time == "" for leg in legs)
    assert all(leg.duration_minutes > 0 for leg in legs)


def test_intraday_transport_amount_uses_unit_price():
    legs = build_intraday_transports([A1, A2, A3], HOTEL, "metro")

    assert len(legs) == 4
    assert all(leg.price_cny == segment_fare(1, "metro") for leg in legs)
    assert sum(leg.price_cny for leg in legs) == 12.0


def test_intraday_transport_taxi_uses_distance():
    legs = build_intraday_transports([A1], HOTEL, "taxi")

    assert len(legs) == 2
    assert all(leg.price_cny >= 13.0 for leg in legs)


def test_intraday_transport_edges():
    assert len(build_intraday_transports([A1, A2, A3], None, "metro")) == 2
    assert len(build_intraday_transports([A1], HOTEL, "metro")) == 2
    assert build_intraday_transports([], HOTEL, "metro") == []


def test_intercity_estimate_rejects_invalid_range():
    inverted = {
        "type": "train", "from_location": "北京", "to_location": "上海",
        "duration_hours_min": 6, "duration_hours_max": 4,
        "price_cny_min": 553, "price_cny_max": 662,
    }
    too_wide = {
        "type": "train", "from_location": "北京", "to_location": "上海",
        "duration_hours_min": 5, "duration_hours_max": 6,
        "price_cny_min": 100, "price_cny_max": 900,
    }
    no_price = {
        "type": "flight", "from_location": "北京", "to_location": "上海",
        "duration_hours_min": 2, "duration_hours_max": 3,
        "price_cny_min": 0, "price_cny_max": 0,
    }
    unknown_mode = {
        "type": "bus", "from_location": "北京", "to_location": "上海",
        "duration_hours_min": 20, "duration_hours_max": 24,
        "price_cny_min": 300, "price_cny_max": 400,
    }

    assert parse_intercity_estimates([inverted, too_wide, no_price, unknown_mode]) == []


def test_intercity_estimate_has_no_times():
    estimates = parse_intercity_estimates(VALID_INTERCITY)

    dumped = [item.model_dump() for item in estimates]
    assert all("departure_time" not in item and "arrival_time" not in item for item in dumped)


def test_intercity_estimate_covers_train_and_flight():
    estimates = parse_intercity_estimates(VALID_INTERCITY)

    assert {item.type for item in estimates} == {"train", "flight"}
    assert intercity_median_total(estimates) == 1557.5


def test_intercity_estimate_allows_short_haul_without_flight():
    train_only = [VALID_INTERCITY[0]]

    estimates = parse_intercity_estimates(train_only)

    assert [item.type for item in estimates] == ["train"]


def test_intercity_estimate_dedupes_identical_bands():
    estimates = parse_intercity_estimates(VALID_INTERCITY + VALID_INTERCITY)

    assert len(estimates) == 2


def test_intercity_estimate_ignores_non_list_payload():
    assert parse_intercity_estimates(None) == []
    assert parse_intercity_estimates({"intercity": []}) == []
