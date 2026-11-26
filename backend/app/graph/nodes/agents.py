"""Specialized agent nodes: attraction, route, hotel, restaurant, transport."""

import json
import logging
from datetime import date, datetime

from app.db.database import async_session
from app.providers.llm.deepseek import DeepSeekProvider, safe_json_parse
from app.schemas.travel_state import AgentExecution, IntercityEstimate
from app.services.geo import haversine_km
from app.services.planning_quality import available_days, route_guidance, with_poi_identity
from app.services.poi_service import (
    search_attractions_hybrid,
    search_hotels_hybrid,
    search_restaurants_hybrid,
)
from app.services.transport_plan import parse_intercity_estimates
from app.services.scenic_restrictions import restriction_snapshot

logger = logging.getLogger(__name__)


def _travel_date(req: dict) -> date | None:
    """Best-effort departure date so stock can be checked against a real day."""
    raw = str(req.get("travel_time") or "").strip()
    candidates = [raw[:10]]
    if len(raw) >= 7:
        candidates.append(f"{raw[:7]}-01")
    for candidate in candidates:
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            continue
    return None


# ═══════════════════════════════════════════════════════════════
# Attraction Agent (Amap POI → LLM curation)
# ═══════════════════════════════════════════════════════════════

ATTRACTION_CURATION_PROMPT = """你是一个景点推荐专家。从真实POI数据中筛选最合适的景点。

## 输出格式
{{
  "attractions": [
    {{
      "id": "高德POI的id",
      "name": "景点名",
      "category": "cultural|natural|entertainment|shopping",
      "description": "1-2句描述（根据景点特点写）",
      "rating": 4.5,
      "visit_duration_hours": 2.5,
      "ticket_price_cny": 60,
      "location": {{"lat": 30.67, "lng": 104.06}},
      "opening_hours": "08:00-17:00",
      "tags": ["拍照", "历史"],
      "suitable_for": ["家庭", "情侣"],
      "recommended_reason": "为什么推荐（结合用户偏好）"
    }}
  ]
}}

## 筛选要求
- 从POI列表中选择 {count} 个最合适的景点
- 类型多样（文化+自然+娱乐混搭），优先高评分
- visit_duration_hours 合理估算（博物馆3h，公园2h，商圈1.5h）
- 根据用户偏好调整推荐理由
- 保留高德POI的真实坐标、评分、票价

只输出JSON。"""


async def attraction_node(state: dict) -> dict:
    """Recommend attractions: Amap POI search → LLM curation."""
    llm = DeepSeekProvider(model=DeepSeekProvider.CHAT_MODEL)
    req = state.get("travel_request", {})

    days = req.get("days", 3)
    destination = req.get("destination", "")
    preferences = req.get("preferences", [])
    target_count = days * 3
    restrictions = state.get("restriction_snapshot") or await restriction_snapshot(destination)

    # Step 1: Content layer (our sellable places) + Amap realtime
    travel_date = _travel_date(req)
    async with async_session() as db:
        pois = await search_attractions_hybrid(
            city=destination,
            preferences=preferences,
            days=days,
            travel_date=travel_date,
            session=db,
        )
    all_pois = pois
    pois = [poi for poi in all_pois if available_days(poi, req, restrictions)]

    if not pois:
        # Fallback: LLM generates attractions from knowledge
        logger.warning(f"No POI results for {destination} (ChromaDB + Amap), falling back to LLM")
        raw = await llm.chat(
            system_prompt=ATTRACTION_CURATION_PROMPT.replace("{count}", str(target_count)),
            user_prompt=f"目的地：{destination}\n天数：{days}\n偏好：{', '.join(preferences)}\n注意：无POI数据，请根据你的知识生成真实景点。",
            temperature=0.5,
            json_mode=True,
            max_tokens=8192,
        )
    else:
        # Step 2: LLM curates from hybrid POI data
        poi_list = json.dumps(pois, ensure_ascii=False, indent=2)
        raw = await llm.chat(
            system_prompt=ATTRACTION_CURATION_PROMPT.replace("{count}", str(target_count)),
            user_prompt=(
                f"目的地：{destination}\n天数：{days}\n偏好：{', '.join(preferences)}\n\n"
                f"POI数据（{len(pois)}条，含ChromaDB语义匹配+高德实时数据）：\n{poi_list[:6000]}"
            ),
            temperature=0.4,
            json_mode=True,
            max_tokens=8192,
        )

    data = safe_json_parse(raw, "attraction")
    selected = [
        with_poi_identity(item, all_pois) for item in data.get("attractions", []) if isinstance(item, dict)
    ]
    attractions = [item for item in selected if available_days(item, req, restrictions)]
    count = len(attractions)

    execution = AgentExecution(
        agent_name="attraction_agent",
        started_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat(),
        input_summary=f"{destination}, {days}天, {preferences}",
        output_summary=f"推荐了{count}个景点（ChromaDB+Amap: {len(pois)}条）",
        llm_calls=1,
        status="done",
    )

    history = list(state.get("agent_history", []))
    history.append(execution.model_dump())

    return {
        "attractions": attractions,
        "agent_history": history,
        "restriction_snapshot": restrictions,
        "scenic_candidates_filtered": len(all_pois) > len(pois) or len(selected) > count,
        "scenic_pois": [
            {key: poi[key] for key in ("source", "id", "name", "city") if key in poi}
            for poi in all_pois
        ],
    }


