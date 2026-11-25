"""Assign or revoke operator access on an existing account."""

import argparse
import asyncio
import sys

from sqlalchemy import select, text

from app.db import database
from app.db.models import User, UserRole


async def set_user_role(username: str, role: UserRole) -> str | None:
    async with database.async_session.begin() as db:
        if db.get_bind().dialect.name == "sqlite":
            await db.execute(text("BEGIN IMMEDIATE"))
        account = await db.scalar(select(User).where(User.username == username).with_for_update())
        if account is None:
            return None
        previous_role = account.role
        account.role = role
        return previous_role


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="设置已有账号的运营或游客身份")
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", required=True, type=UserRole, choices=list(UserRole))
    args = parser.parse_args(argv)

    previous_role = asyncio.run(set_user_role(args.username, args.role))
    if previous_role is None:
        print(f"账号不存在：{args.username}", file=sys.stderr)
        return 1
    print(f"{args.username}: {previous_role} -> {args.role}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
