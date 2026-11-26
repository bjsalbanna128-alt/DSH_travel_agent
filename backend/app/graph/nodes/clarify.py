"""Extract the latest explicit answers. Application rules decide when to plan."""

import json
import math
import re

from app.core.exceptions import ParseError
from app.providers.llm.deepseek import DeepSeekProvider, safe_json_parse
from app.schemas.ai_dialog import INITIAL_DIALOG
from app.services.ai_dialog import DialogError, reply, run_dialog
from app.services.planning_quality import dates_in_text, explicit_departure

TEXT_FIELDS = ("destination", "departure_city", "travel_time")
LIST_FIELDS = ("preferences", "special_requirements")
PACE_TERMS = {
    "轻松": "relaxed", "悠闲": "relaxed", "慢一点": "relaxed", "适中": "moderate", "正常": "moderate",
    "紧凑": "intensive", "紧张": "intensive", "快一点": "intensive", "relaxed": "relaxed",
    "moderate": "moderate", "intensive": "intensive",
}
CN_DIGITS = dict(zip("零一二三四五六七八九", range(10))) | {"两": 2, "〇": 0}
CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
NUMBER = r"(?:[0-9]+|[零〇一二两三四五六七八九十百千万]+)"
BUDGET_NUMBER = rf"(?:[0-9]+(?:\.[0-9]+)?[万千]?|{NUMBER})"

CLARIFY_SYSTEM_PROMPT = """从用户最新一句话提取明确提供或更正的旅行需求。
上文和当前已答只用于解释本轮短答或更正。不得复述已有字段、猜测答案或填默认值。
只返回 JSON 对象 {"changes": {...}}。无新信息时 changes 为空对象。
可提取字段：destination（目的地）、days（正整数天数）、budget_total（非负人民币金额，明确不限为0）、
pace（relaxed / moderate / intensive）、adults、children、elderly、preferences、
special_requirements、departure_city、travel_time。明确取消某项偏好或要求时允许空数组。
出发日请保留用户日期的明确程度：只在用户给了年月日时使用 YYYY-MM-DD。
不要把未提供年份的日期或模糊时段变成某个具体出发日。"""


def _number(value):
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    if type(value) is int:
        return value
    if not isinstance(value, str) or not re.fullmatch(NUMBER, value):
        return None
    section, total, digit = 0, 0, 0
    for char in value:
        if char in CN_DIGITS:
            digit = CN_DIGITS[char]
        elif char == "万":
            total += (section + digit or 1) * 10000
            section = digit = 0
        else:
            section += (digit or 1) * CN_UNITS[char]
            digit = 0
    return total + section + digit


def _clean_values(values):
    result = {}
    for key in TEXT_FIELDS:
        value = values.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()[:240]
    for key in LIST_FIELDS:
        value = values.get(key)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            result[key] = [item.strip()[:240] for item in value[:20] if item.strip()]
    for key in ("days", "budget_total", "adults", "children", "elderly"):
        raw = values.get(key)
        value = raw if key == "budget_total" and type(raw) is float and math.isfinite(raw) else _number(raw)
        if value is not None and value >= (1 if key == "days" else 0):
            result[key] = value
    if isinstance(values.get("pace"), str) and values["pace"] in PACE_TERMS.values():
        result["pace"] = values["pace"]
    return result