# ═══════════════════════════════════════════════════════════════
# Route Agent — K-Means clustering + TSP optimization + deepseek-reasoner
# ═══════════════════════════════════════════════════════════════

import math
import random


def _haversine_km(a: dict, b: dict) -> float:
    """Haversine distance in km, shared with transport planning."""
    return haversine_km(a, b)


def _kmeans_cluster(attractions: list[dict], k: int) -> list[list[dict]]:
    """Cluster attractions into k groups by geographic proximity."""
    if k >= len(attractions):
        return [[a] for a in attractions]

    points = [(a["location"]["lat"], a["location"]["lng"]) for a in attractions]

    # Initialize centroids: pick k evenly spaced points
    rng = random.Random(42)
    centroids = [points[i] for i in rng.sample(range(len(points)), k)]

    clusters = [[] for _ in range(k)]
    for _ in range(50):
        # Assign each point to nearest centroid
        clusters = [[] for _ in range(k)]
        for i, p in enumerate(points):
            best_c = min(range(k), key=lambda c:
                (p[0] - centroids[c][0]) ** 2 + (p[1] - centroids[c][1]) ** 2)
            clusters[best_c].append(i)

        # Update centroids
        new_centroids = []
        for c in range(k):
            if clusters[c]:
                avg_lat = sum(points[i][0] for i in clusters[c]) / len(clusters[c])
                avg_lng = sum(points[i][1] for i in clusters[c]) / len(clusters[c])
                new_centroids.append((avg_lat, avg_lng))
            else:
                new_centroids.append(centroids[c])

        if new_centroids == centroids:
            break
        centroids = new_centroids

    return [[attractions[i] for i in cluster] for cluster in clusters if cluster]


def _nearest_neighbor_tsp(cluster: list[dict]) -> tuple[list[dict], float]:
    """Nearest Neighbor heuristic for TSP within a day. Returns (ordered_cluster, total_km)."""
    if len(cluster) <= 1:
        return list(cluster), 0.0

    remaining = list(cluster)
    ordered = [remaining.pop(0)]
    total = 0.0

    while remaining:
        last = ordered[-1]
        nearest_idx = min(range(len(remaining)),
                          key=lambda i: _haversine_km(last, remaining[i]))
        nearest = remaining.pop(nearest_idx)
        total += _haversine_km(last, nearest)
        ordered.append(nearest)

    return ordered, total


def _two_opt(ordered: list[dict], max_iter: int = 100) -> tuple[list[dict], float]:
    """2-opt local search improvement. Returns (improved_order, total_km)."""
    if len(ordered) <= 2:
        return list(ordered), _route_distance(ordered)

    improved = True
    best = list(ordered)
    n = len(best)

    for _ in range(max_iter):
        if not improved:
            break
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                if j - i == 1:
                    continue
                new_order = best[:i] + best[i:j][::-1] + best[j:]
                if _route_distance(new_order) < _route_distance(best) - 0.01:
                    best = new_order
                    improved = True

    return best, _route_distance(best)


def _route_distance(ordered: list[dict]) -> float:
    if len(ordered) <= 1:
        return 0.0
    return sum(_haversine_km(ordered[i], ordered[i + 1])
               for i in range(len(ordered) - 1))


def _estimate_travel(km: float, pace: str) -> tuple[str, int]:
    """Estimate travel mode and minutes from distance."""
    if km < 2:
        return "walking", round(km / 0.08)
    elif km < 15:
        return "metro", int(km / 30 * 60 + 15)
    else:
        return "taxi", int(km / 40 * 60)


