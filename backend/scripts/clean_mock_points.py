"""Delete mock points created by simulated orders.

Mock payments and refunds use point event keys prefixed with ``mock-``; this
script removes those transactions and rebuilds affected balances from the lots.

Usage: python -m scripts.clean_mock_points [--dry-run]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select

from app.db import database
from app.db.membership_models import PointAccount, PointLot, PointTransaction


async def main(dry_run: bool) -> None:
    async with database.async_session() as db:
        transactions = (await db.scalars(select(PointTransaction))).all()
        mock_transactions = [row for row in transactions if str(row.event_key).startswith("mock-")]
        lots = (await db.scalars(select(PointLot))).all()
        lots_with_refunds = {
            row.order_id for row in transactions
            if str(row.event_key).startswith("mock-") and row.kind == "refund"
        }
        mock_lots = [
            lot for lot in lots
            if lot.order_id in {tx.order_id for tx in mock_transactions} and lot.order_id not in lots_with_refunds
        ]
        print(f"拟删除模拟积分流水 {len(mock_transactions)} 条，模拟订单积分批次 {len(mock_lots)} 条")
        if dry_run:
            return
        for tx in mock_transactions:
            await db.delete(tx)
        for lot in mock_lots:
            await db.delete(lot)
        await db.flush()
        accounts = (await db.scalars(select(PointAccount))).all()
        for account in accounts:
            remaining = sum(
                max(lot.remaining_points, 0)
                for lot in (await db.scalars(
                    select(PointLot).where(PointLot.user_id == account.user_id)
                )).all()
            )
            account.book_balance = remaining
        await db.commit()
    print("模拟积分已清理，余额已按剩余批次重算")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="清理模拟支付产生的积分")
    parser.add_argument("--dry-run", action="store_true", help="只统计不删除")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
