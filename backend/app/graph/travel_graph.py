"""TravelGraph — LangGraph StateGraph builder for the travel planning system."""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from pathlib import Path

from app.schemas.travel_state import TravelState
from app.graph.nodes.parse_request import parse_request_node
from app.graph.nodes.supervisor import supervisor_node
from app.graph.nodes.agents import (
    attraction_node, route_node, hotel_node, restaurant_node, transport_node,
)
from app.graph.nodes.compiler import (
    itinerary_compiler_node, constraint_validator_node,
    human_approval_node, handle_feedback_node,
)

AGENT_DISPLAY_NAMES = {
    "parse_request": "解析需求",
    "supervisor": "分析规划策略",
    "attraction_node": "推荐景点",
    "route_node": "规划路线",
    "hotel_node": "推荐酒店",
    "restaurant_node": "找餐厅",
    "transport_node": "规划交通",
    "itinerary_compiler_node": "生成行程",
    "constraint_validator_node": "校验约束",
    "human_approval_node": "等待确认",
    "handle_feedback_node": "处理反馈",
}


def _route_from_supervisor(state: TravelState) -> str:
    """Route from supervisor based on next_agents."""
    agents = state.get("next_agents", [])
    if not agents:
        return END

    agent = agents[0]
    routing_map = {
        "attraction": "attraction_node",
        "route": "route_node",
        "hotel": "hotel_node",
        "restaurant": "restaurant_node",
        "transport": "transport_node",
        "itinerary_compiler": "itinerary_compiler_node",
        "human_approval": "human_approval_node",
    }
    return routing_map.get(agent, END)


def _route_from_validator(state: TravelState) -> str:
    """Route from validator: replan → supervisor, pass → human_approval."""
    if state.get("needs_replan", False):
        # Add violation context to user_feedback for replan
        violations = state.get("constraint_violations", [])
        return "supervisor"
    return "human_approval_node"


def _route_from_approval(state: TravelState) -> str:
    """Route from human_approval: feedback → handle_feedback, else → END."""
    pending = state.get("pending_approval")
    if pending is None:
        return END
    feedback = state.get("user_feedback", "")
    if feedback:
        return "handle_feedback_node"
    # Check if approval was granted (frontend resumes with empty feedback = approved)
    return END


def build_travel_graph(checkpointer=None):
    """Build and compile the TravelGraph."""
    builder = StateGraph(TravelState)

    # Add nodes
    builder.add_node("parse_request", parse_request_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("attraction_node", attraction_node)
    builder.add_node("route_node", route_node)
    builder.add_node("hotel_node", hotel_node)
    builder.add_node("restaurant_node", restaurant_node)
    builder.add_node("transport_node", transport_node)
    builder.add_node("itinerary_compiler_node", itinerary_compiler_node)
    builder.add_node("constraint_validator_node", constraint_validator_node)
    builder.add_node("human_approval_node", human_approval_node)
    builder.add_node("handle_feedback_node", handle_feedback_node)

    # Entry
    builder.set_entry_point("parse_request")
    builder.add_edge("parse_request", "supervisor")

    # Supervisor conditional routing
    builder.add_conditional_edges(
        "supervisor",
        _route_from_supervisor,
        {
            "attraction_node": "attraction_node",
            "route_node": "route_node",
            "hotel_node": "hotel_node",
            "restaurant_node": "restaurant_node",
            "transport_node": "transport_node",
            "itinerary_compiler_node": "itinerary_compiler_node",
            "human_approval_node": "human_approval_node",
            END: END,
        },
    )

    # All agent nodes return to supervisor
    for name in ["attraction_node", "route_node", "hotel_node", "restaurant_node", "transport_node"]:
        builder.add_edge(name, "supervisor")

    # Compiler → validator
    builder.add_edge("itinerary_compiler_node", "constraint_validator_node")

    # Validator conditional
    builder.add_conditional_edges(
        "constraint_validator_node",
        _route_from_validator,
        {"supervisor": "supervisor", "human_approval_node": "human_approval_node"},
    )

    # Approval conditional
    builder.add_conditional_edges(
        "human_approval_node",
        _route_from_approval,
        {"handle_feedback_node": "handle_feedback_node", END: END},
    )

    # Feedback → supervisor
    builder.add_edge("handle_feedback_node", "supervisor")

    # Compile with checkpointer (MemorySaver — trip data persisted via SQLAlchemy)
    if checkpointer is None:
        print("[TravelGraph] Using MemorySaver (trip data persisted via SQLAlchemy)")
        checkpointer = MemorySaver()

    return builder.compile(checkpointer=checkpointer)


# Create singleton
travel_graph = build_travel_graph()


def planning_config(user_id: str, thread_id: str) -> dict[str, dict[str, str]]:
    """Scope the checkpoint key while retaining the public thread ID."""
    return {"configurable": {"thread_id": f"{user_id}:{thread_id}"}}
