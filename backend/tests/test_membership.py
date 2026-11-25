import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from secrets import token_bytes, token_hex
from unittest.mock import AsyncMock

import pytest
from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.api import deps, routes
from app.config import settings
from app.db import database
from app.db.membership_models import MemberProfile, PointAccount, PointLot, PointTransaction, Traveler
from app.db.models import User, UserProfile
from app.main import app
from app.services.auth_service import create_access_token
from app.services.member_points import (
    BEIJING, OriginalPaymentPending, PointEventConflict, PointEventError,
    expire_due, point_expiry, record_payment, record_refund, utc_now,
)
from app.services.member_privacy import MemberPrivacy
from app.services.members import contact_context, overview
from app.services.trip_store import save_trip

MEMBERS = "/api/v1/members"
ADMIN = "/api/v1/admin/members"
GUEST, OTHER, EDITOR = "member-old", "member-other", "member-operator"
PHONE = "+99900000123"
DOCUMENT = "SYNTHETICZX9012"


def auth(user=GUEST):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json() if response.content else None


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    engine = database.create_db_engine(f"sqlite+aiosqlite:///{tmp_path / 'membership.db'}", poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    for module in (database, deps, routes):
        monkeypatch.setattr(module, "async_session", sessions)
    monkeypatch.setattr(settings, "jwt_secret_key", token_hex(32))
    monkeypatch.setattr(settings, "pii_encryption_key", SecretStr(base64.b64encode(token_bytes(32)).decode()))
    monkeypatch.setattr(routes, "remember_confirmed_trip", AsyncMock())
    yield sessions
    asyncio.run(engine.dispose())


@pytest.fixture
def api(sessions):
    async def initialize():
        await database.init_db()
        async with sessions.begin() as db:
            db.add_all([
                User(id=user, username=user, password_hash="unused", email=f"{user}@example.com", role=role)
                for user, role in [(GUEST, "tourist"), (OTHER, "tourist"), (EDITOR, "operator")]
            ])
            db.add(UserProfile(user_id=GUEST, interest_tags=["徒步"]))

    asyncio.run(initialize())
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


def patch_profile(api, data, account=GUEST):
    return api.patch(f"{MEMBERS}/profile", json=data, headers=auth(account))


def add_traveler(api, name, account=GUEST, **values):
    return api.post(f"{MEMBERS}/travelers", headers=auth(account), json={
        "real_name": name, "relationship": "家人", **values,
    })


def recent(api, **params):
    return checked(api.get(f"{MEMBERS}/point-transactions", params=params, headers=auth()))


def test_roster_includes_existing_and_new_unprofiled_tourists_without_points(api, sessions):
    assert api.get(ADMIN).status_code == 401
    assert api.get(ADMIN, headers=auth()).status_code == 403
    assert api.get(f"{MEMBERS}/points", headers=auth(EDITOR)).status_code == 403
    assert api.get(f"{ADMIN}/{EDITOR}", headers=auth(EDITOR)).status_code == 404
    registered = checked(api.post("/api/v1/auth/register", json={
        "username": "member-new", "email": "synthetic-member@example.com", "password": "test-sample-password",
    }))
    response = api.get(ADMIN, params={"username": "member", "page_size": 1}, headers=auth(EDITOR))
    assert response.headers["cache-control"] == "private, no-store"
    assert checked(response)["total"] == 3
    old, = checked(api.get(ADMIN, params={"username": GUEST}, headers=auth(EDITOR)))["items"]
    assert not old["profile_complete"] and old["effective_balance"] == 0
    detail = checked(api.get(f"{ADMIN}/{GUEST}", headers=auth(EDITOR)))
    assert detail["preferences"]["interest_tags"] == ["徒步"] and detail["profile"]["exists"] is False
    assert api.patch(f"{ADMIN}/{GUEST}", headers=auth(EDITOR), json={"nickname": "代改"}).status_code == 405
    assert api.post(f"{ADMIN}/{GUEST}/point-transactions", headers=auth(EDITOR), json={"delta": 100}).status_code == 405
    assert api.post(f"{MEMBERS}/points", headers=auth(), json={"delta": 100}).status_code == 405
    assert patch_profile(api, {"points": 200}).status_code == 422
    assert checked(patch_profile(api, {"nickname": "旅行者"}))["exists"]

    async def seed_trip():
        async with sessions.begin() as db:
            row = await save_trip(db, "member-trip", {"itinerary": {"title": "测试行程"}}, GUEST, status="draft")
            return row.id

    trip_id = asyncio.run(seed_trip())
    checked(api.post(f"/api/v1/trips/{trip_id}/decision", headers=auth(), json={"action": "approve", "version": 1}))
    assert recent(api)["total"] == 0
    assert checked(api.get(f"{MEMBERS}/points", headers=auth()))["effective_balance"] == 0
    assert checked(api.get(f"{ADMIN}/{registered['user_id']}", headers=auth(EDITOR)))["effective_balance"] == 0


def test_contact_encryption_masks_preservation_and_secret_safe_errors(api, sessions, caplog, capsys):
    values = {"nickname": "公开昵称", "real_name": "李小飞", "phone": PHONE,
              "document_type": "passport", "document_number": DOCUMENT}
    saved = checked(patch_profile(api, values))
    assert saved["real_name"] == values["real_name"] and saved["document_filled"]
    assert saved["phone_mask"].endswith("0123") and saved["document_mask"].endswith("9012")
    staff = checked(api.get(f"{ADMIN}/{GUEST}", headers=auth(EDITOR)))["profile"]
    assert staff["real_name"] == "李**" and staff["nickname"] == "公开昵称"
    for secret in (PHONE, DOCUMENT):
        assert secret not in str(saved) and secret not in str(staff)

    async def ciphertext():
        async with sessions() as db:
            row = await db.get(MemberProfile, GUEST)
            await db.refresh(row, ["document_ciphertext", "phone_ciphertext", "document_digest"])
            return row.document_ciphertext, row.phone_ciphertext, row.document_digest

    first, first_phone, digest = asyncio.run(ciphertext())
    checked(patch_profile(api, {"nickname": "保留原证件"}))
    assert asyncio.run(ciphertext()) == (first, first_phone, digest)
    checked(patch_profile(api, values))
    second, second_phone, same_digest = asyncio.run(ciphertext())
    assert first[1:13] != second[1:13] and first_phone[1:13] != second_phone[1:13] and same_digest == digest
    assert DOCUMENT.encode() not in first and PHONE.encode() not in first_phone
    privacy = MemberPrivacy()
    assert privacy.decrypt(second, context=contact_context(GUEST, "profile", "document")) == DOCUMENT
    assert privacy.decrypt(second_phone, context=contact_context(GUEST, "profile", "phone")) == PHONE
    with pytest.raises(InvalidTag):
        privacy.decrypt(second, context=contact_context(OTHER, "profile", "document"))
    for invalid in (
        {"document_type": "unknown", "document_number": DOCUMENT, "phone": PHONE},
        {"document_number": DOCUMENT},
        {"document_type": "passport", "document_number": saved["document_mask"]},
        {"phone": "INVALID-" + PHONE},
        {PHONE: DOCUMENT},
    ):
        response = patch_profile(api, invalid)
        assert response.status_code == 422 and PHONE not in response.text and DOCUMENT not in response.text
    invalid_json = api.patch(
        f"{MEMBERS}/profile", headers={**auth(), "Content-Type": "application/json"},
        content='{"phone":"' + PHONE + '","document_number":"' + DOCUMENT + '"',
    )
    assert invalid_json.status_code == 422 and PHONE not in invalid_json.text and DOCUMENT not in invalid_json.text
    assert PHONE not in caplog.text + capsys.readouterr().err and DOCUMENT not in caplog.text
    cleared = checked(patch_profile(api, {"clear_document": True, "phone": None}))
    assert not cleared["document_filled"] and cleared["phone_mask"] is None
    assert asyncio.run(ciphertext()) == (None, None, None)


@pytest.mark.parametrize("key", ["", "Ynl0ZXM="])
def test_unavailable_or_short_key_only_blocks_sensitive_new_writes(api, monkeypatch, key):
    checked(patch_profile(api, {"document_type": "passport", "document_number": DOCUMENT}))
    monkeypatch.setattr(settings, "pii_encryption_key", SecretStr(key))
    assert checked(patch_profile(api, {"nickname": "继续编辑"}))["document_filled"]
    assert patch_profile(api, {"phone": PHONE}).status_code == 503
    assert patch_profile(api, {"document_type": "passport", "document_number": DOCUMENT}).status_code == 503
    assert checked(api.get(f"{MEMBERS}/points", headers=auth()))["effective_balance"] == 0
    assert not checked(patch_profile(api, {"clear_document": True}))["document_filled"]


def test_travelers_are_owned_deduplicated_and_have_at_most_one_default(api):
    first = checked(add_traveler(api, "小顾", document_type="passport", document_number=DOCUMENT, phone=PHONE, is_default=True), 201)
    assert first["real_name"] == "小顾" and first["document_filled"] and PHONE not in str(first)
    duplicate = add_traveler(api, "重复", document_type="passport", document_number="ｓｙｎｔｈｅｔｉｃ-ｚｘ 9012")
    assert duplicate.status_code == 409
    checked(add_traveler(api, "不同类型", document_type="other", document_number=DOCUMENT), 201)
    checked(add_traveler(api, "其他家庭", account=OTHER, document_type="passport", document_number=DOCUMENT), 201)
    second = checked(add_traveler(api, "无证件甲", is_default=True), 201)
    third = checked(add_traveler(api, "无证件乙"), 201)
    first_path = f"{MEMBERS}/travelers/{first['id']}"
    for method in ("GET", "PATCH", "DELETE"):
        response = api.request(method, first_path, headers=auth(OTHER), json={} if method == "PATCH" else None)
        assert response.status_code == 404

    def make_default(traveler):
        return api.patch(f"{MEMBERS}/travelers/{traveler['id']}", headers=auth(), json={"is_default": True}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(make_default, [first, third])) == [200, 200]
    rows = checked(api.get(f"{MEMBERS}/travelers", headers=auth()))
    assert sum(row["is_default"] for row in rows) == 1
    staff = checked(api.get(f"{ADMIN}/{GUEST}", headers=auth(EDITOR)))["travelers"]
    assert next(row for row in staff if row["id"] == first["id"])["real_name"] == "**"
    assert checked(api.patch(first_path, json={"clear_document": True}, headers=auth()))["document_filled"] is False
    checked(add_traveler(api, "重新登记", document_type="passport", document_number=DOCUMENT), 201)
    for row in checked(api.get(f"{MEMBERS}/travelers", headers=auth())):
        assert api.delete(f"{MEMBERS}/travelers/{row['id']}", headers=auth()).status_code == 204
    assert checked(api.get(f"{MEMBERS}/travelers", headers=auth())) == []
    assert second["document_mask"] is None


def test_payment_refund_rounding_conflicts_and_idempotent_retry(api, sessions):
    now = utc_now()

    async def pay(order="trip-order", amount=9999, event_id="payment-one", user=GUEST):
        return await record_payment(sessions, order_id=order, member_id=user, amount_fen=amount, paid_at=now, event_id=event_id)

    async def refund(refund_id="refund-one", amount=2000, order="trip-order"):
        return await record_refund(sessions, order_id=order, refund_id=refund_id, amount_fen=amount, refunded_at=now)

    async def scenario():
        with pytest.raises(OriginalPaymentPending):
            await refund()
        original = await pay()
        assert original.delta == 999 and (await pay()).id == original.id
        with pytest.raises(PointEventConflict):
            await pay(amount=10)
        with pytest.raises(PointEventConflict):
            await pay(order="another", user=OTHER)
        with pytest.raises(PointEventConflict):
            await pay(event_id="different-event")
        assert (await pay(order="small-a", event_id="pay-small-a", amount=9)).delta == 0
        assert (await pay(order="small-b", event_id="pay-small-b", amount=5)).delta == 0
        with pytest.raises(PointEventError):
            await pay(order="invalid", event_id="invalid", amount=9.5)
        first = await refund()
        assert first.delta == -200 and (await refund()).id == first.id
        assert (await refund("refund-two", 1)).delta == 0
        with pytest.raises(PointEventConflict):
            await refund("refund-two", 2)
        with pytest.raises(PointEventConflict):
            await refund("refund-one", 2000, "small-a")
        with pytest.raises(PointEventConflict):
            await refund("too-much", 7999)
        assert (await refund("refund-three", 7998)).delta == -799

    asyncio.run(scenario())
    rows = recent(api, order_id="trip-order")["items"]
    assert [row["delta"] for row in rows] == [-799, 0, -200, 999]
    assert rows[0]["book_balance_after"] == 0 and rows[0]["refund_id"] == "refund-three"
    filters = {"order_id": "trip-order", "kind": "refund", "start": now.astimezone(BEIJING).date().isoformat(), "page_size": 2}
    staff = checked(api.get(f"{ADMIN}/{GUEST}/point-transactions", params=filters, headers=auth(EDITOR)))
    assert staff["total"] == 3 and len(staff["items"]) == 2
    assert recent(api)["total"] == 6


def test_expiry_leap_day_late_payment_and_independent_lots(api, sessions):
    now = utc_now()
    leap = datetime(2024, 2, 29, 0, 24, tzinfo=BEIJING)
    assert point_expiry(leap) == datetime(2025, 2, 28, 0, 24, tzinfo=BEIJING)
    old = now - timedelta(days=367)
    near = now - timedelta(days=354)

    async def scenario():
        await record_payment(sessions, order_id="old", member_id=GUEST, amount_fen=3000,
                             paid_at=old, event_id="old-event", now=old)
        await record_payment(sessions, order_id="near", member_id=GUEST, amount_fen=5000,
                             paid_at=near, event_id="near-event", now=now)
        expiry = point_expiry(old).astimezone(timezone.utc)
        async with sessions() as db:
            assert (await overview(db, GUEST, expiry - timedelta(microseconds=1))).effective_balance == 800
            assert (await overview(db, GUEST, expiry)).effective_balance == 500
        counts, refund = await asyncio.gather(
            expire_due(sessions, now=now),
            record_refund(sessions, order_id="old", refund_id="old-refund", amount_fen=1000, refunded_at=now, now=now),
        )
        assert counts in (0, 1) and refund.delta == 0
        assert await expire_due(sessions, now=now) == 0
        await record_payment(sessions, order_id="late", member_id=GUEST, amount_fen=7000,
                             paid_at=old, event_id="late-event", now=now)

    asyncio.run(scenario())
    tour = checked(api.get(f"{MEMBERS}/points", headers=auth()))
    staff = checked(api.get(f"{ADMIN}/{GUEST}", headers=auth(EDITOR)))["points"]
    assert tour["effective_balance"] == staff["effective_balance"] == 500
    assert [row["order_id"] for row in tour["expiring"]] == ["near"]
    assert [row["delta"] for row in recent(api, order_id="old")["items"]] == [0, -300, 300]
    assert [row["delta"] for row in recent(api, order_id="late")["items"]] == [-700, 700]


def test_concurrent_events_and_ledger_rollback(api, sessions):
    now = utc_now()

    async def pay():
        return await record_payment(sessions, order_id="race-order", member_id=GUEST,
                                    amount_fen=9999, paid_at=now, event_id="race-payment")

    async def refund(key, amount):
        return await record_refund(sessions, order_id="race-order", refund_id=key,
                                   amount_fen=amount, refunded_at=now)

    def break_append(_mapper, _connection, row):
        if row.refund_id == "fault":
            raise RuntimeError("simulated interrupted ledger write")

    async def scenario():
        first, repeated = await asyncio.gather(pay(), pay())
        assert first.id == repeated.id
        one, two = await asyncio.gather(refund("one", 2000), refund("two", 3000))
        assert one.delta + two.delta == -500
        event.listen(PointTransaction, "before_insert", break_append)
        try:
            with pytest.raises(RuntimeError, match="interrupted"):
                await refund("fault", 2000)
        finally:
            event.remove(PointTransaction, "before_insert", break_append)
        async with sessions() as db:
            lot = await db.get(PointLot, "race-order")
            account = await db.get(PointAccount, GUEST)
            total = await db.scalar(select(func.sum(PointTransaction.delta)))
            assert lot.refunded_fen == 5000 and lot.remaining_points == account.book_balance == total == 499
        assert (await refund("fault", 2000)).delta == -200

    asyncio.run(scenario())
    assert checked(api.get(f"{MEMBERS}/points", headers=auth()))["effective_balance"] == 299
    assert recent(api)["total"] == 4


def test_repeat_initialization_keeps_membership_and_existing_preferences(api, sessions):
    profile = checked(patch_profile(api, {"nickname": "第一次填写", "real_name": "旧用户"}))
    checked(add_traveler(api, "常用出行人"), 201)
    asyncio.run(database.init_db())
    asyncio.run(database.init_db())
    assert checked(api.get(f"{MEMBERS}/profile", headers=auth())) == profile
    assert checked(api.get(f"{ADMIN}/{GUEST}", headers=auth(EDITOR)))["preferences"]["interest_tags"] == ["徒步"]
    assert len(checked(api.get(f"{MEMBERS}/travelers", headers=auth()))) == 1
