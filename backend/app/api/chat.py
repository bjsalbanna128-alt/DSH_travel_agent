"""Chat/clarification API — multi-turn dialogue before planning."""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUserId
from app.db import database
from app.graph.nodes.clarify import clarify_node
from app.services.ai_dialog import DialogError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/v1/chat/clarify")
async def clarify(request: Request, _user_id: CurrentUserId):
    """Multi-turn clarification endpoint. Returns ask/ready with updated travel_request."""
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(422, "请求格式无效")
    user_input = body.get("query", "")
    history = body.get("history", [])
    travel_request = body.get("travel_request", None)
    thread_id = body.get("thread_id") or str(uuid.uuid4())

    if not user_input:
        return JSONResponse(
            {"error": "query is required"},
            status_code=400,
        )

    if not isinstance(thread_id, str):
        raise HTTPException(422, "线程 ID 无效")
    try:
        result = await clarify_node(
            user_input=user_input, history=history, travel_request=travel_request,
            sessions=database.async_session, user_id=_user_id, thread_id=thread_id,
            expected_turn=body.get("turn"),
        )
    except DialogError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return JSONResponse({**result, "thread_id": thread_id})