def _explicit(query, next_field):
    result = {}
    unlimited = r"不限|无限制|没有限制|无上限"
    budget = re.findall(rf"预算(?:大概|约|为|是|共|合计|控制在|不超过|[：:\s])*({unlimited}|{BUDGET_NUMBER})", query)
    if not budget and (next_field == "budget_total" or re.search(r"总共|总花费|花费|花销|总价", query)):
        budget = re.findall(rf"({BUDGET_NUMBER})\s*(?:元|块钱)(?:左右)?", query)
    if not budget:
        standalone = re.fullmatch(rf"\s*({unlimited}|{BUDGET_NUMBER})\s*(?:元|块钱)?\s*(?:左右|以内)?[。！!]?\s*", query)
        if standalone and (next_field == "budget_total" or re.search(r"元|块钱", query)):
            budget = [standalone[1]]
    if budget:
        amount = budget[-1]
        if re.fullmatch(unlimited, amount):
            result["budget_total"] = 0
        elif re.fullmatch(r"[0-9]+(?:\.[0-9]+)?[万千]?", amount):
            unit = CN_UNITS.get(amount[-1], 1)
            number = amount[:-1] if unit != 1 else amount
            if len(number) < 14:
                result["budget_total"] = float(number) * unit
        elif (number := _number(amount)) is not None:
            result["budget_total"] = number
    days = re.search(rf"({NUMBER})\s*(?:天|日游)", query)
    if days and (amount := _number(days[1])) and amount > 0:
        result["days"] = amount
    # 当上一句问的是「玩几天」时，用户可以只回一个数字（"1"、"三天"）。
    if next_field == "days" and "days" not in result:
        bare = re.fullmatch(rf"\s*({NUMBER})\s*(?:天|日)?\s*[。！!]?\s*", query)
        if bare and (amount := _number(bare[1])) and amount > 0:
            result["days"] = amount
    for found in re.finditer("|".join(PACE_TERMS), query, re.IGNORECASE):
        if not re.search(r"(?:不(?:想|要)?|别)(?:太)?$", query[:found.start()]):
            result["pace"] = PACE_TERMS[found[0].lower()]
    return result


def import_legacy(values, history):
    answers = _clean_values(values)
    if answers.get("budget_total") == 0:
        answers.pop("budget_total")
    if answers.get("pace") == "moderate":
        answers.pop("pace")
    next_field = None
    for entry in history:
        if not isinstance(entry, dict) or not isinstance(entry.get("content"), str):
            continue
        if entry.get("role") == "user":
            answers.update(_explicit(entry["content"], next_field))
        else:
            next_field = "budget_total" if "预算" in entry["content"] else None
    return answers


async def extract_answers(query, answers, next_field):
    llm = DeepSeekProvider(model=DeepSeekProvider.CHAT_MODEL)
    raw = await llm.chat(
        system_prompt=CLARIFY_SYSTEM_PROMPT,
        user_prompt=json.dumps({"latest": query, "answered": answers, "previous_question_field": next_field},
                               ensure_ascii=False),
        temperature=0.3,
        json_mode=True,
    )
    data = safe_json_parse(raw, "clarify")
    if not isinstance(data, dict) or not isinstance(data.get("changes"), dict):
        raise ParseError("Invalid clarification extraction")
    changes = _clean_values(data["changes"])
    explicit = _explicit(query, next_field)
    for field in ("budget_total", "pace"):
        changes.pop(field, None)
    for field in ("days", "adults", "children", "elderly"):
        if field in changes and not re.search(NUMBER, query) and not (
            field == "adults" and re.search(r"独自|自己|闺蜜|朋友|同伴|家人|情侣|兄弟", query)
        ):
            changes.pop(field)
    for field in TEXT_FIELDS:
        if field in changes and field != "travel_time":
            value = changes[field]
            alternate = value.removesuffix("市")
            if value not in query and (len(alternate) < 2 or alternate not in query):
                changes.pop(field)
    starts_on = explicit_departure(query)
    if starts_on is not None:
        changes["travel_time"] = starts_on.isoformat()
    elif "travel_time" in changes:
        value = changes["travel_time"]
        if dates_in_text(value) or value not in query:
            changes.pop("travel_time")
    for field in LIST_FIELDS:
        if changes.get(field) == [] and not re.search("取消|不要|没有|随意|不限|无要求|无偏好", query):
            changes.pop(field)
    return changes | explicit


async def clarify_node(user_input, history=None, travel_request=None, *, sessions=None,
                       user_id=None, thread_id=None, expected_turn=None):
    if not isinstance(user_input, str) or not user_input.strip() or len(user_input) > 4000:
        raise DialogError(422, "请输入 1 至 4000 字的旅行需求")
    if history is not None and not isinstance(history, list):
        raise DialogError(422, "对话历史格式无效")
    if travel_request is not None and not isinstance(travel_request, dict):
        raise DialogError(422, "旅行需求格式无效")
    history, travel_request = history or [], travel_request or {}
    if sessions is not None:
        return await run_dialog(sessions, user_id, thread_id, user_input.strip(), history, travel_request,
                                expected_turn, extract_answers, import_legacy)
    turn = 1 + sum(isinstance(item, dict) and item.get("role") == "user" for item in history)
    _, result = await reply(extract_answers, user_input.strip(), INITIAL_DIALOG,
                            import_legacy(travel_request, history), turn)
    return result
