import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.api import ai_dialog
from app.core.exceptions import LLMCallError
from app.graph.nodes import clarify
from app.graph.nodes.parse_request import parse_request_node

from test_recommendations import api, auth, engine, ok  # noqa: F401

DIALOG = "/api/v1/admin/ai/dialog-config"
CHAT = "/api/v1/chat/clarify"


def chat(api, thread, query, turn=1, account="guest", **legacy):
    return api.post(CHAT, headers=auth(account), json={
        "thread_id": thread, "query": query, "turn": turn, **legacy,
    })


def mock_model(monkeypatch):
    async def extract(query, answers, next_field):
        if query == "服务失败":
            raise LLMCallError("offline")
        result = clarify._explicit(query, next_field)
        if "成都" in query:
            result["destination"] = "成都"
        return result

    monkeypatch.setattr(clarify, "extract_answers", extract)
    monkeypatch.setattr(ai_dialog, "extract_answers", extract)


def test_save_trial_publish_fallback_and_cross_protocol(api, monkeypatch):
    mock_model(monkeypatch)
    old = ok(chat(api, "old", "成都"))
    assert old["missing_fields"] == ["days"]
    assert api.get(DIALOG, headers={"Authorization": ""}).status_code == 401
    assert api.get(DIALOG, headers=auth("guest")).status_code == 403
    initial = ok(api.get(DIALOG))
    config = initial["config"]
    config["introduction"] = "欢迎规划旅行"
    config["required"].append("budget_total")
    invalid = api.put(f"{DIALOG}/draft", json={"expected_revision": 1, "config": config})
    assert invalid.status_code == 422
    config["default_budget"] = None
    config["default_pace"] = "relaxed"
    saved = ok(api.put(f"{DIALOG}/draft", json={"expected_revision": 1, "config": config}))
    trial = ok(api.post(f"{DIALOG}/trial", json={"expected_revision": saved["revision"], "query": "成都三天"}))
    assert trial["message"] == "欢迎规划旅行\n这次旅行总预算大约是多少元？"
    assert trial["collected"] == {"destination": "成都", "days": 3}
    continuation = {"expected_revision": saved["revision"], "continuation": trial["continuation"]}
    failed = api.post(f"{DIALOG}/trial", json={**continuation, "query": "服务失败"})
    assert failed.status_code == 503
    retried = ok(api.post(f"{DIALOG}/trial", json={**continuation, "query": "预算不限"}))
    assert retried["turn"] == 2 and retried["collected"]["budget_total"] == 0
    assert ok(chat(api, "before", "成都三天"))["action"] == "ready"

    def publish(account):
        return api.post(f"{DIALOG}/publish", headers=auth(account), json={"expected_revision": saved["revision"]}).status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(publish, ("editor-one", "editor-two"))) == [200, 409]
    assert ok(chat(api, "old", "三天", 2))["action"] == "ready"
    legacy = ok(chat(api, "upgraded", "三天", 2, history=[{"role": "user", "content": "成都"}],
                     travel_request={"destination": "成都", "pace": "moderate", "budget_total": 0}))
    assert legacy["action"] == "ready"
    assert ok(chat(api, "now", "成都三天"))["message"] == trial["message"]
    assert chat(api, "now", "服务失败", 2).status_code == 503
    with api.websocket_connect("/ws/chat/now") as socket:
        socket.send_json({"type": "auth", "token": auth("guest")["Authorization"].split()[1]})
        assert socket.receive_json()["type"] == "authenticated"
        socket.send_json({"type": "chat", "query": "两千", "turn": 2})
        result = socket.receive_json()
    assert result["type"] == "clarify"
    assert result["travel_request"] == {"destination": "成都", "days": 3, "budget_total": 2000, "pace": "relaxed"}
    planning = asyncio.run(parse_request_node({"skip_parse": True, "travel_request": result["travel_request"]}))
    assert planning["travel_request"]["budget"]["total_cny"] == 2000
    assert planning["travel_request"]["pace"] == "relaxed"
    assert ok(chat(api, "now", "两千", 2)) == {key: value for key, value in result.items() if key != "type"}
    assert chat(api, "now", "预算不限", 2).status_code == 409
    corrected = ok(chat(api, "now", "预算不限，紧凑", 3))
    assert corrected["travel_request"]["budget_total"] == 0
    assert corrected["travel_request"]["pace"] == "intensive"
    isolated = ok(chat(api, "now", "成都三天，总预算两千", account="editor-one"))
    assert isolated["turn"] == 1 and isolated["action"] == "ready"
