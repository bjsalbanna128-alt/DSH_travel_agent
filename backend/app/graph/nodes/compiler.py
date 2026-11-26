"""Itinerary compiler, constraint validator, and the draft review boundary."""

import json
import logging
from datetime import datetime

from app.providers.llm.deepseek import DeepSeekProvider, safe_json_parse
from langgraph.types import interrupt

from app.schemas.travel_state import (
    AgentExecution, DayPlan, Hotel, Itinerary, ApprovalRequest,
)
from app.services.itinerary_costs import estimate_day_cost, traveler_count
from app.services.planning_quality import annotate, assess, route_guidance, with_poi_identity
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


def _resolve_start_date(text: str):
    """Best-effort departure date: ISO, YYYY-MM, or 'M月D日' (next occurrence)."""
    import re
    from datetime import date

    raw = (text or "").strip()
    for candidate in (raw[:10], f"{raw[:7]}-01"):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            continue
    match = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", raw)
    if match:
        today = date.today()
        try:
            resolved = date(today.year, int(match.group(1)), int(match.group(2)))
        except ValueError:
            return None
        return resolved if resolved >= today else date(today.year + 1, resolved.month, resolved.day)
    return None


def _apply_day_dates(day_plans: list[DayPlan], travel_time: str) -> None:
    """Fill each day's absolute date from the departure date plus its offset."""
    from datetime import timedelta

    start = _resolve_start_date(travel_time)

    def _valid(value: str) -> bool:
        from datetime import date as _date
        try:
            _date.fromisoformat(str(value)[:10])
            return True
        except ValueError:
            return False

    for plan in day_plans:
        if _valid(plan.date):
            continue
        # 「Day 1」这类不是日期的值直接丢弃，避免下游按日期查价时拿到脏数据。
        plan.date = (start + timedelta(days=max(0, plan.day - 1))).isoformat() if start else ""


def _attach_hotel_offer(hotel, known: list) -> dict | None:
    """酒店也按名称回填可售信息：LLM 逐日计划里的酒店是它自己复述的，不带 offer。"""
    if not isinstance(hotel, dict):
        return None
    name = str(hotel.get("name") or "").strip()
    if not name:
        return hotel
    for candidate in known:
        if str(candidate.get("name") or "").strip() == name and candidate.get("offer"):
            merged = dict(hotel)
            for extra in ("id", "content_id", "offer", "area"):
                if candidate.get(extra):
                    merged[extra] = candidate[extra]
            return merged
    return hotel


def _with_catalog_note(overall_tips: str, state: dict) -> str:
    """本次没拿到可售库存时，在行程里说清楚，别让用户以为是我们的货。"""
    if state.get("catalog_available", True):
        return overall_tips
    note = "本次行程未检索到可预订库存（商品检索异常或该城市暂无上架商品），行程内容仅供参考。"
    return f"{note}\n{overall_tips}".strip()


def _fill_missing_hotels(day_plans: list[DayPlan], hotels: list) -> None:
    """Every night before the last day needs a hotel, even if the LLM skipped it."""
    if not day_plans or not hotels:
        return
    fallback = next(
        (hotel for hotel in hotels if (hotel.get("offer") or {}).get("sellable")), hotels[0],
    )
    for plan in day_plans[:-1]:
        if plan.hotel is None:
            plan.hotel = Hotel(**{k: v for k, v in fallback.items() if k in Hotel.model_fields})


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
    restrictions = state.get("restriction_snapshot") or {"available": True, "rules": []}
    pois = state.get("scenic_pois") or attractions
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
        "scenic_guidance": route_guidance(attractions, req, restrictions),
    }

    user_prompt = json.dumps(ctx, ensure_ascii=False, indent=2)

    raw = await llm.chat(
        system_prompt=COMPILER_SYSTEM_PROMPT + "\nscenic_guidance 中有可用日的景点只允许排在该列表内。",
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
                attrs.append(with_poi_identity(a, pois))
        attrs = [with_poi_identity(attr, pois) for attr in attrs]

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
        hotel = _attach_hotel_offer(dp.get("hotel"), state.get("hotels") or [])

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
    _apply_day_dates(day_plans, str(req.get("travel_time") or ""))
    _fill_missing_hotels(day_plans, state.get("hotels") or [])
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
        overall_tips=_with_catalog_note(data.get("overall_tips", ""), state),
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

    restrictions = state.get("restriction_snapshot") or {"available": True, "rules": []}
    _, findings = assess(itinerary, req, restrictions)
    violations = [
        item.reason if not item.attraction else f"第{item.day}天 {item.attraction}：{item.reason}"
        for item in findings if item.result == "violation"
    ]
    needs_replan = bool(violations) and replan_count == 0
    return {
        "constraint_violations": violations,
        "needs_replan": needs_replan,
        "replan_count": replan_count + 1 if needs_replan else replan_count,
        "itinerary": annotate(itinerary, findings),
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



