import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import delete

from app.db import database
from app.db.recommendation_models import RecommendationDeliveryMigration
from app.services import recommendation_delivery, recommendations

from test_recommendations import (
    DELIVERY, action, api, auth, create, delivery, engine, feed, fields, ok, picture, upload,
)


def published(api, title, order):
    return ok(action(api, ok(upload(api, create(api, fields(title, order)), picture()))))


def test_upgrade_and_reinitialization(api):
    a = published(api, "晚出发", 20)
    b = published(api, "早出发", 10)
    assert feed(api) == []

    async def simulate_pre_upgrade():
        async with database.async_session.begin() as db:
            await db.execute(delete(RecommendationDeliveryMigration))
        await database.init_db()

    asyncio.run(simulate_pre_upgrade())
    assert [row["id"] for row in feed(api)] == [b["id"], a["id"]]
    ok(delivery(api, b, 1, enabled=False))
    new = published(api, "新发布", 0)
    asyncio.run(database.init_db())
    assert [row["id"] for row in feed(api)] == [a["id"]]
    assert [row["id"] for row in ok(api.get(f"{DELIVERY}/selectable"))] == [new["id"]]
    assert {row["id"]: row["status"] for row in ok(api.get(DELIVERY))} == {a["id"]: "active", b["id"]: "paused"}


def test_window_status_preview_and_conflicts(api, monkeypatch):
    current = datetime(2027, 2, 28, 15, 59, 59, tzinfo=timezone.utc)
    for module in (recommendation_delivery, recommendations):
        monkeypatch.setattr(module, "utc_now", lambda: current)
    assert api.get(DELIVERY, headers={"Authorization": ""}).status_code == 401
    assert api.get(f"{DELIVERY}/preview", headers=auth("guest")).status_code == 403
    draft = create(api, fields())
    assert delivery(api, draft).status_code == 422
    row = published(api, "赏花", 20)
    always = published(api, "四季", 10)
    valid = {"starts_at": "2027-03-01T00:00:00+08:00", "ends_at": "2027-04-01T00:00:00+08:00"}
    assert delivery(api, row, starts_at="2027-03-01T00:00:00").status_code == 422
    assert delivery(api, row, starts_at=valid["ends_at"], ends_at=valid["starts_at"]).status_code == 422
    assert ok(delivery(api, always, ends_at="2027-12-31T00:00:00Z"))["status"] == "active"
    assert ok(delivery(api, row, **valid))["status"] == "scheduled"
    start = datetime.fromisoformat(valid["starts_at"]).astimezone(timezone.utc)
    end = datetime.fromisoformat(valid["ends_at"]).astimezone(timezone.utc)
    assert [card["id"] for card in feed(api)] == [always["id"]]
    for when, include in [(start, True), (end.replace(minute=0, second=0) -
            (start - current), True), (end, False)]:
        current = when
        live = feed(api)
        assert live == ok(api.get(f"{DELIVERY}/preview", params={"at": when.isoformat()}))
        assert (row["id"] in [card["id"] for card in live]) is include
    assert delivery(api, row, 1, **valid).status_code == 422
    assert ok(delivery(api, row, 1, enabled=False, **valid))["status"] == "paused"
    assert ok(action(api, row, "unpublish"))["visibility"] == "unpublished"
    assert ok(api.get(DELIVERY))[1]["status"] == "content_unpublished"

    def write(account):
        return api.put(f"{DELIVERY}/{always['id']}", headers=auth(account),
                       json={"expected_revision": 1, "enabled": False}).status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(write, ("editor-one", "editor-two"))) == [200, 409]
