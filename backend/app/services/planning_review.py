"""Persist planning drafts and apply decisions to the version the tourist reviewed."""

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.exceptions import LLMCallError, ParseError
from app.graph.nodes.agents import _estimate_travel, _route_distance
from app.providers.llm.deepseek import DeepSeekProvider, safe_json_parse
from app.schemas.travel_state import Attraction, Hotel, Restaurant, Route, TransportOption
from app.services.fleet_sales import decorate_day_plans
from app.services.itinerary_costs import estimate_day_cost, traveler_count
from app.services.notifications import enqueue_trip_confirmation, wake_delivery
from app.services.planning_quality import annotate, assess, save_report, with_poi_identity
from app.services.scenic_restrictions import restriction_snapshot
from app.services.trip_store import (
    TripRevisionConflict,
    TripThreadConflict,
    apply_draft_decision,
    get_trip,
    get_trip_by_thread,
    save_trip,
)

logger = logging.getLogger(__name__)


class DraftDecision(BaseModel):
    action: Literal["approve", "adjust"]
    version: int = Field(ge=1)
    feedback: str = Field(default="", max_length=2000)


class ReviewError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class DayChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: int = Field(ge=1)
    remove_attractions: list[str] = Field(default_factory=list)
    attractions: list[Attraction] = Field(default_factory=list)
    lunch: Restaurant | None = None
    dinner: Restaurant | None = None
    hotel: Hotel | None = None
    transport: list[TransportOption] = Field(default_factory=list)
    notes: str = ""


class DraftChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: list[DayChange]


REVISION_PROMPT = """根据用户反馈调整当前旅游路书。只输出 JSON。
格式为 {"days":[{"day":3,"remove_attractions":["杜甫草堂"]}]}。
仅列出需要修改的天，且仅提供需要改动的字段。允许字段：
remove_attractions（使用该天已有景点全名）、attractions（替换景点列表）、
lunch、dinner、hotel、transport、notes。保持当前目的地、总天数及未涉及的安排。
仅删除景点时使用 remove_attractions。不要用备注代替实际修改。
需要改目的地、总天数或重新生成整个路书时，返回 {"days":[]}。
"""


def _specified_days(feedback: str) -> set[int]:
    numbers = {name: n for n, name in enumerate("零一二三四五六七八九")}
    numbers["两"] = 2
    days = set()
    for value in re.findall(r"第\s*([0-9]{1,3}|[一二两三四五六七八九十]{1,3})\s*天", feedback):
        if value.isascii():
            days.add(int(value))
        elif "十" in value:
            tens, units = value.split("十", 1)
            if tens in ("", *numbers) and units in ("", *numbers):
                days.add(numbers.get(tens, 1) * 10 + numbers.get(units, 0))
        elif value in numbers:
            days.add(numbers[value])
    return days


async def _revise_itinerary(trip: dict, feedback: str) -> dict:
    itinerary = trip["itinerary"]
    request = trip["travel_request"]
    llm = DeepSeekProvider(model=DeepSeekProvider.CHAT_MODEL)
    try:
        raw = await llm.chat(
            system_prompt=REVISION_PROMPT,
            user_prompt=json.dumps(
                {"反馈": feedback, "原需求": request, "当前路书": itinerary}, ensure_ascii=False
            ),
            temperature=0.2,
            json_mode=True,
        )
    except LLMCallError as exc:
        raise ReviewError(502, "AI 调整服务暂时不可用，请稍后重试") from exc
    try:
        changes = DraftChanges.model_validate(safe_json_parse(raw, "draft_revision")).days
        by_day = {day["day"]: day for day in itinerary["day_plans"]}
        planned_days = {change.day for change in changes}
        if not changes or not planned_days <= by_day.keys() or len(planned_days) != len(changes):
            raise ValueError("Invalid revision days")
        requested_days = _specified_days(feedback)
        if requested_days and not planned_days <= requested_days:
            raise ValueError("Revision changes days outside the request")

        people = traveler_count(request)
        delta = 0.0
        for change in changes:
            current = by_day[change.day]
            revised = _merge_day_change(current, change, request.get("pace", "moderate"))
            delta += estimate_day_cost(revised, people) - estimate_day_cost(current, people)
            by_day[change.day] = revised

        day_plans = list(by_day.values())
        if day_plans == itinerary["day_plans"]:
            raise ValueError("Revision did not change the itinerary")
    except (ParseError, ValueError, KeyError, TypeError) as exc:
        raise ReviewError(422, "未能应用这次调整，请明确要修改的日期和项目。需要全程重排时请新建规划。") from exc

    day_plans = [dict(day) for day in day_plans]
    await decorate_day_plans(day_plans, request, request.get("destination") or itinerary.get("destination", ""))
    return {
        **itinerary,
        "day_plans": day_plans,
        "total_budget_estimate_cny": round(max(0, trip["budget_total"] + delta), 2),
    }


