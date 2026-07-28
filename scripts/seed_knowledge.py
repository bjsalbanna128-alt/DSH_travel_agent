#!/usr/bin/env python3
"""
Seed knowledge base with sample data for 3 cities.
Generates attraction, hotel, and restaurant entries and imports into ChromaDB.

Usage:
  python scripts/seed_knowledge.py --cities chengdu,beijing,sanya
  python scripts/seed_knowledge.py --all --force
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.providers.llm.deepseek import DeepSeekProvider, safe_json_parse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── City seed data ──────────────────────────────────────────────

CITY_ATTRACTIONS = {
    "成都": [
        {"name": "宽窄巷子", "category": "cultural", "rating": 4.5, "duration": 2.5,
         "ticket": 0, "lat": 30.6704, "lng": 104.0552, "tags": ["拍照", "美食"],
         "suitable": ["家庭", "情侣", "朋友"], "hours": "全天"},
        {"name": "大熊猫繁育研究基地", "category": "natural", "rating": 4.8, "duration": 4.0,
         "ticket": 55, "lat": 30.7380, "lng": 104.1465, "tags": ["亲子", "自然"],
         "suitable": ["家庭", "亲子"], "hours": "07:30-18:00"},
        {"name": "武侯祠", "category": "cultural", "rating": 4.6, "duration": 2.0,
         "ticket": 60, "lat": 30.6454, "lng": 104.0450, "tags": ["历史", "三国"],
         "suitable": ["家庭", "情侣", "朋友"], "hours": "08:00-18:00"},
        {"name": "锦里古街", "category": "cultural", "rating": 4.3, "duration": 2.0,
         "ticket": 0, "lat": 30.6435, "lng": 104.0469, "tags": ["美食", "拍照", "夜景"],
         "suitable": ["家庭", "情侣", "朋友"], "hours": "全天"},
        {"name": "杜甫草堂", "category": "cultural", "rating": 4.4, "duration": 2.5,
         "ticket": 60, "lat": 30.6614, "lng": 104.0287, "tags": ["历史", "文学"],
         "suitable": ["家庭", "情侣"], "hours": "08:00-18:30"},
        {"name": "青城山", "category": "natural", "rating": 4.7, "duration": 6.0,
         "ticket": 90, "lat": 30.9035, "lng": 103.5724, "tags": ["自然", "登山", "道教"],
         "suitable": ["朋友", "情侣"], "hours": "08:00-17:00"},
        {"name": "都江堰", "category": "cultural", "rating": 4.7, "duration": 4.0,
         "ticket": 90, "lat": 31.0006, "lng": 103.6140, "tags": ["历史", "水利"],
         "suitable": ["家庭", "朋友"], "hours": "08:00-18:00"},
        {"name": "春熙路", "category": "shopping", "rating": 4.2, "duration": 2.0,
         "ticket": 0, "lat": 30.6543, "lng": 104.0815, "tags": ["购物", "美食"],
         "suitable": ["情侣", "朋友"], "hours": "全天"},
        {"name": "金沙遗址博物馆", "category": "cultural", "rating": 4.5, "duration": 2.5,
         "ticket": 80, "lat": 30.6826, "lng": 104.0130, "tags": ["历史", "考古"],
         "suitable": ["家庭", "朋友"], "hours": "08:00-17:30"},
        {"name": "九眼桥", "category": "entertainment", "rating": 4.1, "duration": 1.5,
         "ticket": 0, "lat": 30.6417, "lng": 104.0885, "tags": ["夜景", "酒吧"],
         "suitable": ["情侣", "朋友"], "hours": "傍晚-深夜"},
    ],
    "北京": [
        {"name": "故宫博物院", "category": "cultural", "rating": 4.9, "duration": 5.0,
         "ticket": 60, "lat": 39.9163, "lng": 116.3972, "tags": ["历史", "世界遗产"],
         "suitable": ["家庭", "情侣", "朋友"], "hours": "08:30-17:00"},
        {"name": "八达岭长城", "category": "cultural", "rating": 4.7, "duration": 5.0,
         "ticket": 40, "lat": 40.3544, "lng": 116.0204, "tags": ["历史", "登山", "世界遗产"],
         "suitable": ["家庭", "朋友"], "hours": "07:30-18:00"},
        {"name": "颐和园", "category": "cultural", "rating": 4.7, "duration": 4.0,
         "ticket": 30, "lat": 39.9999, "lng": 116.2755, "tags": ["园林", "历史"],
         "suitable": ["家庭", "情侣", "朋友"], "hours": "06:30-20:00"},
        {"name": "天坛公园", "category": "cultural", "rating": 4.6, "duration": 2.5,
         "ticket": 15, "lat": 39.8822, "lng": 116.4066, "tags": ["历史", "建筑"],
         "suitable": ["家庭", "朋友"], "hours": "06:00-21:00"},
        {"name": "鸟巢（国家体育场）", "category": "entertainment", "rating": 4.3, "duration": 1.5,
         "ticket": 50, "lat": 39.9928, "lng": 116.3887, "tags": ["建筑", "奥运"],
         "suitable": ["家庭", "朋友"], "hours": "09:00-18:00"},
        {"name": "南锣鼓巷", "category": "cultural", "rating": 4.2, "duration": 2.0,
         "ticket": 0, "lat": 39.9375, "lng": 116.4048, "tags": ["胡同", "美食", "拍照"],
         "suitable": ["情侣", "朋友"], "hours": "全天"},
        {"name": "798艺术区", "category": "cultural", "rating": 4.4, "duration": 3.0,
         "ticket": 0, "lat": 39.9842, "lng": 116.4949, "tags": ["艺术", "拍照"],
         "suitable": ["朋友", "情侣"], "hours": "10:00-18:00"},
        {"name": "王府井大街", "category": "shopping", "rating": 4.1, "duration": 2.0,
         "ticket": 0, "lat": 39.9143, "lng": 116.4109, "tags": ["购物", "美食"],
         "suitable": ["家庭", "朋友"], "hours": "全天"},
        {"name": "什刹海", "category": "natural", "rating": 4.3, "duration": 2.0,
         "ticket": 0, "lat": 39.9370, "lng": 116.3871, "tags": ["湖泊", "胡同"],
         "suitable": ["情侣", "朋友"], "hours": "全天"},
        {"name": "圆明园", "category": "cultural", "rating": 4.5, "duration": 3.0,
         "ticket": 10, "lat": 40.0122, "lng": 116.2990, "tags": ["历史", "园林"],
         "suitable": ["家庭", "情侣"], "hours": "07:00-19:00"},
    ],
    "三亚": [
        {"name": "亚龙湾", "category": "natural", "rating": 4.7, "duration": 4.0,
         "ticket": 0, "lat": 18.2269, "lng": 109.6409, "tags": ["海滩", "游泳"],
         "suitable": ["家庭", "情侣", "朋友"], "hours": "全天"},
        {"name": "天涯海角", "category": "natural", "rating": 4.3, "duration": 3.0,
         "ticket": 81, "lat": 18.2425, "lng": 109.3550, "tags": ["海滩", "拍照"],
         "suitable": ["情侣", "家庭"], "hours": "07:30-18:30"},
        {"name": "蜈支洲岛", "category": "natural", "rating": 4.6, "duration": 6.0,
         "ticket": 144, "lat": 18.1968, "lng": 109.7556, "tags": ["潜水", "海滩"],
         "suitable": ["情侣", "朋友"], "hours": "08:00-17:30"},
        {"name": "南山文化旅游区", "category": "cultural", "rating": 4.5, "duration": 4.0,
         "ticket": 129, "lat": 18.3073, "lng": 109.2097, "tags": ["佛教", "文化"],
         "suitable": ["家庭"], "hours": "08:00-17:30"},
        {"name": "三亚湾", "category": "natural", "rating": 4.2, "duration": 2.0,
         "ticket": 0, "lat": 18.2435, "lng": 109.5027, "tags": ["日落", "海滩"],
         "suitable": ["情侣", "家庭"], "hours": "全天"},
        {"name": "大东海", "category": "natural", "rating": 4.3, "duration": 3.0,
         "ticket": 0, "lat": 18.2242, "lng": 109.5216, "tags": ["游泳", "海滩"],
         "suitable": ["朋友", "家庭"], "hours": "全天"},
        {"name": "呀诺达雨林", "category": "natural", "rating": 4.4, "duration": 5.0,
         "ticket": 168, "lat": 18.4380, "lng": 109.7071, "tags": ["雨林", "冒险"],
         "suitable": ["朋友", "家庭"], "hours": "08:00-17:30"},
        {"name": "鹿回头", "category": "natural", "rating": 4.3, "duration": 2.0,
         "ticket": 42, "lat": 18.2254, "lng": 109.5221, "tags": ["日落", "拍照"],
         "suitable": ["情侣"], "hours": "08:00-22:00"},
        {"name": "海棠湾免税店", "category": "shopping", "rating": 4.1, "duration": 3.0,
         "ticket": 0, "lat": 18.3081, "lng": 109.7355, "tags": ["购物", "免税"],
         "suitable": ["情侣", "朋友"], "hours": "10:00-22:00"},
        {"name": "西岛", "category": "natural", "rating": 4.3, "duration": 5.0,
         "ticket": 98, "lat": 18.2514, "lng": 109.3768, "tags": ["海岛", "水上活动"],
         "suitable": ["朋友", "情侣"], "hours": "08:00-17:30"},
    ],
}


async def generate_descriptions(city: str, attractions: list[dict]) -> list[dict]:
    """Use DeepSeek to generate rich Chinese descriptions for each attraction."""
    llm = DeepSeekProvider()

    names_list = "\n".join(f"{i+1}. {a['name']}" for i, a in enumerate(attractions))
    prompt = f"""为以下{city}的景点各写一句简短的描述（20-40字）：
{names_list}