ROUTE_REASONER_PROMPT = """你是一个路线规划专家。以下是通过 K-Means 聚类 + TSP 算法生成的初步每日路线。

## 你的任务
审查算法生成的路线，根据实际情况调整：
1. 检查景点开放时间是否和游览时段冲突（如下午4点关门的景点不应排在下午3点之后到）
2. 检查同一天景点类型是否多样（避免同一天全是寺庙或全是公园）
3. 检查每天游览总时长是否超标（含交通）
4. 如果某天景点太多/太少，可以跨天调整

## 节奏约束
- relaxed: 每天 ≤ 6小时（含交通），≤ 2个景点
- moderate: 每天 ≤ 8小时（含交通），≤ 3个景点
- intensive: 每天 ≤ 10小时（含交通），≤ 4个景点

## 输出格式
{
  "routes": [
    {
      "day": 1,
      "attraction_ids": ["<id>", "<id>"],
      "total_distance_km": 8.0,
      "travel_mode": "metro",
      "estimated_travel_time_minutes": 30,
      "notes": "上午去A（8-10点开），下午去B"
    }
  ]
}

只输出JSON，不要其他文字。"""


def _route_key(attraction):
    return attraction.get("id") or attraction.get("name", "")


def _compute_route(day, cluster, pace):
    ordered, _ = _nearest_neighbor_tsp(cluster)
    ordered, total_km = _two_opt(ordered)
    mode, travel_min = _estimate_travel(total_km, pace)
    return {
        "day": day,
        "attraction_ids": [_route_key(item) for item in ordered],
        "total_distance_km": round(total_km, 2),
        "travel_mode": mode,
        "estimated_travel_time_minutes": travel_min,
        "algorithm_total_hours": round(sum(item.get("visit_duration_hours", 2) for item in ordered) + travel_min / 60, 1),
    }


def _enforce_open_days(routes, attractions, guidance, pace):
    if not guidance:
        return routes
    indexed = {_route_key(item): item for item in attractions}
    planned = {route["day"]: dict(route) for route in routes}
    changed_days, displaced = set(), {}
    for day, route in planned.items():
        retained = []
        for attraction_id in route["attraction_ids"]:
            rule = guidance.get(attraction_id)
            if rule and day not in rule["allowed_days"]:
                displaced[attraction_id] = rule["allowed_days"]
                changed_days.add(day)
            else:
                retained.append(attraction_id)
        route["attraction_ids"] = retained
    for attraction_id, allowed_days in displaced.items():
        if not allowed_days or any(attraction_id in route["attraction_ids"] for route in planned.values()):
            continue
        day = min(allowed_days, key=lambda value: (len(planned.get(value, {}).get("attraction_ids", [])), value))
        planned.setdefault(day, {"day": day, "attraction_ids": []})["attraction_ids"].append(attraction_id)
        changed_days.add(day)
    return [
        _compute_route(day, [indexed[key] for key in route["attraction_ids"] if key in indexed], pace)
        if day in changed_days else route
        for day, route in sorted(planned.items())
    ]