def _merge_day_change(day: dict, change: DayChange, pace: str) -> dict:
    patch = change.model_dump(mode="json", exclude_unset=True, exclude={"day", "remove_attractions"})
    revised = {**day, **patch}
    removals = set(change.remove_attractions)
    before = day.get("attractions") or []
    if removals:
        if "attractions" in patch or not removals <= {a["name"] for a in before}:
            raise ValueError("Invalid attractions to remove")
        revised["attractions"] = [a for a in before if a["name"] not in removals]
    elif "attractions" in patch:
        revised["attractions"] = [with_poi_identity(item, before) for item in revised["attractions"]]
    after = revised.get("attractions") or []
    if after != before:
        removed_names = {a["name"] for a in before} - {a["name"] for a in after}
        revised["transport"] = [
            item for item in revised.get("transport") or []
            if not removed_names.intersection((item.get("from_location"), item.get("to_location")))
        ]
        if after:
            distance = _route_distance(after)
            mode, minutes = _estimate_travel(distance, pace)
            revised["route"] = Route(
                day=change.day,
                attraction_ids=[a["id"] for a in after if a.get("id")],
                total_distance_km=round(distance, 2),
                travel_mode=mode,
                estimated_travel_time_minutes=minutes,
            ).model_dump()
        else:
            revised["route"] = None
    return revised


async def persist_draft(
    sessions, user_id: str, thread_id: str, state: dict, interrupts: tuple
) -> dict:
    approval = interrupts[0].value
    try:
        async with sessions.begin() as db:
            request = state.get("travel_request", {})
            itinerary = state.get("itinerary", state)
            destination = request.get("destination") or itinerary.get("destination", "")
            rules = state.get("restriction_snapshot") or await restriction_snapshot(destination, db)
            status, findings = assess(itinerary, {**request, "destination": destination}, rules)
            try:
                trip = await save_trip(db, thread_id, {**state, "itinerary": annotate(itinerary, findings)},
                                       user_id, status="draft")
            except (TripThreadConflict, IntegrityError) as exc:
                raise ReviewError(409, "该规划会话已有行程，请打开原行程或新建规划") from exc
            await save_report(db, trip.id, trip.version, trip.destination, "initial", status, findings)
            return {
                **approval,
                "data": trip.itinerary,
                "trip_id": trip.id,
                "thread_id": thread_id,
                "version": trip.version,
                "status": trip.status,
            }
    except SQLAlchemyError as exc:
        logger.warning("Could not persist quality report for draft", exc_info=True)
        raise ReviewError(503, "暂时无法保存行程草稿，请重试") from exc


async def review_draft(
    sessions, user_id: str, decision: DraftDecision, *,
    trip_id: str | None = None, thread_id: str | None = None,
) -> tuple[dict, bool]:
    async with sessions() as db:
        if trip_id is not None:
            trip = await get_trip(db, trip_id, user_id=user_id)
        else:
            trip = await get_trip_by_thread(db, thread_id, user_id=user_id)
    if not trip:
        raise ReviewError(404, "行程不存在")
    if trip["version"] != decision.version or (decision.action == "adjust" and trip["status"] != "draft"):
        raise ReviewError(409, "行程版本或状态已变化，请刷新后重试")

    revised = None
    if decision.action == "adjust":
        feedback = decision.feedback.strip()
        if not feedback:
            raise ReviewError(422, "请填写调整意见")
        revised = await _revise_itinerary(trip, feedback)

    event_queued = False
    try:
        async with sessions.begin() as db:
            if revised is not None:
                destination = trip["destination"]
                request = {**trip["travel_request"], "destination": destination}
                rules = await restriction_snapshot(destination, db)
                status, findings = assess(revised, request, rules)
                revised = annotate(revised, findings)
            saved, newly_confirmed = await apply_draft_decision(
                db, trip["id"], user_id, decision.version, revised
            )
            if revised is not None:
                await save_report(db, saved["id"], saved["version"], saved["destination"], "adjusted", status, findings)
            if newly_confirmed:
                event_queued = await enqueue_trip_confirmation(db, user_id, saved)
    except TripRevisionConflict as exc:
        raise ReviewError(409, "行程版本或状态已变化，请刷新后重试") from exc
    except SQLAlchemyError as exc:
        logger.warning("Could not persist trip decision for %s", trip["id"])
        raise ReviewError(503, "暂时无法保存行程处理结果，请稍后重试") from exc

    if event_queued:
        wake_delivery()

    return saved, newly_confirmed


async def remember_confirmed_trip(user_id: str, trip: dict) -> None:
    try:
        from app.services.chroma_store import get_chroma_store
        from app.services.user_profile_store import update_from_trip

        await update_from_trip(
            user_id=user_id, travel_request=trip["travel_request"], itinerary=trip["itinerary"]
        )
        get_chroma_store().add_trip_episode(
            trip_id=trip["id"], user_id=user_id, destination=trip["destination"],
            duration_days=trip["duration_days"], total_budget=trip["budget_total"],
            summary=trip["title"],
        )
    except Exception:
        logger.warning("Failed to update memory after trip confirmation", exc_info=True)
