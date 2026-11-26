import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError

from app.db import database
from app.db.models import Trip
from app.db.scenic_models import PlanningQualityReport
from app.graph.nodes import agents, compiler, parse_request
from app.services import planning_quality, planning_review, scenic_restrictions

from test_recommendations import api, auth, engine, ok  # noqa: F401

RULES = "/api/v1/admin/ai/scenic-restrictions"
REPORTS = "/api/v1/admin/ai/quality-reports"
POI = {"id": "scenic", "name": "示例景区", "city": "成都市", "source": "amap", "type": "attraction"}
REQUEST = {"destination": "成都", "travel_time": "2027年4月9日", "days": 5, "budget": {"total_cny": 1000}}


def publish(api, row):
    return api.post(f'{RULES}/{row["id"]}/publish', json={"expected_revision": row["revision"]})


def create(api, **changes):
    return api.post(RULES, json={
        "poi": POI, "kind": "closure", "starts_on": "2027-04-10", "ends_on": "2027-04-12",
        "description": "检修暂停开放", "source_note": "公告甲", **changes,
    })


def itinerary(*attractions, day=3, cost=1500, travel=0):
    return {
        "title": "游客私有标题", "destination": "成都", "duration_days": 5, "total_budget_estimate_cny": cost,
        "day_plans": [{"day": day, "date": "2027-04-11", "attractions": list(attractions),
                       "notes": "原路书说明", "route": {"estimated_travel_time_minutes": travel}}],
    }


def snapshot():
    return asyncio.run(scenic_restrictions.restriction_snapshot("成都"))


def test_restriction_lifecycle_matching_and_revision_history(api):
    assert api.get(RULES, headers={"Authorization": ""}).status_code == 401
    assert api.get(REPORTS, headers=auth("guest")).status_code == 403
    assert create(api, poi={**POI, "type": "hotel"}).status_code == 422
    assert create(api, ends_on="2027-04-09").status_code == 422
    row = ok(create(api), 201)
    assert snapshot() == {"available": True, "rules": []}
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: publish(api, row).status_code, range(2))) == [200, 409]
    version = ok(api.get(f'{RULES}/{row["id"]}'))
    assert version["published_version"] == 1 and not version["has_unpublished_changes"]
    assert ok(api.get(RULES, params={"city": "成都", "name": "示例", "kind": "closure",
                                    "visibility": "published"}))["total"] == 1
    other = ok(create(api, kind="reservation", starts_on="2027-04-09", ends_on=None, source_note="公告乙"), 201)
    ok(publish(api, other))
    latest = snapshot()
    assert planning_quality.available_days(POI, REQUEST, latest) == [1, 5]
    for day in (2, 3, 4):
        status, findings = planning_quality.assess(itinerary(POI, day=day), REQUEST, latest)
        assert status == "violation"
        assert [item.rule for item in findings] == ["closure", "reservation"]
        assert findings[0].matched_by == "id"
        assert findings[0].restriction_version == 1
    status, findings = planning_quality.assess(itinerary({"name": POI["name"]}, day=1), REQUEST, latest)
    assert status == "notice" and findings[0].matched_by == "unique_name"
    assert "公告乙" in planning_quality.annotate(itinerary(POI, day=1), findings)["day_plans"][0]["notes"]
    different = {**POI, "city": "洛阳"}
    assert planning_quality.assess(itinerary(different), REQUEST, latest)[0] == "pass"
    unknown = {**REQUEST, "travel_time": "春天"}
    result, findings = planning_quality.assess(itinerary(POI), unknown, latest)
    assert result == "verify" and findings[0].visit_date is None
    conflicting = {**POI, "id": "different"}
    assert planning_quality.assess(itinerary(conflicting), REQUEST, latest)[0] == "verify"
    assert planning_quality.assess(itinerary(POI), REQUEST, {"available": False})[0] == "verify"
    admission = ok(create(api, kind="admission", source_note="北门公告", description="仅北门开放"), 201)
    ok(publish(api, admission))
    _, extra = planning_quality.assess(itinerary(POI), REQUEST, snapshot())
    assert [(item.rule, item.result) for item in extra] == [
        ("closure", "violation"), ("reservation", "notice"), ("admission", "notice"),
    ]

    keys = ("poi", "kind", "starts_on", "ends_on", "description", "source_note")
    edited = {key: version[key] for key in keys}
    edited["source_note"] = "更正后的公告"
    saved = ok(api.put(f'{RULES}/{row["id"]}/draft', json={**edited, "expected_revision": version["revision"]}))
    assert saved["has_unpublished_changes"] and all(rule["source_note"] != edited["source_note"] for rule in snapshot()["rules"])
    updated = ok(publish(api, saved))
    assert updated["published_version"] == 2
    assert api.delete(f'{RULES}/{row["id"]}', params={"expected_revision": updated["revision"]}).status_code == 409
    stopped = ok(api.post(f'{RULES}/{row["id"]}/disable', json={"expected_revision": updated["revision"]}))
    assert stopped["visibility"] == "inactive" and stopped["published_version"] == 2
    assert all(rule["id"] != row["id"] for rule in snapshot()["rules"])


