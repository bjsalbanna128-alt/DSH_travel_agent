"""Preview or clear isolated demo points. The default operation is read-only."""

import argparse
import asyncio

from sqlalchemy import delete, func, select

from app.db import database
from app.db.order_models import DemoPointEvent
from app.services.demo_points import overview


async def main(apply: bool = False, sessions=None) -> None:
    if sessions is None:
        sessions = database.async_session
    async with sessions.begin() as db:
        if apply:
            await database.reserve_write(db)
            if db.get_bind().dialect.name == "postgresql":
                from sqlalchemy import text
                await db.execute(text("LOCK TABLE demo_point_events IN SHARE ROW EXCLUSIVE MODE"))
        result = await overview(db)
        count = await db.scalar(select(func.count()).select_from(DemoPointEvent))
        print(f"模拟事件 {count} 条，清理后演示可用余额减少 {result['balance']} 分，正式积分不变。")
        if apply:
            await db.execute(delete(DemoPointEvent))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="预览或清理独立的演示积分账本")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="只预览（默认）")
    mode.add_argument("--apply", action="store_true", help="执行清理")
    asyncio.run(main(parser.parse_args().apply))
