"""TravelState — unified state schema for the LangGraph StateGraph."""

from datetime import datetime, time
from typing import Annotated, Any, Literal, Optional, TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# LangGraph State (TypedDict — keys persist across nodes)
# ═══════════════════════════════════════════════════════════════


class TravelState(TypedDict, total=False):
    """State schema for the TravelGraph.

    Keys NOT returned by a node PERSIST from the previous state.
    (This is the key difference from StateGraph(dict) which replaces the entire dict.)
    """
    # ── Messages ──
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Identity ──
    user_id: str
    session_id: str
    thread_id: str

    # ── User request ──
    travel_request: dict[str, Any]
    # 必须声明：sse.py 在收到预填充 travel_request 时置 True，parse_request 据此跳过 LLM 解析。
    # 未声明时 LangGraph 会丢弃该键，预填充通道失效。
    skip_parse: bool

    # ── Agent outputs ──
    attractions: list[dict[str, Any]]
    routes: list[dict[str, Any]]
    hotels: list[dict[str, Any]]
    restaurants: list[dict[str, Any]]
    transport: dict[str, Any]

    # ── Final output ──
    itinerary: dict[str, Any]
    itinerary_versions: list[dict[str, Any]]

    # ── Supervisor control ──
    next_agents: list[str]
    agent_history: list[dict[str, Any]]
    current_iteration: int
    max_iterations: int

    # ── HITL ──
    pending_approval: dict[str, Any] | None
    user_feedback: str
    user_partial_edits: dict[str, Any] | None

    # ── Validation ──
    constraint_violations: list[str]
    needs_replan: bool
    replan_count: int
    restriction_snapshot: dict[str, Any]
    scenic_candidates_filtered: bool
    scenic_pois: list[dict[str, Any]]

    # ── Error handling ──
    errors: list[dict[str, Any]]
    retry_counts: dict[str, int]
    fallback_used: dict[str, bool]

    # ── Memory context ──
    user_profile_context: str                        # "用户偏好自然风光，轻松节奏..."
    episodic_memory_context: str                     # "历史相似行程摘要..."
    similar_trips: list[dict[str, Any]]
    supervisor_context: dict[str, Any]


# ═══════════════════════════════════════════════════════════════
# Request / User Input
# ═══════════════════════════════════════════════════════════════


class BudgetConstraint(BaseModel):
    total_cny: float = 0.0
    per_day_cny: float = 0.0


class Travelers(BaseModel):
    adults: int = 1
    children: int = 0  # 0-12
    elderly: int = 0  # 60+


class TravelRequest(BaseModel):
    destination: str = ""
    days: int = 1
    budget: BudgetConstraint = Field(default_factory=BudgetConstraint)
    travelers: Travelers = Field(default_factory=Travelers)
    preferences: list[str] = Field(default_factory=list)
    special_requirements: list[str] = Field(default_factory=list)
    departure_city: str = ""
    travel_time: str = ""  # "2026-08-01" or "春季"
    pace: Literal["relaxed", "moderate", "intensive"] = "moderate"


# ═══════════════════════════════════════════════════════════════
# Agent Outputs
# ═══════════════════════════════════════════════════════════════


class Location(BaseModel):
    lat: float
    lng: float


class Attraction(BaseModel):
    id: str = ""
    name: str
    source: Literal["amap", "chroma"] | None = None
    city: str = ""
    category: str = ""  # natural | cultural | entertainment | shopping
    description: str = ""
    rating: float = 4.0
    visit_duration_hours: float = 2.0
    ticket_price_cny: float = 0.0
    location: Location = Field(default_factory=lambda: Location(lat=0, lng=0))
    opening_hours: str = ""  # "08:00-17:00"
    tags: list[str] = Field(default_factory=list)
    suitable_for: list[str] = Field(default_factory=list)
    recommended_reason: str = ""


class Route(BaseModel):
    day: int
    attraction_ids: list[str] = Field(default_factory=list)
    total_distance_km: float = 0.0
    travel_mode: str = "walking"  # walking | bus | metro | taxi
    estimated_travel_time_minutes: int = 0
    constraint_violations: list[str] = Field(default_factory=list)


class Hotel(BaseModel):
    id: str = ""
    name: str
    area: str = ""
    price_per_night_cny: float = 0.0
    rating: float = 4.0
    location: Location = Field(default_factory=lambda: Location(lat=0, lng=0))
    amenities: list[str] = Field(default_factory=list)
    description: str = ""
    booking_url: str = ""


class Restaurant(BaseModel):
    id: str = ""
    name: str
    cuisine: str = ""
    area: str = ""
    avg_price_per_person_cny: float = 0.0
    rating: float = 4.0
    location: Location = Field(default_factory=lambda: Location(lat=0, lng=0))
    must_try_dishes: list[str] = Field(default_factory=list)
    description: str = ""


class TransportOption(BaseModel):
    type: str = ""  # flight | train | bus | metro | taxi | walk
    from_location: str = ""
    to_location: str = ""
    departure_time: str = ""
    arrival_time: str = ""
    duration_minutes: int = 0  # estimated leg time; times are left empty by design
    price_cny: float = 0.0
    booking_url: str = ""


class IntercityEstimate(BaseModel):
    """Ranged estimate for an intercity leg. Never carries departure times."""

    type: str = ""  # train | flight
    from_location: str = ""
    to_location: str = ""
    duration_hours_min: float = 0.0
    duration_hours_max: float = 0.0
    price_cny_min: float = 0.0
    price_cny_max: float = 0.0
    is_estimate: bool = True
    note: str = "预估区间，请自行比价"


class TransportPlan(BaseModel):
    intercity: list[IntercityEstimate] = Field(default_factory=list)
    intraday: list[list[TransportOption]] = Field(default_factory=list)


class DayPlan(BaseModel):
    day: int
    date: str = ""
    attractions: list[Attraction] = Field(default_factory=list)
    route: Route | None = None
    lunch: Restaurant | None = None
    dinner: Restaurant | None = None
    hotel: Hotel | None = None
    transport: list[TransportOption] = Field(default_factory=list)
    notes: str = ""


class Itinerary(BaseModel):
    title: str = ""
    destination: str = ""
    duration_days: int = 0
    total_budget_estimate_cny: float = 0.0
    day_plans: list[DayPlan] = Field(default_factory=list)
    intercity_estimates: list[IntercityEstimate] = Field(default_factory=list)
    overall_tips: str = ""
    version: int = 1
    created_at: str = ""


class ItinerarySnapshot(BaseModel):
    version: int
    itinerary: Itinerary
    created_at: datetime = Field(default_factory=datetime.now)
    description: str = ""


# ═══════════════════════════════════════════════════════════════
# HITL / Progress / Execution
# ═══════════════════════════════════════════════════════════════


class ApprovalRequest(BaseModel):
    approval_id: str = ""
    type: str = "itinerary"  # itinerary | day | attraction | hotel
    question: str = ""
    options: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class AgentProgress(BaseModel):
    agent_name: str
    status: str = "pending"  # pending | running | done | failed
    message: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ProgressInfo(BaseModel):
    overall_percent: float = 0.0
    current_phase: str = ""
    agents: list[AgentProgress] = Field(default_factory=list)


class AgentExecution(BaseModel):
    agent_name: str
    started_at: str = ""
    completed_at: str = ""
    input_summary: str = ""
    output_summary: str = ""
    llm_calls: int = 0
    tokens_total: int = 0
    cost_rmb: float = 0.0
    status: str = "running"
    error: str | None = None