def test_graph_restricts_candidates_and_days_then_detects_compiler_reinsertion(api, monkeypatch):
    blocked = {**POI, "id": "blocked", "name": "长期闭园景区"}
    for response in (create(api), create(api, poi=blocked, starts_on="2027-04-01", ends_on=None)):
        ok(publish(api, ok(response, 201)))
    location = {"lat": 30.62, "lng": 104.06}
    candidates = [{**poi, "location": location} for poi in (POI, blocked)]

    async def search(**kwargs):
        return candidates

    async def respond(self, *, system_prompt, user_prompt, **kwargs):
        if "从真实POI数据" in system_prompt:
            assert "长期闭园景区" not in user_prompt
            return json.dumps({"attractions": candidates})
        if "行程整合专家" in system_prompt:
            assert json.loads(user_prompt)["scenic_guidance"]["scenic"]["allowed_days"] == [1, 5]
            return json.dumps({"day_plans": [{"day": 3, "attractions": [POI["name"]]}]})
        assert "允许日" in user_prompt
        return json.dumps({"routes": [{"day": 3, "attraction_ids": ["scenic"]}]})

    monkeypatch.setattr(agents, "search_attractions_hybrid", search)
    monkeypatch.setattr(agents.DeepSeekProvider, "chat", respond)

    async def run():
        state = {"travel_request": REQUEST}
        state.update(await agents.attraction_node(state))
        assert [item["source"] for item in state["attractions"]] == ["amap"]
        state.update(await agents.route_node(state))
        assert [route["day"] for route in state["routes"] if "scenic" in route["attraction_ids"]] == [1]
        state.update(await compiler.itinerary_compiler_node(state))
        valid = await compiler.constraint_validator_node(state)
        assert valid["needs_replan"] and valid["replan_count"] == 1
        _, findings = planning_quality.assess(state["itinerary"], REQUEST, state["restriction_snapshot"])
        assert findings[0].visit_date.isoformat() == "2027-04-11"
        assert "闭园" in valid["itinerary"]["day_plans"][0]["notes"]
        assert not (await compiler.constraint_validator_node({**state, **valid}))["needs_replan"]
        unknown = await compiler.constraint_validator_node({**state, "travel_request": {**REQUEST, "travel_time": "4月"}})
        assert not unknown["needs_replan"] and "未明确出发日期" in unknown["itinerary"]["day_plans"][0]["notes"]

    asyncio.run(run())


