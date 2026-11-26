"""SSE streaming endpoint for real-time agent progress."""

import json
import logging
import uuid
from datetime import datetime, time as dt_time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from app.api.deps import CurrentUserId
from app.db.database import async_session
from app.services.planning_review import (
    DraftDecision, ReviewError, persist_draft, remember_confirmed_trip, review_draft,
)
from pydantic import BaseModel, Field

from app.graph.travel_graph import AGENT_DISPLAY_NAMES, planning_config, travel_graph

logger = logging.getLogger(__name__)
router = APIRouter(tags=["streaming"])


def _json_default(obj):
    """Custom JSON serializer for non-serializable objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dt_time):
        return obj.isoformat()
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    return str(obj)


def _sse(event: str, data: dict) -> str:
    """Format an SSE event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=_json_default)}\n\n"


@router.post("/v1/trips/stream")
async def stream_travel_planning(request: Request, user_id: CurrentUserId):
    """Submit a travel query and stream agent progress via SSE."""
    body = await request.json()
    query = body.get("query", "")
    thread_id = body.get("thread_id", str(uuid.uuid4()))
    prefill_travel_request = body.get("travel_request", None)

    if not isinstance(thread_id, str) or not 1 <= len(thread_id) <= 100:
        raise HTTPException(status_code=422, detail="无效的规划会话标识")

    if not query:
        return StreamingResponse(
            iter([_sse("error", {"message": "query is required"})]),
            media_type="text/event-stream",
        )

    initial_state = {
        "messages": [HumanMessage(content=query)],
        "user_id": user_id,
        "session_id": str(uuid.uuid4()),
        "thread_id": thread_id,
        "current_iteration": 0,
        "max_iterations": 15,
        "agent_history": [],
        "constraint_violations": [],
        "needs_replan": False,
        "replan_count": 0,
        "errors": [],
        "retry_counts": {},
        "fallback_used": {},
        "user_profile_context": "",
        "episodic_memory_context": "",
        "similar_trips": [],
    }

    # Pre-fill travel_request from clarification phase to skip parse_request
    if prefill_travel_request:
        initial_state["travel_request"] = prefill_travel_request
        initial_state["skip_parse"] = True

    async def event_generator():
        config = planning_config(user_id, thread_id)
        last_node = None

        # ── Load memory context ──────────────────────────────────
        try:
            from app.services.user_profile_store import get_profile_context
            profile_ctx = await get_profile_context(user_id)
            if profile_ctx:
                # Inject into initial_state so nodes can use it
                # (LangGraph state merges with initial_state on each node output)
                logger.info(f"[SSE] Loaded profile for {user_id}: {profile_ctx[:100]}")

            from app.services.chroma_store import get_chroma_store
            store = get_chroma_store()
            similar = store.search_similar_trips(
                query=query, user_id=user_id, k=2,
            )
            episode_ctx = ""
            if similar:
                trips_desc = "；".join(
                    f"{t['destination']}{t['duration_days']}天(预算{t['total_budget']:.0f})"
                    for t in similar
                )
                episode_ctx = f"历史相似行程: {trips_desc}"
                logger.info(f"[SSE] Loaded {len(similar)} episodic memories for {user_id}")

            # Inject memory context into initial_state
            if profile_ctx:
                initial_state["user_profile_context"] = profile_ctx
            if episode_ctx:
                initial_state["episodic_memory_context"] = episode_ctx
            if similar:
                initial_state["similar_trips"] = similar

        except Exception as e:
            logger.warning(f"[SSE] Memory loading failed (continuing without): {e}")
            profile_ctx = ""
            episode_ctx = ""
            similar = []

        try:
            async for event in travel_graph.astream(initial_state, config):
                for node_name, node_output in event.items():
                    if node_name == "__end__":
                        continue

                    if node_name == "__interrupt__":
                        snapshot = await travel_graph.aget_state(config)
                        draft = await persist_draft(
                            async_session, user_id, thread_id, snapshot.values, node_output
                        )
                        yield _sse("approval_required", draft)
                        return

                    node_key = node_name
                    display = AGENT_DISPLAY_NAMES.get(node_key, node_name)
                    if node_name != last_node:
                        yield _sse("agent_start", {
                            "agent": node_key,
                            "display": display,
                            "progress": _estimate_progress(node_key),
                        })
                    yield _sse("agent_done", {
                        "agent": node_key,
                        "display": display,
                        "summary": _summarize(node_key, node_output),
                        "progress": _estimate_progress(node_key, done=True),
                        "data": {key: value for key, value in node_output.items()
                                 if key not in ("restriction_snapshot", "scenic_pois")}
                                if isinstance(node_output, dict) else {},
                    })
                    last_node = node_name

            yield _sse("error", {"message": "规划没有生成可确认的行程"})
        except ReviewError as exc:
            yield _sse("error", {"message": str(exc)})

        except Exception as e:
            logger.exception(f"Stream error: {e}")
            yield _sse("error", {"message": str(e)[:500]})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class DraftResume(DraftDecision):
    thread_id: str = Field(min_length=1, max_length=100)


@router.post("/v1/trips/resume")
async def resume_travel_planning(body: DraftResume, user_id: CurrentUserId, background: BackgroundTasks):
    """Accept the reviewed draft decision, even after the graph process restarts."""
    try:
        trip, newly_confirmed = await review_draft(async_session, user_id, body, thread_id=body.thread_id)
    except ReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    event = "done" if trip["status"] == "completed" else "approval_required"
    if newly_confirmed:
        background.add_task(remember_confirmed_trip, user_id, trip)
    return StreamingResponse(
        iter([_sse(event, {
            "trip_id": trip["id"],
            "thread_id": trip["thread_id"],
            "version": trip["version"],
            "status": trip["status"],
            "data": trip["itinerary"],
        })]),
        media_type="text/event-stream",
    )


def _estimate_progress(node_name: str, done: bool = False) -> float:
    weights = {
        "parse_request": 0.05,
        "supervisor": 0.10,
        "attraction_node": 0.25,
        "route_node": 0.40,
        "hotel_node": 0.50,
        "restaurant_node": 0.55,
        "transport_node": 0.65,
        "itinerary_compiler_node": 0.80,
        "constraint_validator_node": 0.90,
        "human_approval_node": 0.95,
    }
    return weights.get(node_name, 0.5)


def _summarize(node_name: str, output: dict) -> str:
    if not isinstance(output, dict):
        return "完成"
    if "attractions" in output:
        return f"推荐了 {len(output['attractions'])} 个景点"
    if "routes" in output:
        return f"规划了 {len(output['routes'])} 天路线"
    if "hotels" in output:
        return f"推荐了 {len(output['hotels'])} 家酒店"
    if "restaurants" in output:
        return f"推荐了 {len(output['restaurants'])} 家餐厅"
    if "transport" in output:
        return "交通方案已规划"
    if "itinerary" in output:
        it = output["itinerary"]
        return f"行程已生成: {it.get('title', '')}, {it.get('duration_days', 0)}天"
    return "完成"
