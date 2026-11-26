import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.config import settings
from app.core.exceptions import AgentError
from app.db.ai_dialog_models import DialogDraft, DialogSession, DialogTurn, DialogVersion
from app.db.database import reserve_write
from app.schemas.ai_dialog import INITIAL_DIALOG, DialogConfig


class DialogError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _insert(db, model):
    return (sqlite_insert if db.dialect.name == "sqlite" else pg_insert)(model)


async def seed_dialog(db):
    now = datetime.now(timezone.utc)
    config = INITIAL_DIALOG.model_dump()
    await db.execute(_insert(db, DialogVersion).values(
        version=1, revision=1, config=config, published_at=now,
    ).on_conflict_do_nothing())
    await db.execute(_insert(db, DialogDraft).values(
        id=1, revision=1, current_version=1, config=config, updated_at=now,
    ).on_conflict_do_nothing())


async def get_dialog(db):
    draft = await db.get(DialogDraft, 1)
    live = await db.get(DialogVersion, draft.current_version)
    return {
        "config": draft.config, "revision": draft.revision,
        "updated_by": draft.updated_by, "updated_at": draft.updated_at,
        "published_version": live.version, "published_revision": live.revision,
        "published_by": live.published_by, "published_at": live.published_at,
    }


async def change_dialog(db, account_id, payload, *, publish=False):
    draft = await db.scalar(select(DialogDraft).where(DialogDraft.id == 1).with_for_update())
    if draft.revision != payload.expected_revision:
        raise DialogError(409, "草稿已更新，请重新加载")
    now = datetime.now(timezone.utc)
    if publish:
        live = await db.get(DialogVersion, draft.current_version)
        if live.revision == draft.revision:
            raise DialogError(409, "这份草稿已经发布")
        config = DialogConfig.model_validate(draft.config).model_dump()
        draft.current_version += 1
        db.add(DialogVersion(
            version=draft.current_version, revision=draft.revision, config=config,
            published_by=account_id, published_at=now,
        ))
    else:
        draft.config = payload.config.model_dump()
        draft.revision += 1
        draft.updated_by = account_id
        draft.updated_at = now
    await db.flush()
    return await get_dialog(db)


async def reply(extract, query, config, answers, turn):
    missing = [field for field in config.order if field in config.required and field not in answers]
    try:
        changes = await extract(query, answers, missing[0] if missing else None)
    except AgentError as exc:
        raise DialogError(503, "暂时无法识别旅行需求，请重试") from exc
    answers = {**answers, **changes}
    missing = [field for field in config.order if field in config.required and field not in answers]
    request = answers.copy()
    if missing:
        message = config.questions[missing[0]]
    else:
        message = f"好的，已收齐{answers['destination']}{answers['days']}天的旅行需求，可以开始规划。"
        for field, default in (("budget_total", config.default_budget), ("pace", config.default_pace)):
            if default is not None:
                request.setdefault(field, default)
    if turn == 1 and config.introduction:
        message = f"{config.introduction}\n{message}"
    return answers, {
        "action": "ask" if missing else "ready", "message": message,
        "travel_request": request, "missing_fields": missing, "turn": turn,
    }


def _signature(encoded):
    return hmac.new(settings.jwt_secret_key.encode(), b"dialog-trial:" + encoded, "sha256").hexdigest()


async def trial_dialog(db, operator, payload, extract):
    draft = await db.get(DialogDraft, 1)
    if draft.revision != payload.expected_revision:
        raise DialogError(409, "草稿已更新，请重新开始试聊")
    answers, turn = {}, 1
    if payload.continuation:
        try:
            encoded, signature = payload.continuation.encode().rsplit(b".", 1)
            if not hmac.compare_digest(signature, _signature(encoded).encode()):
                raise ValueError
            previous = json.loads(base64.urlsafe_b64decode(encoded))
            if previous["operator"] != operator or previous["revision"] != draft.revision:
                raise ValueError
            answers, turn = previous["answers"], previous["turn"] + 1
        except (ValueError, KeyError, UnicodeError) as exc:
            raise DialogError(409, "试聊已失效，请清空后重试") from exc
    answers, response = await reply(extract, payload.query, DialogConfig.model_validate(draft.config), answers, turn)
    encoded = base64.urlsafe_b64encode(json.dumps({
        "operator": operator, "revision": draft.revision, "answers": answers, "turn": turn,
    }).encode())
    return {**response, "collected": answers, "continuation": encoded.decode() + "." + _signature(encoded)}


def _replay(saved, digest):
    if saved is None or saved.query_hash != digest:
        raise DialogError(409, "对话轮次已更新，请重新发送")
    return saved.result


async def run_dialog(sessions, user_id, thread_id, query, history, prior, expected_turn, extract, import_legacy):
    if not thread_id or len(thread_id) > 128:
        raise DialogError(422, "线程 ID 无效")
    if expected_turn is not None and (type(expected_turn) is not int or expected_turn < 1):
        raise DialogError(422, "对话轮次无效")
    prior_turns = sum(isinstance(item, dict) and item.get("role") == "user" for item in history)
    key = (user_id, thread_id)
    digest = hashlib.sha256(query.encode()).hexdigest()
    async with sessions() as db:
        await reserve_write(db)
        session = await db.get(DialogSession, key)
        if session is None:
            live = await db.get(DialogDraft, 1)
            legacy = prior_turns > 0
            await db.execute(_insert(db.get_bind(), DialogSession).values(
                user_id=user_id, thread_id=thread_id, version=1 if legacy else live.current_version,
                turn=prior_turns if legacy else 0, answers=import_legacy(prior, history) if legacy else {},
            ).on_conflict_do_nothing())
            session = await db.get(DialogSession, key)
        if expected_turn is None and not history and session.turn:
            saved = await db.get(DialogTurn, (*key, session.turn))
            if saved is not None and saved.query_hash == digest:
                return saved.result
        turn = expected_turn if expected_turn is not None else (prior_turns + 1 if history else session.turn + 1)
        if turn <= session.turn:
            return _replay(await db.get(DialogTurn, (*key, turn)), digest)
        if turn != session.turn + 1:
            raise DialogError(409, "对话轮次已更新，请重新发送")
        version = await db.get(DialogVersion, session.version)
        config = DialogConfig.model_validate(version.config)
        answers = session.answers
        await db.commit()
    answers, result = await reply(extract, query, config, answers, turn)
    result["thread_id"] = thread_id
    async with sessions() as db:
        await reserve_write(db)
        session = await db.get(DialogSession, key, with_for_update=True)
        if session.turn >= turn:
            return _replay(await db.get(DialogTurn, (*key, turn)), digest)
        session.turn, session.answers = turn, answers
        db.add(DialogTurn(user_id=user_id, thread_id=thread_id, turn=turn, query_hash=digest, result=result))
        await db.commit()
    return result