## 输出格式
{{"descriptions": {{"景点名": "描述", ...}}}}

只输出JSON。"""

    try:
        raw = await llm.chat(
            system_prompt="你是一个旅游文案编辑，用简洁优美的中文描述景点。",
            user_prompt=prompt,
            temperature=0.7,
            json_mode=True,
        )
        data = safe_json_parse(raw, "descriptions")
        desc_map = data.get("descriptions", {})

        for a in attractions:
            a["description"] = desc_map.get(a["name"], f"{city}著名景点")
    except Exception as e:
        logger.warning(f"Failed to generate descriptions for {city}: {e}")
        for a in attractions:
            a["description"] = a.get("description", f"{city}热门景点")

    return attractions


def seed_chromadb(cities: list[str], chroma_path: str = None):
    """Import attractions into ChromaDB."""
    if chroma_path is None:
        chroma_path = str(Path(__file__).parent.parent / "chroma_data")

    client = chromadb.PersistentClient(path=chroma_path)

    # Get or create collections
    try:
        client.delete_collection("attractions")
        client.delete_collection("hotels")
        client.delete_collection("restaurants")
    except Exception:
        pass

    attr_collection = client.create_collection(
        name="attractions",
        metadata={"description": "旅游景点知识库，embedding: bge-large-zh-v1.5"},
    )

    logger.info(f"Seeding {len(cities)} cities into ChromaDB at {chroma_path}")

    total = 0
    for city in cities:
        if city not in CITY_ATTRACTIONS:
            logger.error(f"No seed data for city: {city}")
            continue

        attractions = CITY_ATTRACTIONS[city]

        # Run async description generation
        attractions = asyncio.run(generate_descriptions(city, attractions))

        # Prepare batch
        ids = []
        documents = []
        metadatas = []
        embeddings = None  # Let ChromaDB generate embeddings with default model

        for a in attractions:
            doc_id = f"attr_{city}_{a['name'].replace(' ', '_')}"
            ids.append(doc_id)

            doc_text = (
                f"{a['name']}是{a.get('description', city + '著名景点')}。"
                f"类型：{a['category']}，评分：{a['rating']}/5，"
                f"建议游玩{a['duration']}小时，门票{a['ticket']}元。"
                f"适合：{'、'.join(a.get('suitable', []))}。"
                f"标签：{'、'.join(a.get('tags', []))}。"
            )
            documents.append(doc_text)

            metadatas.append({
                "name": a["name"],
                "city": city,
                "category": a["category"],
                "rating": a["rating"],
                "visit_duration": a["duration"],
                "ticket_price": a["ticket"],
                "lat": a["lat"],
                "lng": a["lng"],
                "opening_hours": a.get("hours", ""),
                "tags": json.dumps(a.get("tags", []), ensure_ascii=False),
                "suitable_for": json.dumps(a.get("suitable", []), ensure_ascii=False),
            })

        attr_collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

        total += len(attractions)
        logger.info(f"  {city}: {len(attractions)} attractions imported")

    logger.info(f"Total: {total} documents seeded across {len(cities)} cities")


def main():
    parser = argparse.ArgumentParser(description="Seed ChromaDB with travel knowledge")
    parser.add_argument("--cities", type=str, default="成都,北京,三亚",
                        help="Comma-separated city names")
    parser.add_argument("--all", action="store_true", help="Seed all available cities")
    parser.add_argument("--force", action="store_true", help="Force delete existing collections")
    parser.add_argument("--chroma-path", type=str, default=None,
                        help="ChromaDB persistence path")
    args = parser.parse_args()

    if args.all:
        cities = list(CITY_ATTRACTIONS.keys())
    else:
        cities = [c.strip() for c in args.cities.split(",")]

    valid_cities = [c for c in cities if c in CITY_ATTRACTIONS]
    if not valid_cities:
        logger.error(f"No valid cities found. Available: {list(CITY_ATTRACTIONS.keys())}")
        sys.exit(1)

    seed_chromadb(valid_cities, args.chroma_path)
    logger.info("Done!")


if __name__ == "__main__":
    main()