def test_persist_adjust_and_confirm_reports_are_atomic_and_private(api, monkeypatch):
    rule = ok(publish(api, ok(create(api), 201)))
    rules = snapshot()
    state = {"travel_request": {**REQUEST, "private_contact": "私人数据"}, "itinerary": itinerary(POI),
             "restriction_snapshot": rules}
    sessions = database.async_session
    interrupts = (SimpleNamespace(value={"question": "确认行程？"}),)

    def fail_database(*args):
        raise OperationalError("insert", {}, Exception("test fault"))

    async def initial():
        event.listen(PlanningQualityReport, "before_insert", fail_database)
        try:
            with pytest.raises(planning_review.ReviewError) as failure:
                await planning_review.persist_draft(sessions, "guest", "quality", state, interrupts)
            assert failure.value.status_code == 503
        finally:
            event.remove(PlanningQualityReport, "before_insert", fail_database)
        async with sessions() as db:
            assert await db.scalar(select(func.count()).select_from(Trip)) == 0
        return await planning_review.persist_draft(sessions, "guest", "quality", state, interrupts)

    draft = asyncio.run(initial())
    url = f'{REPORTS}/{draft["trip_id"]}'
    before = ok(api.get(f"{url}/1"))
    assert before["status"] == "violation" and before["findings"][0]["source_note"] == "公告甲"
    assert "private_contact" not in str(before) and "游客私有标题" not in str(before)
    assert ok(api.get("/api/v1/admin/trips"))["total"] == 0
    assert ok(api.get(REPORTS, params={"rule": "closure"}))["total"] == 1
    ok(api.post(f'{RULES}/{rule["id"]}/disable', json={"expected_revision": rule["revision"]}))

    async def revise(trip, feedback):
        return itinerary({**POI, "id": "different", "name": "开放景区"})

    monkeypatch.setattr(planning_review, "_revise_itinerary", revise)
    adjust = planning_review.DraftDecision(action="adjust", version=1, feedback="第3天换景点")
    approved = planning_review.DraftDecision(action="approve", version=2)
    saved, confirmed = asyncio.run(planning_review.review_draft(sessions, "guest", adjust, trip_id=draft["trip_id"]))
    assert saved["version"] == 2 and not confirmed
    assert ok(api.get(f"{url}/2"))["status"] == "pass"
    assert ok(api.get(f"{url}/1")) == before
    for result in (True, False):
        assert asyncio.run(planning_review.review_draft(sessions, "guest", approved, trip_id=draft["trip_id"]))[1] is result
    assert ok(api.get(REPORTS))["total"] == 2

    async def old_trip():
        async with sessions.begin() as db:
            row = Trip(thread_id="old-quality", user_id="guest", status="completed", destination="成都", version=1)
            db.add(row)
            await db.flush()
            return row.id

    assert ok(api.get(f"{REPORTS}/{asyncio.run(old_trip())}/1"))["status"] == "unchecked"


def test_thresholds_and_unconfirmed_date(api, monkeypatch):
    no_rules = {"available": True, "rules": []}
    sample = {**POI, "visit_duration_hours": 11}
    assert planning_quality.assess(itinerary(sample, travel=60), REQUEST, no_rules)[0] == "pass"
    assert {item.rule for item in planning_quality.assess(itinerary(sample, cost=1501, travel=61), REQUEST, no_rules)[1]} == {
        "budget", "duration",
    }
    assert planning_quality.assess(itinerary(), REQUEST, no_rules)[1][0].rule == "no_attractions"

    async def parse(self, **kwargs):
        return '{"destination": "成都", "days": 5, "travel_time": "2027-04-09"}'

    monkeypatch.setattr(parse_request.DeepSeekProvider, "chat", parse)
    state = {"user_input": "春天想去成都玩五天"}
    assert asyncio.run(parse_request.parse_request_node(state))["travel_request"]["travel_time"] == ""
    state["user_input"] = "从2027年4月9日至2027年4月13日在成都玩"
    assert asyncio.run(parse_request.parse_request_node(state))["travel_request"]["travel_time"] == "2027-04-09"
    state["user_input"] = "去成都玩几天，2027年4月13日返程"
    assert asyncio.run(parse_request.parse_request_node(state))["travel_request"]["travel_time"] == ""
