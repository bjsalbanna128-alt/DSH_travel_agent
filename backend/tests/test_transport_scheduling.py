"""Transport scheduling must not depend on the plan being non-empty."""

from unittest.mock import AsyncMock

import pytest

from app.graph import travel_graph
from app.graph.nodes.agents import _normalize_transport
from app.graph.nodes.supervisor import _build_state_summary, supervisor_node
from app.providers.llm.deepseek import DeepSeekProvider

DONE_UP_TO_RESTAURANT = {
    "travel_request": {"destination": "成都", "days": 3, "pace": "moderate"},
    "attractions": [{"name": "宽窄巷子"}],
    "routes": [{"day": 1}],
    "hotels": [{"name": "某酒店"}],
    "restaurants": [{"name": "某餐厅"}],
    "agent_history": [],
    "constraint_violations": [],
}


@pytest.mark.parametrize("raw", [{}, None, [], "not a dict", {"intercity": "bad", "intraday": 5}])
def test_normalize_transport_always_returns_both_keys(raw):
    assert _normalize_transport(raw) == {"intercity": [], "intraday": []}


def test_normalize_transport_keeps_usable_lists():
    plan = {"intercity": [{"type": "train"}], "intraday": [[{"type": "metro"}]]}

    assert _normalize_transport(plan) == plan


def test_invalid_field_preserves_other_transport_legs(caplog):
    legs = [{"type": "train", "day": 3}]

    assert _normalize_transport({"intercity": legs, "intraday": "bad"}) == {
        "intercity": legs,
        "intraday": [],
    }
    assert "Transport plan field intraday is not a list" in caplog.text


async def test_empty_transport_plan_is_not_rescheduled():
    """Regression: an empty but valid plan used to loop until the safety valve."""
    state = {**DONE_UP_TO_RESTAURANT, "transport": {"intercity": [], "intraday": []}}

    result = await supervisor_node(state)

    assert result["next_agents"] == ["itinerary_compiler"]
    assert "交通: 已完成" in _build_state_summary(state)


async def test_transport_runs_when_never_attempted():
    result = await supervisor_node(dict(DONE_UP_TO_RESTAURANT))

    assert result["next_agents"] == ["transport"]


@pytest.mark.parametrize(
    ("max_iterations", "used", "expected"),
    [
        (5, 4, "transport"),
        (5, 5, "itinerary_compiler"),
        (30, 15, "transport"),
        (None, 15, "itinerary_compiler"),
    ],
)
async def test_safety_valve_reads_configured_limit(max_iterations, used, expected, caplog):
    history = [{"agent_name": "restaurant_agent"}]
    state = {**DONE_UP_TO_RESTAURANT, "current_iteration": used, "agent_history": history}
    if max_iterations is not None:
        state["max_iterations"] = max_iterations

    result = await supervisor_node(state)

    assert result["next_agents"] == [expected]
    assert result["current_iteration"] == used + 1
    assert result["agent_history"][:-1] == history
    limit = max_iterations if max_iterations is not None else 15
    assert f"当前迭代: {used}/{limit}" in _build_state_summary(state)
    assert (f"hit max iterations ({limit})" in caplog.text) == (expected == "itinerary_compiler")


@pytest.mark.parametrize("replan", [False, True])
async def test_empty_transport_runs_once_through_graph(monkeypatch, replan):
    chat = AsyncMock(side_effect=[
        '{"next_agent": "route"}',
        '{"intercity": [], "intraday": []}',
    ])
    monkeypatch.setattr(DeepSeekProvider, "__init__", lambda self, model=None: None)
    monkeypatch.setattr(DeepSeekProvider, "chat", chat)

    async def parse_request(state):
        return {"travel_request": {
            **DONE_UP_TO_RESTAURANT["travel_request"],
            "budget": {"total_cny": 100},
        }}

    def stub_result(key):
        async def run(state):
            return {key: DONE_UP_TO_RESTAURANT[key]}

        return run

    async def compile_itinerary(state):
        assert state["transport"] == {"intercity": [], "intraday": []}
        return {"itinerary": {
            "title": "步行行程",
            "duration_days": 3,
            "total_budget_estimate_cny": 200 if replan else 100,
            "day_plans": [{"day": 1, "attractions": state["attractions"]}],
        }}

    monkeypatch.setattr(travel_graph, "parse_request_node", parse_request)
    monkeypatch.setattr(travel_graph, "attraction_node", stub_result("attractions"))
    monkeypatch.setattr(travel_graph, "route_node", stub_result("routes"))
    monkeypatch.setattr(travel_graph, "hotel_node", stub_result("hotels"))
    monkeypatch.setattr(travel_graph, "restaurant_node", stub_result("restaurants"))
    monkeypatch.setattr(travel_graph, "itinerary_compiler_node", compile_itinerary)

    graph = travel_graph.build_travel_graph()
    config = travel_graph.planning_config("tourist", "walking-trip")
    nodes = []
    async for event in graph.astream({"max_iterations": 15}, config):
        nodes.extend(name for name in event if name != "supervisor")

    expected = [
        "parse_request", "attraction_node", "route_node", "hotel_node", "restaurant_node",
        "transport_node", "itinerary_compiler_node", "constraint_validator_node",
    ]
    if replan:
        expected += [
            "attraction_node", "route_node", "itinerary_compiler_node", "constraint_validator_node",
        ]
    assert nodes == [*expected, "__interrupt__"]
    snapshot = await graph.aget_state(config)
    history = snapshot.values["agent_history"]
    assert sum(entry["agent_name"] == "transport_agent" for entry in history) == 1
    assert chat.await_count == 2
