"""Parse user natural language input into structured TravelRequest."""

import logging
from datetime import datetime

from app.providers.llm.deepseek import DeepSeekProvider, safe_json_parse
from app.schemas.travel_state import TravelRequest, AgentExecution

logger = logging.getLogger(__name__)

PARSE_SYSTEM_PROMPT = """你是一个旅游需求分析师。从用户输入中提取结构化信息。

## 提取字段
1. destination（必填）：目的地城市或国家
2. days（必填）：出行天数
3. budget_total：总预算（人民币），用户明确说的数字，不要自己编
4. adults：成年人数量
5. children：儿童数（0-12岁）
6. elderly：老人数（60+）
7. preferences：偏好类型（文化历史/自然风光/美食体验/购物休闲/亲子游乐/情侣浪漫/冒险运动）
8. special_requirements：特殊需求（无障碍设施/素食/母婴设施等）
9. departure_city：出发城市
10. travel_time：出行时间或季节
11. pace：旅行节奏（relaxed/moderate/intensive）

## 关键推断规则（按优先级）

### 人数推断
- "和兄弟/和闺蜜/和朋友/和对象/和老婆/和老公/和同学/和同事" → adults≥2（用户+同伴）
- "一个人/独自/一个人去/ solo" → adults=1
- "带爸妈/带父母" → adults=1, elderly=2
- "一家人/全家" → adults=2, children≥1 或 elderly≥2
- "带孩子/带娃" → children≥1
- 完全没提同伴 → adults=1

### 预算推断
- 用户明确说了预算数字 → 直接使用，不要修改
- 用户没提预算 → budget_total=0（由后续Agent根据实际消费估算）
- "穷游/省钱/背包客" → budget_total=天数×200×人数（低预算标志）
- "豪华/奢华/五星" → budget_total=天数×1500×人数（高预算标志）

### 偏好推断
- "和兄弟/和朋友/和同学" → preferences含"美食体验"+"冒险运动"
- "和闺蜜" → preferences含"美食体验"+"购物休闲"
- "和对象/和老婆/和老公" → preferences含"情侣浪漫"
- "带爸妈/带父母/带老人" → pace=relaxed, special_requirements含"无障碍设施"
- 未说偏好 → 默认["文化历史","美食体验"]

### 节奏推断
- 带老人 → relaxed
- 带小孩 → relaxed
- 特种兵/打卡/暴走 → intensive
- 未说 → moderate

## 示例

输入："带爸妈去成都5天，预算2万"
输出：{"destination":"成都","days":5,"budget_total":20000,"adults":1,"children":0,"elderly":2,"preferences":["文化历史","美食体验"],"special_requirements":["无障碍设施"],"departure_city":"","travel_time":"","pace":"relaxed"}

输入："和兄弟去成都玩3天"
输出：{"destination":"成都","days":3,"budget_total":0,"adults":2,"children":0,"elderly":0,"preferences":["美食体验","冒险运动"],"special_requirements":[],"departure_city":"","travel_time":"","pace":"moderate"}

输入："一个人去三亚躺5天"
输出：{"destination":"三亚","days":5,"budget_total":0,"adults":1,"children":0,"elderly":0,"preferences":["自然风光"],"special_requirements":[],"departure_city":"","travel_time":"","pace":"relaxed"}

输入："带娃去上海迪士尼3天，预算1万"
输出：{"destination":"上海","days":3,"budget_total":10000,"adults":1,"children":1,"elderly":0,"preferences":["亲子游乐"],"special_requirements":["母婴设施"],"departure_city":"","travel_time":"","pace":"relaxed"}

只输出JSON。"""


async def parse_request_node(state: dict) -> dict:
    """Parse user input into TravelRequest. Skips if already pre-filled from clarification."""

    # If travel_request was pre-filled from clarification phase, skip parsing
    if state.get("skip_parse") and state.get("travel_request"):
        logger.info("Skipping parse_request — travel_request pre-filled from clarification")
        req_data = state["travel_request"]
        req = TravelRequest(
            destination=req_data.get("destination", ""),
            days=req_data.get("days", 1),
            budget={
                "total_cny": float(req_data.get("budget_total", 0) or 0),
                "per_day_cny": float(req_data.get("budget_total", 0) or 0) / max(req_data.get("days", 1), 1),
            },
            travelers={
                "adults": req_data.get("adults", 1),
                "children": req_data.get("children", 0),
                "elderly": req_data.get("elderly", 0),
            },
            preferences=req_data.get("preferences", ["文化历史"]),
            special_requirements=req_data.get("special_requirements", []),
            departure_city=req_data.get("departure_city", ""),
            travel_time=req_data.get("travel_time", ""),
            pace=req_data.get("pace", "moderate"),
        )
        execution = AgentExecution(
            agent_name="parse_request",
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
            input_summary="预填充的旅行需求",
            output_summary=f"目的地:{req.destination}, {req.days}天 (预填充)",
            llm_calls=0,
            status="done",
        )
        return {
            "travel_request": req.model_dump(),
            "agent_history": [execution.model_dump()],
        }

    llm = DeepSeekProvider(model=DeepSeekProvider.CHAT_MODEL)

    messages = state.get("messages", [])
    user_input = ""
    for m in reversed(messages):
        if hasattr(m, "content") and m.type == "human":
            user_input = str(m.content)
            break
    if not user_input:
        user_input = state.get("user_input", "")

    # Build extended system prompt with user profile context
    extended_prompt = PARSE_SYSTEM_PROMPT
    profile_ctx = state.get("user_profile_context", "")
    if profile_ctx:
        extended_prompt += (
            f"\n\n## 用户画像参考\n"
            f"根据用户历史旅行数据：{profile_ctx}\n"
            f"如果用户在当前输入中没有明确指定某个字段，请用画像中的偏好作为默认值填充。"
        )

    raw = await llm.chat(
        system_prompt=extended_prompt,
        user_prompt=f"用户输入：{user_input}",
        temperature=0.2,
        json_mode=True,
    )

    data = safe_json_parse(raw, "parse_request")

    # Validate required fields
    if not data.get("destination"):
        raise ValueError("无法识别目的地，请重新描述您的旅行计划")

    days = data.get("days", 1)
    budget_total = float(data.get("budget_total", 0) or 0)

    req = TravelRequest(
        destination=data.get("destination", ""),
        days=days,
        budget={
            "total_cny": budget_total,
            "per_day_cny": budget_total / days if budget_total > 0 else 0,
        },
        travelers={
            "adults": data.get("adults", 1),
            "children": data.get("children", 0),
            "elderly": data.get("elderly", 0),
        },
        preferences=data.get("preferences", ["文化历史"]),
        special_requirements=data.get("special_requirements", []),
        departure_city=data.get("departure_city", ""),
        travel_time=data.get("travel_time", ""),
        pace=data.get("pace", "moderate"),
    )

    execution = AgentExecution(
        agent_name="parse_request",
        started_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat(),
        input_summary=user_input[:200],
        output_summary=f"目的地:{req.destination}, {req.days}天, 预算:{req.budget.total_cny}",
        llm_calls=1,
        status="done",
    )

    return {
        "travel_request": req.model_dump(),
        "agent_history": [execution.model_dump()],
    }
