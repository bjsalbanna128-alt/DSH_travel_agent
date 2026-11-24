"""Supervisor node — LLM-based dynamic scheduler with rule fallback."""

import json
import logging
from datetime import datetime

from app.schemas.travel_state import AgentExecution

logger = logging.getLogger(__name__)

SUPERVISOR_PROMPT = """你是一个 Multi-Agent 系统的调度器。根据当前旅行规划的状态，决定下一步应该执行哪些 Agent。

## 可用 Agent
- attraction: 推荐景点（需要先执行，是其他 Agent 的基础）
- route: 规划每日路线（依赖 attraction 的结果）
- hotel: 推荐酒店（可以与 restaurant 并行，不依赖 route）
- restaurant: 推荐餐厅（可以与 hotel 并行，不依赖 route）
- transport: 规划交通（依赖 route 结果）
- itinerary_compiler: 整合生成最终行程（所有 Agent 完成后执行）

## 调度规则（按优先级）
1. attraction 必须最先执行（路线、酒店、餐厅都依赖景点信息）
2. route 依赖 attraction，必须在 attraction 之后执行
3. hotel 和 restaurant 只需 attraction 完成，不需要等 route
4. transport 依赖 route，在 route 之后执行
5. 所有 Agent 完成后才执行 itinerary_compiler

## 高效调度策略
- 如果只有 attraction 完成，可以同时建议 hotel 和 restaurant（实际按顺序执行）
- 如果 route 也已完成后，优先执行 transport
- 如果用户是本地游（不需要城际交通）或偏好步行，可以跳过 transport
- 遇到 replan 时，只需重跑 attraction + route

## 输出格式
{"next_agent": "<agent_key>", "reasoning": "<一句话解释为什么选这个>"}

只输出 JSON。"""


def _rule_based_fallback(has_attractions: bool, has_routes: bool, has_hotels: bool,
                         has_restaurants: bool, has_transport: bool) -> str:
    """Deterministic fallback scheduler.

    Order: attraction → route → hotel → restaurant → transport → compiler
    Returns ONE agent name.
    """
    if not has_attractions:
        return "attraction"
    if has_attractions and not has_routes:
        return "route"
    # Hotel and restaurant can run after attractions (don't need route)
    if has_routes and not has_hotels:
        return "hotel"
    if has_routes and has_hotels and not has_restaurants:
        return "restaurant"
    if has_routes and has_hotels and has_restaurants and not has_transport:
        return "transport"
    return "itinerary_compiler"


def _build_state_summary(state: dict) -> str:
    """Build a concise summary of current state for the supervisor LLM."""
    req = state.get("travel_request", {})
    iteration = state.get("current_iteration", 0)
    violations = state.get("constraint_violations", [])
    needs_replan = state.get("needs_replan", False)

    parts = [
        f"当前迭代: {iteration}/15",
        f"目的地: {req.get('destination', '未设定')}",
        f"天数: {req.get('days', '未设定')}",
        f"节奏: {req.get('pace', 'moderate')}",
        f"景点: {'已完成' if state.get('attractions') else '未完成'} ({len(state.get('attractions', []))}个)",
        f"路线: {'已完成' if state.get('routes') else '未完成'}",
        f"酒店: {'已完成' if state.get('hotels') else '未完成'}",
        f"餐厅: {'已完成' if state.get('restaurants') else '未完成'}",
        f"交通: {'已完成' if state.get('transport') else '未完成'}",
    ]

    if needs_replan:
        parts.append(f"约束校验失败: {'; '.join(violations)}")
    return "\n".join(parts)


