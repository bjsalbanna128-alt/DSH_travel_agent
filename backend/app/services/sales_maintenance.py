import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from app.db.database import reserve_write
from app.services import contents, orders

logger = logging.getLogger(__name__)


async def maintenance_once(sessions):
    for operation in (orders.expire_due, orders.process_refunds, orders.apply_demo_events, contents.process_vector_job):
        try:
            async with sessions.begin() as db:
                await reserve_write(db)
                await operation(db)
        except Exception:
            logger.warning("销售后台任务将重试 %s", operation.__name__, exc_info=True)


@asynccontextmanager
async def sales_worker(sessions):
    async def loop():
        while True:
            await maintenance_once(sessions)
            await asyncio.sleep(30)

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
