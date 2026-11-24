"""Clarification agent — multi-turn dialogue to refine travel requirements."""

import json
import logging

from app.providers.llm.deepseek import DeepSeekProvider, safe_json_parse

logger = logging.getLogger(__name__)

CLARIFY_SYSTEM_PROMPT = """你是一个旅行规划顾问。你的任务是通过追问完善用户的旅行需求。

## 工作流程
用户给了初始需求后，检查以下维度是否明确：

1. **目的地**（最高优先级）：必须知道城市/国家
2. **天数**：玩几天？没说的话要问
3. **同行人**：一个人还是有同伴？和谁一起？
4. **预算**：大概花多少钱？没说的话不追问（可后续估算）
5. **偏好**：喜欢什么类型的？自然风光/文化历史/美食/购物/冒险？
6. **节奏**：轻松悠闲/适中/紧凑打卡？
7. **出发城市**：从哪里出发？（不追问，可选）

## 追问规则
- 每次最多问 1 个问题
- 目的地和天数缺一不可，必须问清楚
- 只要知道目的地+天数，就可以返回 ready。人数、预算、偏好、节奏都有合理默认值
- "和兄弟/和闺蜜"等暗示了人数和偏好，直接推断无需追问
- 用户说预算数字时直接用，不要追问人均还是总计
- 沿用已收集的信息，用户明确更正时才覆盖。仍缺少目的地或天数时继续追问

## 当前已收集的信息
{current_state}

## 对话历史
{history}

## 输出格式
{{
  "action": "ask|ready",
  "message": "给用户的自然语言回复（口语化、友好）",
  "travel_request": {{"destination":"","days":0,"adults":1,"children":0,"elderly":0,"budget_total":0,"preferences":[],"special_requirements":[],"departure_city":"","travel_time":"","pace":"moderate"}},
  "missing_fields": ["destination", "days"],
  "turn": 1
}}

- action=ask 时 message 是追问用户的问题
- action=ready 时 message 是确认信息并告知即将开始规划
- 只输出JSON。"""


async def clarify_node(
    user_input: str,
    history: list[dict] | None = None,
    travel_request: dict | None = None,
) -> dict:
    """Run one clarification turn. Returns ask/ready decision with updated travel_request."""
    llm = DeepSeekProvider(model=DeepSeekProvider.CHAT_MODEL)

    if history is None:
        history = []
    if travel_request is None:
        travel_request = {}

    current = json.dumps(travel_request, ensure_ascii=False, indent=2) if travel_request else "{}"
    hist = json.dumps(history, ensure_ascii=False, indent=2) if history else "[]"
    turn = len([h for h in history if h.get("role") == "user"])

    system = CLARIFY_SYSTEM_PROMPT.replace("{current_state}", current).replace("{history}", hist)

    raw = await llm.chat(
        system_prompt=system,
        user_prompt=f"用户最新输入：{user_input}",
        temperature=0.3,
        json_mode=True,
    )

    data = safe_json_parse(raw, "clarify")

    # Merge travel_request first
    merged = travel_request.copy() if travel_request else {}
    new_req = data.get("travel_request", {})
    for key in ["destination", "adults", "children", "elderly",
                "preferences", "special_requirements", "departure_city",
                "travel_time", "pace"]:
        if new_req.get(key) not in (None, "", 0, []):
            merged[key] = new_req[key]
    if new_req.get("budget_total", 0) > 0:
        merged["budget_total"] = new_req["budget_total"]

    for candidate in (new_req.get("days"), merged.get("days")):
        if isinstance(candidate, (int, str)) and not isinstance(candidate, bool):
            if str(candidate).isascii() and str(candidate).isdecimal() and int(candidate) > 0:
                merged["days"] = int(candidate)
                break
    else:
        merged.pop("days", None)

    missing = [field for field in ("destination", "days") if not merged.get(field)]
    action = "ask" if missing else "ready"
    if missing:
        message = "你想去哪个城市或目的地？" if missing[0] == "destination" else "你计划玩几天？"
    else:
        message = f"好的，已收齐{merged['destination']}{merged['days']}天的旅行需求，可以开始规划。"
    logger.info("Clarify turn=%s action=%s missing=%s", turn + 1, action, missing)

    return {
        "action": action,
        "message": message,
        "travel_request": merged,
        "missing_fields": missing,
        "turn": turn + 1,
    }
