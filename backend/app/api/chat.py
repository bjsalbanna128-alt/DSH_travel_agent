"""Chat/clarification API — multi-turn dialogue before planning."""

import logging
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUserId
from app.graph.nodes.clarify import clarify_node

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/v1/chat/clarify")
async def clarify(request: Request, _user_id: CurrentUserId):
    """Multi-turn clarification endpoint. Returns ask/ready with updated travel_request."""
    body = await request.json()
    user_input = body.get("query", "")
    history = body.get("history", [])
    travel_request = body.get("travel_request", None)
    thread_id = body.get("thread_id", str(uuid.uuid4()))

    if not user_input:
        return JSONResponse(
            {"error": "query is required"},
            status_code=400,
        )

    result = await clarify_node(
        user_input=user_input,
        history=history,
        travel_request=travel_request,
    )

    result["thread_id"] = thread_id
    return JSONResponse(result)