async def route_node(state: dict) -> dict:
    """Plan daily routes via K-Means + TSP + deepseek-reasoner refinement.

    Phase 1 (algorithmic):
      1. K-Means cluster attractions by lat/lng → one cluster per day
      2. Nearest Neighbor TSP within each cluster
      3. 2-opt improvement

    Phase 2 (reasoner refinement):
      Feed baseline routes to deepseek-reasoner for soft-constraint adjustment.
    """
    req = state.get("travel_request", {})
    attractions = list(state.get("attractions", []))
    days = req.get("days", 1)
    pace = req.get("pace", "moderate")

    if not attractions:
        return {"routes": [], "agent_history": list(state.get("agent_history", []))}

    # ── Phase 1: K-Means + TSP ─────────────────────────────
    k = min(days, len(attractions))
    clusters = _kmeans_cluster(attractions, k)

    # Split oversized clusters and merge undersized ones
    max_per_day = {"relaxed": 2, "moderate": 3, "intensive": 4}.get(pace, 3)
    balanced = []
    for cluster in clusters:
        if len(cluster) > max_per_day:
            # Split: recursively cluster into ceil(len/max_per_day) sub-clusters
            sub_k = max(2, (len(cluster) + max_per_day - 1) // max_per_day)
            balanced.extend(_kmeans_cluster(cluster, min(sub_k, len(cluster))))
        else:
            balanced.append(cluster)

    clusters = balanced
    clusters.sort(key=lambda c: sum(
        a["location"]["lng"] for a in c) / len(c) if c else 0)

    # Merge excess clusters into nearest ones
    while len(clusters) > days:
        smallest_idx = min(range(len(clusters)), key=lambda i: len(clusters[i]))
        smallest = clusters.pop(smallest_idx)
        for attr in smallest:
            nearest_idx = min(range(len(clusters)), key=lambda i:
                min(_haversine_km(attr, a) for a in clusters[i]) if clusters[i] else float('inf'))
            clusters[nearest_idx].append(attr)

    # NN + 2-opt TSP per cluster, assigned to days
    pace_hours = {"relaxed": 6, "moderate": 8, "intensive": 10}.get(pace, 8)

    guidance = route_guidance(attractions, req, state.get("restriction_snapshot") or {"available": True, "rules": []})
    baseline_routes = _enforce_open_days(
        [_compute_route(day, cluster, pace) for day, cluster in enumerate(clusters, 1)], attractions, guidance, pace,
    )

    logger.info(
        f"Route agent baseline: {len(baseline_routes)} days, "
        f"K-Means clusters: {[len(c) for c in clusters]}"
    )

    # If only 1 day or trivial: skip reasoner, use algorithm output directly
    if days <= 1 and len(attractions) <= 3:
        execution = AgentExecution(
            agent_name="route_agent",
            started_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
            input_summary=f"{len(attractions)}个景点, {days}天 (算法直出)",
            output_summary=f"规划了{len(baseline_routes)}天路线",
            llm_calls=0,
            status="done",
        )
        history = list(state.get("agent_history", []))
        history.append(execution.model_dump())
        return {"routes": baseline_routes, "agent_history": history}

    # ── Phase 2: Reasoner refinement ──────────────────────
    try:
        llm = DeepSeekProvider(model=DeepSeekProvider.REASONER_MODEL)

        attr_info_lines = []
        for a in attractions:
            a_id = a.get("id", a.get("name", ""))
            a_name = a.get("name", "?")
            a_hours = a.get("visit_duration_hours", 2)
            a_cat = a.get("category", "?")
            a_open = a.get("opening_hours", "未知")
            a_loc = a.get("location", {})
            attr_info_lines.append(
                f"- {a_id}: {a_name} (耗时{a_hours}h, 分类:{a_cat}, "
                f"开放:{a_open}, 坐标:({a_loc.get('lat',0):.4f},{a_loc.get('lng',0):.4f}))"
            )

        raw = await llm.chat(
            system_prompt=ROUTE_REASONER_PROMPT,
            user_prompt=(
                f"目的地：{req.get('destination')}，{days}天，节奏：{pace}\n"
                f"约束：每天≤{pace_hours}小时，≤{max_per_day}个景点\n\n"
                f"景点开放日与注意事项：{json.dumps(guidance, ensure_ascii=False)}。仅在允许日安排。\n\n"
                f"景点详情：\n" + "\n".join(attr_info_lines) + "\n\n"
                f"算法生成的基线路线（供参考，可调整）：\n"
                + "\n".join(
                    f"  Day {r['day']}: 距离{r['total_distance_km']}km, "
                    f"交通{r['travel_mode']}({r['estimated_travel_time_minutes']}min), "
                    f"总耗时{r['algorithm_total_hours']}h, "
                    f"景点: {r['attraction_ids']}"
                    for r in baseline_routes
                )
            ),
            temperature=0.2,
            max_tokens=16384,  # Reasoner needs room for reasoning + output
        )

        data = safe_json_parse(raw, "route_reasoner")
        routes = data.get("routes", baseline_routes)
        routes = _enforce_open_days(routes, attractions, guidance, pace)

        llm_calls = 1
        logger.info(f"Route reasoner output: {len(routes)} days")

    except Exception as e:
        logger.warning(f"Route reasoner failed ({e}), using baseline routes")
        routes = baseline_routes
        llm_calls = 0

    execution = AgentExecution(
        agent_name="route_agent",
        started_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat(),
        input_summary=f"{len(attractions)}个景点, {days}天 (K-Means+TSP+Reasoner)",
        output_summary=f"规划了{len(routes)}天路线",
        llm_calls=llm_calls,
        status="done",
    )

    history = list(state.get("agent_history", []))
    history.append(execution.model_dump())

    return {
        "routes": routes,
        "agent_history": history,
    }


# ═══════════════════════════════════════════════════════════════
# Hotel Agent
# ═══════════════════════════════════════════════════════════════

HOTEL_CURATION_PROMPT = """你是一个酒店推荐专家。从真实POI数据中筛选最合适的酒店。

## 约束
- 酒店每晚价格 ≤ 日预算的40%
- 优先选择评分高、位置便利的
- 考虑用户特殊需求

## 输出格式
{{
  "hotels": [
    {{
      "id": "高德POI的id",
      "name": "酒店名",
      "area": "区域",
      "price_per_night_cny": 400,
      "rating": 4.5,
      "location": {{"lat": 30.67, "lng": 104.06}},
      "amenities": ["WiFi", "停车场"],
      "description": "简要描述",
      "booking_url": ""
    }}
  ]
}}

推荐 1-2 家酒店。只输出JSON。"""


async def hotel_node(state: dict) -> dict:
    """Recommend hotels: Amap POI → LLM curation."""
    llm = DeepSeekProvider(model=DeepSeekProvider.CHAT_MODEL)
    req = state.get("travel_request", {})
    destination = req.get("destination", "")

    per_day_budget = req.get("budget", {}).get("per_day_cny", 0)
    hotel_budget = per_day_budget * 0.4 if per_day_budget > 0 else 500

    # Fetch hotels from content layer + Amap, nearest to the first planned attraction
    anchor = next(
        (item.get("location") for item in state.get("attractions", []) if item.get("location")), None,
    )
    travel_date = _travel_date(req)
    async with async_session() as db:
        pois = await search_hotels_hybrid(
            city=destination,
            max_price_per_night=hotel_budget if hotel_budget > 0 else 0,
            count=10,
            travel_date=travel_date,
            anchor=anchor,
            session=db,
        )

    if not pois:
        logger.warning(f"No hotel results for {destination} (ChromaDB + Amap), falling back to LLM")
        hotel_list = "无POI数据，请根据你的知识推荐真实酒店。"
    else:
        hotel_list = json.dumps(pois, ensure_ascii=False, indent=2)

    raw = await llm.chat(
        system_prompt=HOTEL_CURATION_PROMPT,
        user_prompt=(
            f"目的地：{destination}\n"
            f"酒店预算上限：{hotel_budget:.0f}元/晚\n"
            f"特殊要求：{', '.join(req.get('special_requirements', []))}\n\n"
            f"高德POI数据（{len(pois)}条）：\n{hotel_list[:5000]}"
        ),
        temperature=0.4,
        json_mode=True,
    )

    data = safe_json_parse(raw, "hotel")

    execution = AgentExecution(
        agent_name="hotel_agent",
        started_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat(),
        output_summary=f"推荐了{len(data.get('hotels', []))}家酒店（ChromaDB+Amap: {len(pois)}条）",
        llm_calls=1,
        status="done",
    )

    history = list(state.get("agent_history", []))
    history.append(execution.model_dump())

    return {
        "hotels": data.get("hotels", []),
        "agent_history": history,
    }


# ═══════════════════════════════════════════════════════════════
# Restaurant Agent
# ═══════════════════════════════════════════════════════════════

RESTAURANT_CURATION_PROMPT = """你是一个美食推荐专家。从真实POI数据中筛选最合适的餐厅。

## 约束
- 优先推荐本地特色菜系
- 人均价格适中，符合预算
- 考虑用户饮食偏好

## 输出格式
{{
  "restaurants": [
    {{
      "id": "高德POI的id",
      "name": "餐厅名",
      "cuisine": "川菜",
      "area": "区域",
      "avg_price_per_person_cny": 80,
      "rating": 4.5,
      "location": {{"lat": 30.67, "lng": 104.06}},
      "must_try_dishes": ["招牌菜1", "招牌菜2"],
      "description": "简要描述（口味、环境等）"
    }}
  ]
}}

推荐 {count} 家餐厅。只输出JSON。"""


async def restaurant_node(state: dict) -> dict:
    """Recommend restaurants: Amap POI → LLM curation."""
    llm = DeepSeekProvider(model=DeepSeekProvider.CHAT_MODEL)
    req = state.get("travel_request", {})
    destination = req.get("destination", "")
    days = req.get("days", 3)
    preferences = req.get("preferences", [])

    # Fetch restaurants from hybrid search (ChromaDB + Amap)
    pois = await search_restaurants_hybrid(
        city=destination,
        preferences=preferences,
        count=15,
    )

    if not pois:
        logger.warning(f"No restaurant results for {destination} (ChromaDB + Amap), falling back to LLM")
        restaurant_list = "无POI数据，请根据你的知识推荐真实餐厅。"
    else:
        restaurant_list = json.dumps(pois, ensure_ascii=False, indent=2)

    target_count = days * 3

    raw = await llm.chat(
        system_prompt=RESTAURANT_CURATION_PROMPT.replace("{count}", str(target_count)),
        user_prompt=(
            f"目的地：{destination}\n天数：{days}\n偏好：{', '.join(preferences)}\n\n"
            f"高德POI数据（{len(pois)}条）：\n{restaurant_list[:6000]}"
        ),
        temperature=0.4,
        json_mode=True,
    )

    data = safe_json_parse(raw, "restaurant")

    execution = AgentExecution(
        agent_name="restaurant_agent",
        started_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat(),
        output_summary=f"推荐了{len(data.get('restaurants', []))}家餐厅（ChromaDB+Amap: {len(pois)}条）",
        llm_calls=1,
        status="done",
    )

    history = list(state.get("agent_history", []))
    history.append(execution.model_dump())

    return {
        "restaurants": data.get("restaurants", []),
        "agent_history": history,
    }


# ═══════════════════════════════════════════════════════════════
# Transport Agent
# ═══════════════════════════════════════════════════════════════

TRANSPORT_SYSTEM_PROMPT = """你是交通规划顾问。只规划城际往返，给出预估区间，不列具体班次。

## 规则
- 每种方向同时给出高铁（train）与航班（flight）两种方式的耗时区间与票价区间
- 两地距离过近、航班明显不适用时可只给高铁，但每种方向至少给出一种方式
- 禁止输出具体发车/到达时刻、车次号、航班号
- 价格与耗时按常见区间给预估，宁可区间宽一些，也不要给出看起来精确的错数
- 用户未提供出发城市时不要编造，返回空的 intercity

## 输出格式
{
  "intercity": [
    {"type": "train", "from_location": "北京", "to_location": "上海",
     "duration_hours_min": 4.5, "duration_hours_max": 5.5,
     "price_cny_min": 553, "price_cny_max": 662},
    {"type": "flight", "from_location": "北京", "to_location": "上海",
     "duration_hours_min": 2.0, "duration_hours_max": 2.5,
     "price_cny_min": 700, "price_cny_max": 1200}
  ]
}

只输出JSON。"""


def _normalize_transport(plan: object) -> dict[str, list]:
    """Return both leg lists, including for trips with no scheduled transport."""
    normalized: dict[str, list] = {"intercity": [], "intraday": []}
    if not isinstance(plan, dict):
        logger.warning("Transport plan is not a JSON object (%s)", type(plan).__name__)
        return normalized

    for key in normalized:
        value = plan.get(key, [])
        if isinstance(value, list):
            normalized[key] = value
        else:
            logger.warning("Transport plan field %s is not a list (%s)", key, type(value).__name__)
    return normalized


async def transport_node(state: dict) -> dict:
    """Estimate intercity transport ranges.

    Intraday legs are not produced here: the compiler builds them from the
    planned attraction order, so they always match what the itinerary shows.
    """
    req = state.get("travel_request", {})
    departure = str(req.get("departure_city") or "").strip()
    destination = str(req.get("destination") or "").strip()

    estimates: list[IntercityEstimate] = []
    llm_calls = 0

    if departure and destination and departure != destination:
        llm = DeepSeekProvider(model=DeepSeekProvider.CHAT_MODEL)
        raw = await llm.chat(
            system_prompt=TRANSPORT_SYSTEM_PROMPT,
            user_prompt=(
                f"出发城市：{departure}\n"
                f"目的地：{destination}\n"
                f"天数：{req.get('days')}"
            ),
            temperature=0.3,
            json_mode=True,
        )
        data = safe_json_parse(raw, "transport")
        candidates = data.get("intercity") if isinstance(data, dict) else None
        estimates = parse_intercity_estimates(candidates)
        llm_calls = 1
        summary = f"给出 {len(estimates)} 条城际预估"
    else:
        summary = "未提供出发城市，跳过城际预估"

    execution = AgentExecution(
        agent_name="transport_agent",
        started_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat(),
        output_summary=summary,
        llm_calls=llm_calls,
        status="done",
    )

    history = list(state.get("agent_history", []))
    history.append(execution.model_dump())

    return {
        "transport": _normalize_transport({
            "intercity": [item.model_dump() for item in estimates],
            "intraday": [],
        }),
        "agent_history": history,
    }
