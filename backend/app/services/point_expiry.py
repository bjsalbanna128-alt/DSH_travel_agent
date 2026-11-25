"""Scan due lots at startup and at Beijing midnight, or via python -m app.services.point_expiry."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime, time, timedelta

from app.db import database
from app.services.member_points import BEIJING, expire_due, utc_now

logger = logging.getLogger(__name__)


async def _run_daily(sessions):
    while True:
        try:
            await expire_due(sessions)
        except Exception:
            logger.error("Points expiry scan failed; retrying in five minutes")
            await asyncio.sleep(300)
        else:
            now = utc_now().astimezone(BEIJING)
            tomorrow = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=BEIJING)
            await asyncio.sleep((tomorrow - now).total_seconds())


@asynccontextmanager
async def point_expiry_worker(sessions):
    task = asyncio.create_task(_run_daily(sessions))
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def _main():
    try:
        await database.init_db()
        print(f"Expired point lots: {await expire_due(database.async_session)}")
    finally:
        await database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
