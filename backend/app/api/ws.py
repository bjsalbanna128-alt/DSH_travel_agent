"""WebSocket chat endpoint for bidirectional real-time travel planning."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, time as dt_time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ValidationError

from app.api.deps import authenticate_user
from app.db.database import async_session
from app.graph.travel_graph import AGENT_DISPLAY_NAMES, planning_config, travel_graph
from app.graph.nodes.clarify import clarify_node
from app.services.planning_review import (
    DraftDecision, ReviewError, persist_draft, remember_confirmed_trip, review_draft,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dt_time):
        return obj.isoformat()
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    return str(obj)


def _to_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, default=_json_default)


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
        return f"行程: {it.get('title', '')}, {it.get('duration_days', 0)}天"
    return "完成"


@router.websocket("/ws/chat/{thread_id}")
async def websocket_chat(ws: WebSocket, thread_id: str):
    """Bidirectional WebSocket for travel planning chat.

    Client → Server messages:
      {"type": "auth", "token": "..."} (first message)
      {"type": "start", "query": "..."}
         Start a new travel planning graph.
      {"type": "chat", "query": "...", "history": [...], "travel_request": {...}}
         Free-form chat to clarify/pre-fill before planning.
      {"type": "resume", "action": "approve|adjust|reject|partial_edit",
       "feedback": "...", "edits": {...}}
         Resume a paused graph (after approval_required).
      {"type": "cancel"}
         Cancel the current graph execution.

    Server → Client messages:
      {"type": "agent_start", "agent": "...", "display": "...", "progress": 0.0}
      {"type": "agent_done", "agent": "...", "display": "...", "summary": "...",
       "progress": 0.0, "data": {...}}
      {"type": "approval_required", "data": {...}}
      {"type": "clarify", "action": "ask|ready", "message": "...", ...}
      {"type": "done", "thread_id": "...", "trip_id": "..."}
      {"type": "error", "message": "..."}
    """
    await ws.accept()

    try:
        message = await asyncio.wait_for(ws.receive(), timeout=10)
        if message["type"] == "websocket.disconnect":
            return
        auth_message = json.loads(message.get("text") or "")
    except (TimeoutError, ValueError):
        auth_message = None

    token = None
    if isinstance(auth_message, dict) and auth_message.get("type") == "auth":
        token = auth_message.get("token")
    user_id = await authenticate_user(token) if isinstance(token, str) and token else None
    if user_id is None:
        await ws.close(code=1008, reason="请登录后使用旅游服务")
        return

    await ws.send_json({"type": "authenticated"})
    logger.info(f"[WS] Connected: thread_id={thread_id}, user_id={user_id}")

    graph_task: asyncio.Task | None = None
    _cancel_flag = False

    # Use a queue to bridge graph events → WebSocket sends
    event_queue: asyncio.Queue = asyncio.Queue()

    async def send_loop():
        """Continuously send events from the queue to the WebSocket."""
        while True:
            event = await event_queue.get()
            if event is None:  # Sentinel to stop
                break
            try:
                await ws.send_text(_to_json(event))
            except Exception:
                break

    async def run_graph(state, config: dict):
        """Run the graph and push events into the queue. Stops on interrupt or completion."""
        try:
            async for event in travel_graph.astream(state, config):
                if _cancel_flag:
                    break

                for node_name, node_output in event.items():
                    if node_name == "__end__":
                        continue

                    if node_name == "__interrupt__":
                        snapshot = await travel_graph.aget_state(config)
                        draft = await persist_draft(
                            async_session, user_id, thread_id, snapshot.values, node_output
                        )
                        await event_queue.put({"type": "approval_required", "data": draft})
                        return

                    node_key = node_name
                    display = AGENT_DISPLAY_NAMES.get(node_key, node_name)

                    await event_queue.put({
                        "type": "agent_start",
                        "agent": node_key,
                        "display": display,
                        "progress": _estimate_progress(node_key),
                    })

                    await event_queue.put({
                        "type": "agent_done",
                        "agent": node_key,
                        "display": display,
                        "summary": _summarize(node_key, node_output),
                        "progress": _estimate_progress(node_key, done=True),
                        "data": node_output if isinstance(node_output, dict) else {},
                    })

            if not _cancel_flag:
                await event_queue.put({"type": "error", "message": "规划没有生成可确认的行程"})
        except ReviewError as exc:
            await event_queue.put({"type": "error", "message": str(exc)})
        except Exception as e:
            logger.exception(f"[WS] Graph error: {e}")
            await event_queue.put({"type": "error", "message": str(e)[:500]})

    # Start the send loop as a background task
    sender = asyncio.create_task(send_loop())

    config = planning_config(user_id, thread_id)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg: dict = json.loads(raw)
            except json.JSONDecodeError:
                await event_queue.put({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "start":
                # Start new planning
                if graph_task and not graph_task.done():
                    await event_queue.put({"type": "error", "message": "规划正在生成"})
                    continue
                query = msg.get("query", "")
                prefill = msg.get("travel_request", None)

                if not query:
                    await event_queue.put({"type": "error", "message": "query is required"})
                    continue

                # ── Load memory context ──────────────────────
                profile_ctx = ""
                episode_ctx = ""
                similar: list[dict] = []
                try:
                    from app.services.user_profile_store import get_profile_context
                    profile_ctx = await get_profile_context(user_id) or ""
                    if profile_ctx:
                        logger.info(f"[WS] Profile loaded for {user_id}")

                    from app.services.chroma_store import get_chroma_store
                    store = get_chroma_store()
                    similar = store.search_similar_trips(
                        query=query, user_id=user_id, k=2,
                    )
                    if similar:
                        trips_desc = "；".join(
                            f"{t['destination']}{t['duration_days']}天(预算{t['total_budget']:.0f})"
                            for t in similar
                        )
                        episode_ctx = f"历史相似行程: {trips_desc}"
                except Exception as e:
                    logger.warning(f"[WS] Memory loading failed: {e}")

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
                    "user_profile_context": profile_ctx,
                    "episodic_memory_context": episode_ctx,
                    "similar_trips": similar,
                }

                if prefill:
                    initial_state["travel_request"] = prefill
                    initial_state["skip_parse"] = True

                _cancel_flag = False
                graph_task = asyncio.create_task(run_graph(initial_state, config))

            elif msg_type == "chat":
                # Clarification chat
                user_input = msg.get("query", "")
                history = msg.get("history", [])
                travel_request = msg.get("travel_request", None)

                if not user_input:
                    await event_queue.put({"type": "error", "message": "query is required"})
                    continue

                try:
                    result = await clarify_node(
                        user_input=user_input,
                        history=history,
                        travel_request=travel_request,
                    )
                    result["thread_id"] = thread_id
                    await event_queue.put({"type": "clarify", **result})
                except Exception as e:
                    logger.exception(f"[WS] Clarify error: {e}")
                    await event_queue.put({"type": "error", "message": str(e)[:500]})

            elif msg_type == "resume":
                try:
                    decision = DraftDecision.model_validate(msg)
                    trip, newly_confirmed = await review_draft(
                        async_session, user_id, decision, thread_id=thread_id
                    )
                    kind = "done" if trip["status"] == "completed" else "approval_required"
                    await event_queue.put({
                        "type": kind, "trip_id": trip["id"], "thread_id": thread_id,
                        "data": {
                            "trip_id": trip["id"], "version": trip["version"],
                            "status": trip["status"], "data": trip["itinerary"],
                        },
                    })
                    if newly_confirmed:
                        await remember_confirmed_trip(user_id, trip)
                except ValidationError:
                    await event_queue.put({"type": "error", "message": "请指定当前版本和审批操作"})
                except ReviewError as exc:
                    await event_queue.put({"type": "error", "message": str(exc)})

            elif msg_type == "cancel":
                _cancel_flag = True
                if graph_task and not graph_task.done():
                    graph_task.cancel()
                await event_queue.put({"type": "cancelled", "thread_id": thread_id})

            else:
                await event_queue.put({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info(f"[WS] Disconnected: thread_id={thread_id}")
        _cancel_flag = True
        if graph_task and not graph_task.done():
            graph_task.cancel()
    finally:
        await event_queue.put(None)  # Signal sender to stop
        await sender


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
