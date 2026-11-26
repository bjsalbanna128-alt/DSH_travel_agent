"""Import Beijing seed data into the content layer (attractions and hotels).

Idempotent: existing (city, name) rows are skipped so operator edits survive.

Usage: python -m scripts.import_seed_contents [--cities 北京]
"""

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db import database
from app.db.content_models import PlaceContent

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEED_KNOWLEDGE = REPO_ROOT / "scripts" / "seed_knowledge.py"
SEED_HOTELS = Path(__file__).resolve().parent / "seed_hotels.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def attraction_rows(city: str) -> list[dict]:
    module = _load(SEED_KNOWLEDGE, "seed_knowledge")
    rows = []
    for item in module.CITY_ATTRACTIONS.get(city, []):
        rows.append({
            "kind": "attraction", "city": city, "name": item["name"],
            "category": item.get("category", ""), "rating": item.get("rating"),
            "visit_duration_hours": item.get("duration"),
            "opening_hours": item.get("hours", ""),
            "ticket_price_hint_cny": item.get("ticket"),
            "lat": item.get("lat"), "lng": item.get("lng"),
            "tags": item.get("tags", []), "suitable_for": item.get("suitable", []),
            "description": item.get("description") or f"{city}热门景点",
            "source": "seed", "status": "published",
        })
    return rows


def hotel_rows(city: str) -> list[dict]:
    module = _load(SEED_HOTELS, "seed_hotels")
    items = getattr(module, "BEIJING_HOTELS", []) if city == "北京" else []
    rows = []
    for item in items:
        location = item.get("location", {})
        rows.append({
            "kind": "hotel", "city": city, "name": item["name"],
            "landmark_hint": item.get("area", ""),
            "rating": item.get("rating"),
            "ticket_price_hint_cny": item.get("price_per_night_cny"),
            "lat": location.get("lat"), "lng": location.get("lng"),
            "tags": item.get("amenities", []),
            "suitable_for": [],
            "description": item.get("description", ""),
            "source": "seed", "status": "published",
        })
    return rows


async def main(cities: list[str]) -> None:
    await database.init_db()
    created = skipped = 0
    async with database.async_session() as db:
        for city in cities:
            for row in attraction_rows(city) + hotel_rows(city):
                exists = await db.scalar(select(PlaceContent.id).where(
                    PlaceContent.city == row["city"], PlaceContent.name == row["name"],
                ))
                if exists:
                    skipped += 1
                    continue
                db.add(PlaceContent(**row))
                created += 1
        await db.commit()
    print(f"[Contents] 新增 {created} 条，跳过 {skipped} 条")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import seed data into the content layer")
    parser.add_argument("--cities", default="北京", help="逗号分隔的城市，默认只导北京")
    args = parser.parse_args()
    asyncio.run(main([city.strip() for city in args.cities.split(",") if city.strip()]))
