"""Itinerary compiler, constraint validator, and the draft review boundary."""

import json
import logging
from datetime import datetime

from app.providers.llm.deepseek import DeepSeekProvider, safe_json_parse
from langgraph.types import interrupt

from app.schemas.travel_state import (
    AgentExecution, DayPlan, Itinerary, ApprovalRequest,
)
from app.services.itinerary_costs import estimate_day_cost, traveler_count
from app.services.transport_plan import (
    build_intraday_transports, intercity_median_total, parse_intercity_estimates,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Itinerary Compiler
# ═══════════════════════════════════════════════════════════════

COMPILER_SYSTEM_PROMPT = """你是一个行程整合专家。将所有Agent的输出组装为完整的每日行程。

## 任务
1. 将景点按route分配到每天
2. 为每天匹配酒店和午餐/晚餐餐厅
3. 参考交通安排给景点和餐饮留出合理时间，交通段和费用由程序合并计算
4. 生成整体旅行建议

## 输出格式
{
  "title": "成都5日文化美食之旅",
  "destination": "成都",
  "duration_days": 5,
  "day_plans": [
    {
      "day": 1,
      "date": "Day 1",
      "attractions": [{"name": "宽窄巷子", ...}],
      "route": null,
      "lunch": {"name": "餐厅名", ...},
      "dinner": {"name": "餐厅名", ...},
      "hotel": {"name": "酒店名", ...},
      "notes": ""
    }
  ],
  "overall_tips": "整体建议"
}

只输出JSON。"""


def _attach_intraday_transports(day_plans: list[DayPlan]) -> None:
    """Build each day's legs from its own attraction order, in place."""
    for plan in day_plans:
        travel_mode = plan.route.travel_mode if plan.route else "walking"
        plan.transport = build_intraday_transports(
            [attraction.model_dump() for attraction in plan.attractions],
            plan.hotel.model_dump() if plan.hotel else None,
            travel_mode,
        )


async def itinerary_compiler_node(state: dict) -> dict:
    """Compile all agent outputs into a complete itinerary."""
    llm = DeepSeekProvider(model=DeepSeekProvider.CHAT_MODEL)
    req = state.get("travel_request", {})
    attractions = state.get("attractions", [])
    routes = state.get("routes", [])
    hotels = state.get("hotels", [])
    restaurants = state.get("restaurants", [])
    days = req.get("days", 0)
    destination = req.get("destination", "")
    transport_state = state.get("transport")
    intercity_estimates = parse_intercity_estimates(
        transport_state.get("intercity") if isinstance(transport_state, dict) else None
    )

    ctx = {
        "destination": destination,
        "days": days,
        "preferences": req.get("preferences", []),
        "attractions": json.dumps(attractions, ensure_ascii=False, indent=2),
        "routes": json.dumps(routes, ensure_ascii=False, indent=2),
        "hotels": json.dumps(hotels, ensure_ascii=False, indent=2),
        "restaurants": json.dumps(restaurants, ensure_ascii=False, indent=2),
    }

    user_prompt = json.dumps(ctx, ensure_ascii=False, indent=2)

    raw = await llm.chat(
        system_prompt=COMPILER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.4,
        json_mode=True,
        max_tokens=16384,  # 5-day itinerary needs lots of tokens
    )

    data = safe_json_parse(raw, "compiler")

    # Build day plans with sanitized data (LLM output is often incomplete)
    day_plans = []
    planned_days = set()
    for dp in data.get("day_plans", []):
        try:
            day_num = int(dp.get("day") or len(day_plans) + 1)
        except (ValueError, TypeError):
            continue
        if not 1 <= day_num <= days or day_num in planned_days:
            continue
        planned_days.add(day_num)

        # Sanitize attractions
        attrs = []
        for a in dp.get("attractions", []):
            if isinstance(a, str):
                attrs.append({"name": a, "description": a, "visit_duration_hours": 2.0,
                              "rating": 4.0, "ticket_price_cny": 0, "category": "cultural"})
            elif isinstance(a, dict):
                attrs.append(a)

        # Sanitize route — LLM often outputs a string or dict missing "day" field
        route = dp.get("route")
        if isinstance(route, str):
            # LLM wrote "metro" or "步行" etc.
            route = {"day": day_num, "travel_mode": route,
                     "attraction_ids": [], "total_distance_km": 0,
                     "estimated_travel_time_minutes": 0, "constraint_violations": []}
        elif isinstance(route, dict):
            route.setdefault("day", day_num)
            route.setdefault("attraction_ids", [])
            route.setdefault("total_distance_km", 0)
            route.setdefault("travel_mode", "walking")
            route.setdefault("estimated_travel_time_minutes", 0)
            route.setdefault("constraint_violations", [])
        else:
            route = None

        # Sanitize lunch/dinner — LLM often uses strings
        def _sanitize_meal(m):
            if isinstance(m, str):
                return {"name": m, "cuisine": "", "avg_price_per_person_cny": 0, "rating": 4.0}
            if isinstance(m, dict):
                return m
            return None

        lunch = _sanitize_meal(dp.get("lunch"))
        dinner = _sanitize_meal(dp.get("dinner"))
        hotel = dp.get("hotel") if isinstance(dp.get("hotel"), dict) else None

        try:
            day_plans.append(DayPlan(
                day=day_num,
                date=dp.get("date") or "",
                attractions=attrs,
                route=route,
                lunch=lunch,
                dinner=dinner,
                hotel=hotel,
                transport=[],
                notes=dp.get("notes", ""),
            ))
        except Exception as e:
            logger.warning(f"Invalid DayPlan day={day_num}, using minimal plan: {e}")
            day_plans.append(DayPlan(day=day_num, attractions=attrs))

    day_plans.sort(key=lambda plan: plan.day)
    _attach_intraday_transports(day_plans)
    people = traveler_count(req)
    total_estimate = sum(estimate_day_cost(plan.model_dump(), people) for plan in day_plans)
    total_estimate += intercity_median_total(intercity_estimates)

    # Build Itinerary
    itinerary = Itinerary(
        title=data.get("title", f"{req.get('destination')}{req.get('days')}日游"),
        destination=destination,
        duration_days=days,
        total_budget_estimate_cny=round(total_estimate, 2),
        day_plans=day_plans,
        intercity_estimates=intercity_estimates,
        overall_tips=data.get("overall_tips", ""),
        version=state.get("itinerary", {}).get("version", 0) + 1,
        created_at=datetime.now().isoformat(),
    )

    # Save version snapshot
    snapshot = {
        "version": itinerary.version,
        "itinerary": itinerary.model_dump(mode="json"),
        "created_at": datetime.now().isoformat(),
        "description": f"Version {itinerary.version}",
    }
    versions = list(state.get("itinerary_versions", []))
    versions.append(snapshot)

    execution = AgentExecution(
        agent_name="itinerary_compiler",
        started_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat(),
        output_summary=f"生成了{itinerary.duration_days}天行程",
        llm_calls=1,
        status="done",
    )

    history = list(state.get("agent_history", []))
    history.append(execution.model_dump())

    return {
        "itinerary": itinerary.model_dump(mode="json"),
        "itinerary_versions": versions,
        "agent_history": history,
    }


# ═══════════════════════════════════════════════════════════════
# Constraint Validator
# ═══════════════════════════════════════════════════════════════

async def constraint_validator_node(state: dict) -> dict:
    """Validate itinerary against constraints (no LLM needed)."""
    req = state.get("travel_request", {})
    itinerary = state.get("itinerary", {})
    replan_count = state.get("replan_count", 0)

    violations = []
    budget_limit = req.get("budget", {}).get("total_cny", 0)
    total_estimate = itinerary.get("total_budget_estimate_cny", 0)

    # Budget check
    if budget_limit > 0 and total_estimate > budget_limit * 1.5:
        violations.append(
            f"超出预算：预估{total_estimate:.0f}元 vs 预算{budget_limit:.0f}元"
        )

    # Time check per day
    for dp in itinerary.get("day_plans", []):
        total_hours = sum(
            a.get("visit_duration_hours", 2) for a in dp.get("attractions", [])
        )
        total_hours += (dp.get("route") or {}).get("estimated_travel_time_minutes", 0) / 60
        if total_hours > 12:
            violations.append(
                f"第{dp.get('day')}天行程过满：游览和路途预计{total_hours:.1f}小时"
            )

    # Attraction count check
    total_attrs = sum(
        len(dp.get("attractions", [])) for dp in itinerary.get("day_plans", [])
    )
    if total_attrs == 0:
        violations.append("行程中没有景点")

    # Only replan on FIRST violation — avoid infinite loops
    if replan_count > 0:
        logger.info(f"Already replanned once, accepting constraints with {len(violations)} violations")
        return {
            "constraint_violations": violations,
            "needs_replan": False,  # always proceed after first replan
        }

    needs_replan = len(violations) > 0
    return {
        "constraint_violations": violations,
        "needs_replan": needs_replan,
        "replan_count": replan_count + 1 if needs_replan else replan_count,
    }


# ═══════════════════════════════════════════════════════════════
# Human Approval
# ═══════════════════════════════════════════════════════════════

async def human_approval_node(state: dict) -> dict:
    """Generate approval request and send to user (via SSE event)."""
    itinerary = state.get("itinerary", {})

    approval = ApprovalRequest(
        type="itinerary",
        question=(
            f"行程「{itinerary.get('title', '您的旅行')}」已生成 "
            f"({itinerary.get('duration_days', 0)}天, "
            f"预估¥{itinerary.get('total_budget_estimate_cny', 0):.0f})，是否确认？"
        ),
        options=[
            "确认行程",
            "调整部分安排",
        ],
        data=itinerary,
    )

    interrupt(approval.model_dump())
    return {}
