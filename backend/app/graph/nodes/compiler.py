"""Itinerary compiler, constraint validator, human approval, and feedback handler."""

import json
import logging
import uuid
from datetime import datetime

from app.providers.llm.deepseek import DeepSeekProvider, safe_json_parse
from app.schemas.travel_state import (
    AgentExecution, DayPlan, Itinerary, ApprovalRequest,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Itinerary Compiler
# ═══════════════════════════════════════════════════════════════

COMPILER_SYSTEM_PROMPT = """你是一个行程整合专家。将所有Agent的输出组装为完整的每日行程。

## 任务
1. 将景点按route分配到每天
2. 为每天匹配酒店和午餐/晚餐餐厅
3. 计算每日预算
4. 生成整体旅行建议

## 输出格式
{
  "title": "成都5日文化美食之旅",
  "destination": "成都",
  "duration_days": 5,
  "total_budget_estimate_cny": 18000,
  "day_plans": [
    {
      "day": 1,
      "date": "Day 1",
      "attractions": [{"name": "宽窄巷子", ...}],
      "route": null,
      "lunch": {"name": "餐厅名", ...},
      "dinner": {"name": "餐厅名", ...},
      "hotel": {"name": "酒店名", ...},
      "transport": [],
      "notes": ""
    }
  ],
  "overall_tips": "整体建议"
}

只输出JSON。"""


async def itinerary_compiler_node(state: dict) -> dict:
    """Compile all agent outputs into a complete itinerary."""
    llm = DeepSeekProvider(model=DeepSeekProvider.CHAT_MODEL)
    req = state.get("travel_request", {})
    attractions = state.get("attractions", [])
    routes = state.get("routes", [])
    hotels = state.get("hotels", [])
    restaurants = state.get("restaurants", [])

    # Check for partial edits
    partial_edits = state.get("user_partial_edits")

    ctx = {
        "destination": req.get("destination", ""),
        "days": req.get("days", 0),
        "preferences": req.get("preferences", []),
        "attractions": json.dumps(attractions, ensure_ascii=False, indent=2),
        "routes": json.dumps(routes, ensure_ascii=False, indent=2),
        "hotels": json.dumps(hotels, ensure_ascii=False, indent=2),
        "restaurants": json.dumps(restaurants, ensure_ascii=False, indent=2),
    }

    user_prompt = json.dumps(ctx, ensure_ascii=False, indent=2)
    if partial_edits:
        user_prompt = (
            f"## 局部编辑指令\n{json.dumps(partial_edits, ensure_ascii=False)}\n\n"
            f"## 当前行程（只更新受影响的day）\n{user_prompt}"
        )

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
    for dp in data.get("day_plans", []):
        day_num = dp.get("day", 0)
        if not day_num:
            day_num = len(day_plans) + 1

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

        # Sanitize transport
        transport = []
        for t in dp.get("transport", []):
            if isinstance(t, str):
                transport.append({"type": t, "from_location": "", "to_location": "",
                                  "departure_time": "", "arrival_time": "", "price_cny": 0})
            elif isinstance(t, dict):
                transport.append(t)

        try:
            day_plans.append(DayPlan(
                day=day_num,
                attractions=attrs,
                route=route,
                lunch=lunch,
                dinner=dinner,
                hotel=hotel,
                transport=transport,
                notes=dp.get("notes", ""),
            ))
        except Exception as e:
            logger.warning(f"Invalid DayPlan day={day_num}, using minimal plan: {e}")
            day_plans.append(DayPlan(day=day_num, attractions=attrs))

    # Build Itinerary
    itinerary = Itinerary(
        title=data.get("title", f"{req.get('destination')}{req.get('days')}日游"),
        destination=req.get("destination", ""),
        duration_days=req.get("days", 0),
        total_budget_estimate_cny=data.get("total_budget_estimate_cny", 0),
        day_plans=day_plans,
        overall_tips=data.get("overall_tips", ""),
        version=state.get("itinerary", {}).get("version", 1) + 1,
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
        if total_hours > 12:
            violations.append(
                f"第{dp.get('day')}天行程过满：景点总耗时{total_hours}小时"
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
        approval_id=str(uuid.uuid4()),
        type="itinerary",
        question=(
            f"行程「{itinerary.get('title', '您的旅行')}」已生成 "
            f"({itinerary.get('duration_days', 0)}天, "
            f"预估¥{itinerary.get('total_budget_estimate_cny', 0):.0f})，是否确认？"
        ),
        options=[
            "确认行程",
            "调整部分安排",
            "降低预算",
            "换一批景点",
        ],
        data=itinerary,
    )

    return {"pending_approval": approval.model_dump()}


# ═══════════════════════════════════════════════════════════════
# Handle Feedback
# ═══════════════════════════════════════════════════════════════

FEEDBACK_SYSTEM_PROMPT = """解析用户的行程修改意见，输出结构化编辑指令。

## 输出格式
{
  "action": "partial_edit|full_replan",
  "edits": {"day_index": 0, "action": "replace_hotel|remove_attraction|add_attraction|reduce_budget", ...},
  "feedback_summary": "总结用户意图"
}

只输出JSON。"""


async def handle_feedback_node(state: dict) -> dict:
    """Process user feedback and convert to actionable edits."""
    llm = DeepSeekProvider(model=DeepSeekProvider.CHAT_MODEL)
    feedback = state.get("user_feedback", "")

    if not feedback:
        return {"next_agents": [], "needs_replan": False}

    raw = await llm.chat(
        system_prompt=FEEDBACK_SYSTEM_PROMPT,
        user_prompt=f"用户反馈: {feedback}\n行程概要: {json.dumps(state.get('itinerary', {}), ensure_ascii=False)[:2000]}",
        temperature=0.3,
        json_mode=True,
    )

    data = safe_json_parse(raw, "feedback")

    if data.get("action") == "partial_edit":
        return {
            "user_partial_edits": data.get("edits", {}),
            "user_feedback": "",
            "next_agents": [],
        }

    # Full replan
    return {
        "user_feedback": "",
        "needs_replan": True,
        "next_agents": ["attraction"],
        "attractions": [],
        "routes": [],
        "hotels": [],
        "restaurants": [],
        "transport": {},
        "itinerary": {},
    }
