from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import CurrentOperator, DbSession, WriteDbSession
from app.api.support import no_store
from app.graph.nodes.clarify import extract_answers
from app.schemas.ai_dialog import DialogRevision, SaveDialog, TrialDialog
from app.services.ai_dialog import DialogError, change_dialog, get_dialog, trial_dialog

router = APIRouter(prefix="/ai/dialog-config", tags=["ai-operations"], dependencies=[Depends(no_store)])


@router.get("")
async def read_dialog(db: DbSession):
    return await get_dialog(db)


@router.put("/draft")
async def save_dialog(payload: SaveDialog, account: CurrentOperator, db: WriteDbSession):
    try:
        return await change_dialog(db, account.id, payload)
    except DialogError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.post("/publish")
async def publish_dialog(payload: DialogRevision, account: CurrentOperator, db: WriteDbSession):
    try:
        return await change_dialog(db, account.id, payload, publish=True)
    except DialogError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.post("/trial")
async def simulate_dialog(payload: TrialDialog, account: CurrentOperator, db: DbSession):
    try:
        return await trial_dialog(db, account.id, payload, extract_answers)
    except DialogError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
