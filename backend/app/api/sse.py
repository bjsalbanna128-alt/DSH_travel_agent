"""SSE streaming endpoint for real-time agent progress."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, time as dt_time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from app.db.database import async_session
from app.services.trip_store import save_trip
from app.services.auth_service import decode_access_token
from langgraph.types import Command
from pydantic import BaseModel

from app.graph.travel_graph import travel_graph
from app.graph.travel_graph import AGENT_DISPLAY_NAMES

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
async def stream_travel_planning(request: Request):
    """Submit a travel query and stream agent progress via SSE."""
    body = await request.json()
    query = body.get("query", "")
    thread_id = body.get("thread_id", str(uuid.uuid4()))
    prefill_travel_request = body.get("travel_request", None)

    # Extract user_id from JWT or use body-provided or fallback to anonymous
    user_id = "anonymous"
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        decoded = decode_access_token(token)
        if decoded:
            user_id = decoded
    if user_id == "anonymous":
        user_id = body.get("user_id", "anonymous")

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
        config = {"configurable": {"thread_id": thread_id}}
        last_node = None
        final_state: dict = {}

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

                    # Handle LangGraph interrupt (HITL pause)
                    if node_name == "__interrupt__":
                        interrupt_data = node_output
                        if isinstance(interrupt_data, (dict, list)):
                            yield _sse("approval_required", interrupt_data if isinstance(interrupt_data, dict) else {"data": interrupt_data})
                        continue

                    node_key = node_name
                    display = AGENT_DISPLAY_NAMES.get(node_key, node_name)

                    # Collect state from node outputs
                    if isinstance(node_output, dict):
                        final_state.update(node_output)

                    if node_name != last_node:
                        yield _sse("agent_start", {
                            "agent": node_key,
                            "display": display,
                            "progress": _estimate_progress(node_key),
                        })

                    # Check for approval in node output
                    if isinstance(node_output, dict) and node_output.get("pending_approval"):
                        yield _sse("approval_required", node_output["pending_approval"])

                    yield _sse("agent_done", {
                        "agent": node_key,
                        "display": display,
                        "summary": _summarize(node_key, node_output),
                        "progress": _estimate_progress(node_key, done=True),
                        "data": node_output if isinstance(node_output, dict) else {},
                    })

                    last_node = node_name

            # Capture keys from initial_state that nodes don't return
            if not final_state.get("travel_request"):
                final_state["travel_request"] = initial_state.get("travel_request", {})

            # Save trip to database
            trip_id = None
            itinerary = final_state.get("itinerary") or {}
            if itinerary:
                try:
                    async with async_session() as db:
                        trip = await save_trip(
                            db=db,
                            thread_id=thread_id,
                            trip_data={
                                "itinerary": itinerary,
                                "travel_request": final_state.get("travel_request", {}),
                            },
                            user_id=user_id,
                        )
                        await db.commit()
                        trip_id = trip.id
                        logger.info(f"[SSE] Trip saved: {trip_id}")
                except Exception as e:
                    logger.error(f"[SSE] Failed to save trip: {e}")

            yield _sse("done", {
                "message": "行程规划完成",
                "thread_id": thread_id,
                "trip_id": trip_id,
            })

            # ── Save memory after completion ───────────────────
            try:
                from app.services.user_profile_store import update_from_trip
                travel_req = final_state.get("travel_request", {})
                itinerary_data = final_state.get("itinerary", {})
                await update_from_trip(
                    user_id=user_id,
                    travel_request=travel_req,
                    itinerary=itinerary_data,
                )

                # Save episodic memory
                if itinerary_data and trip_id:
                    from app.services.chroma_store import get_chroma_store
                    store = get_chroma_store()
                    store.add_trip_episode(
                        trip_id=trip_id,
                        user_id=user_id,
                        destination=travel_req.get("destination", ""),
                        duration_days=itinerary_data.get("duration_days", 0),
                        total_budget=itinerary_data.get("total_budget_estimate_cny", 0),
                        summary=itinerary_data.get("title", ""),
                    )
                    logger.info(f"[SSE] Memory saved for {user_id}: profile + episode {trip_id}")
            except Exception as e:
                logger.warning(f"[SSE] Memory save failed (non-critical): {e}")

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


@router.post("/v1/trips/resume")
async def resume_travel_planning(request: Request):
    """Resume a paused graph after user approval/feedback."""
    body = await request.json()
    thread_id = body.get("thread_id", "")
    action = body.get("action", "approve")  # approve | adjust | reject | lower_budget | partial_edit
    feedback = body.get("feedback", "")
    edits = body.get("edits", None)

    if not thread_id:
        return StreamingResponse(
            iter([_sse("error", {"message": "thread_id is required"})]),
            media_type="text/event-stream",
        )

    user_decision: dict[str, Any] = {"action": action, "feedback": feedback}
    if edits:
        user_decision["edits"] = edits

    async def event_generator():
        config = {"configurable": {"thread_id": thread_id}}

        try:
            async for event in travel_graph.astream(Command(resume=user_decision), config):
                for node_name, node_output in event.items():
                    if node_name == "__end__":
                        continue

                    if node_name == "__interrupt__":
                        yield _sse("approval_required", node_output if isinstance(node_output, dict) else {"data": node_output})
                        continue

                    node_key = node_name
                    display = AGENT_DISPLAY_NAMES.get(node_key, node_name)
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
                        "data": node_output if isinstance(node_output, dict) else {},
                    })

            yield _sse("done", {"message": "行程规划完成", "thread_id": thread_id})

        except Exception as e:
            logger.exception(f"Resume stream error: {e}")
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