async def supervisor_node(state: dict) -> dict:
    """LLM-based dynamic scheduler with rule fallback.

    Uses deepseek-chat to analyze the current state and decide which agent
    to run next. Falls back to deterministic rules on any LLM failure.
    """
    iteration = state.get("current_iteration", 0) + 1

    # Safety valve: max iterations
    if iteration > 15:
        logger.warning("Supervisor: hit max iterations (15), forcing compiler")
        return _done(iteration, "itinerary_compiler", "安全阀: 达到最大迭代次数")

    # Replan: reset and re-run from attraction
    if state.get("needs_replan"):
        violations = state.get("constraint_violations", [])
        replan_count = state.get("replan_count", 0)
        logger.info(f"Supervisor: replan #{replan_count} due to {violations}")
        return _done(iteration, "attraction", f"Replan #{replan_count}",
                     extra_state={
                         "needs_replan": False,
                         "constraint_violations": [],
                         "attractions": [],
                         "routes": [],
                     })

    # Check what's done
    has_attractions = bool(state.get("attractions"))
    has_routes = bool(state.get("routes"))
    has_hotels = bool(state.get("hotels"))
    has_restaurants = bool(state.get("restaurants"))
    has_transport = bool(state.get("transport", {}).get("intercity") or
                         state.get("transport", {}).get("intraday"))

    # ── Fast path: rule-based fallback when next step is unambiguous ──
    # Most iterations have exactly one valid next agent. LLM is overkill.
    next_agent: str
    reasoning: str
    llm_calls = 0

    rule_next = _rule_based_fallback(
        has_attractions, has_routes, has_hotels, has_restaurants, has_transport,
    )

    # Only consult LLM when replanning (attraction was already done) or
    # when both hotel+restaurant could run (let LLM pick order).
    use_llm = (
        has_attractions and not has_routes and not has_hotels and not has_restaurants
    )  # After attractions done: hotel/restaurant can run in either order

    if not use_llm:
        next_agent = rule_next
        reasoning = "快速规则路由"
        logger.info(f"Supervisor iteration {iteration}: {next_agent} (rule)")
    else:
        try:
            from app.providers.llm.deepseek import DeepSeekProvider, safe_json_parse

            llm = DeepSeekProvider(model=DeepSeekProvider.CHAT_MODEL)
            state_summary = _build_state_summary(state)

            raw = await llm.chat(
                system_prompt=SUPERVISOR_PROMPT,
                user_prompt=(
                    f"## 当前状态\n{state_summary}\n\n"
                    f"## 任务\n现在需要推荐酒店和餐厅（两者都可以执行），请选择先执行哪个。\n"
                    f"输出 JSON: {{\"next_agent\": \"hotel|restaurant\", \"reasoning\": \"...\"}}"
                ),
                temperature=0.2,
                json_mode=True,
                max_tokens=256,
            )

            data = safe_json_parse(raw, "supervisor")
            next_agent = data.get("next_agent", "")
            reasoning = data.get("reasoning", "LLM 决策")

            valid_agents = {"attraction", "route", "hotel", "restaurant", "transport", "itinerary_compiler"}
            if next_agent not in valid_agents:
                next_agent = rule_next
                reasoning = f"规则回退 (LLM 输出无效)"
            else:
                # Sanity-check hard dependencies
                if next_agent == "route" and not has_attractions:
                    next_agent = "attraction"
                elif next_agent == "transport" and not has_routes:
                    next_agent = "route"
                elif next_agent == "itinerary_compiler" and not has_attractions:
                    next_agent = "attraction"

            llm_calls = 1
            logger.info(f"Supervisor iteration {iteration}: {next_agent} (LLM: {reasoning[:80]})")

        except Exception as e:
            logger.warning(f"Supervisor LLM failed ({e}), using rule-based fallback")
            next_agent = rule_next
            reasoning = f"规则回退 (LLM 异常: {str(e)[:80]})"

    return _done(iteration, next_agent, reasoning, state=state, llm_calls=llm_calls)


def _done(iteration: int, next_agent: str, reasoning: str,
          state: dict | None = None, extra_state: dict | None = None,
          llm_calls: int = 0) -> dict:
    """Build the supervisor return dict with execution tracking."""
    execution = AgentExecution(
        agent_name="supervisor",
        started_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat(),
        input_summary=f"迭代 {iteration}",
        output_summary=reasoning[:200],
        llm_calls=llm_calls,
        status="done",
    )

    history = list(state.get("agent_history", [])) if state else []
    history.append(execution.model_dump())

    result: dict = {
        "current_iteration": iteration,
        "next_agents": [next_agent],
        "agent_history": history,
    }
    if extra_state:
        result.update(extra_state)

    return result
