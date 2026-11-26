"""Push published content into ChromaDB.

Usage:
  python -m scripts.sync_content_vectors            # 增量
  python -m scripts.sync_content_vectors --rebuild  # 全量重建
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import database
from app.services.contents import sync_vectors


async def main(rebuild: bool) -> None:
    async with database.async_session() as db:
        result = await sync_vectors(db, rebuild=rebuild)
    print(f"[ContentVectors] added={result.added} updated={result.updated} removed={result.removed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync content layer into ChromaDB")
    parser.add_argument("--rebuild", action="store_true", help="删除并重建集合")
    args = parser.parse_args()
    asyncio.run(main(args.rebuild))
