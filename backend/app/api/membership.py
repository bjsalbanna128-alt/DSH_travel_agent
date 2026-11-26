"""Tourist self-service and operator read-only membership endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.api.deps import CurrentAccount, DbSession, WriteDbSession
from app.api.support import Page, no_store, require_tourist
from app.schemas.admin_resources import ResourcePage
from app.schemas.membership import (
    MemberDetail, MemberSummary, PointEntry, PointKind, PointOverview, ProfilePatch,
    ProfileView, TouristPointOverview, TravelerCreate, TravelerPatch, TravelerView,
)
from app.services import members


class PrivateInputRoute(APIRoute):
    def get_route_handler(self):
        handle = super().get_route_handler()

        async def sanitized(request):
            try:
                return await handle(request)
            except RequestValidationError:
                # Default FastAPI details can include the submitted personal data and user-supplied keys.
                raise HTTPException(
                    422, "填写内容或查询条件无效。更新证件时请同时填写类型和完整号码。",
                    headers={"Cache-Control": "private, no-store"},
                ) from None

        return sanitized


tourist_router = APIRouter(
    prefix="/v1/members", route_class=PrivateInputRoute,
    dependencies=[Depends(require_tourist), Depends(no_store)],
)
admin_router = APIRouter(prefix="/members", route_class=PrivateInputRoute, dependencies=[Depends(no_store)])


@tourist_router.get("/profile", response_model=ProfileView)
async def profile(account: CurrentAccount, db: DbSession):
    return await members.my_profile(db, account.id)


@tourist_router.patch("/profile", response_model=ProfileView)
async def save_profile(body: ProfilePatch, account: CurrentAccount, db: WriteDbSession):
    result = await members.update_profile(db, account.id, body)
    await db.commit()
    return result


@tourist_router.get("/travelers", response_model=list[TravelerView])
async def travelers(account: CurrentAccount, db: DbSession):
    return await members.list_travelers(db, account.id)


@tourist_router.post("/travelers", response_model=TravelerView, status_code=201)
async def add_traveler(body: TravelerCreate, account: CurrentAccount, db: WriteDbSession):
    result = await members.add_traveler(db, account.id, body)
    await db.commit()
    return result


@tourist_router.get("/travelers/{traveler_id}", response_model=TravelerView)
async def get_traveler(traveler_id: str, account: CurrentAccount, db: DbSession):
    return await members.get_traveler(db, account.id, traveler_id)


@tourist_router.patch("/travelers/{traveler_id}", response_model=TravelerView)
async def patch_traveler(traveler_id: str, body: TravelerPatch, account: CurrentAccount, db: WriteDbSession):
    result = await members.update_traveler(db, account.id, traveler_id, body)
    await db.commit()
    return result


@tourist_router.delete("/travelers/{traveler_id}", status_code=204)
async def delete_traveler(traveler_id: str, account: CurrentAccount, db: WriteDbSession):
    await members.delete_traveler(db, account.id, traveler_id)
    await db.commit()
    return Response(status_code=204, headers={"Cache-Control": "private, no-store"})


@tourist_router.get("/points", response_model=TouristPointOverview)
async def my_points(account: CurrentAccount, db: DbSession):
    from app.services.demo_points import overview

    actual = await members.overview(db, account.id)
    demo = await overview(db, account.id)
    return TouristPointOverview(**actual.model_dump(), demo_balance=demo["balance"], demo_payments=demo["payments"],
                                demo_refunds=demo["refunds"])


class LedgerFilter:
    def __init__(
        self, order_id: Annotated[str, Query(max_length=128)] = "", kind: PointKind | None = None,
        start: date | None = None, end: date | None = None,
    ):
        self.order_id, self.kind, self.start, self.end = order_id.strip(), kind, start, end

    async def read(self, db, page, member_id):
        return await members.ledger(
            db, member_id, order_id=self.order_id, kind=self.kind, start=self.start, end=self.end,
            offset=page.offset, limit=page.limit,
        )


LedgerQuery = Annotated[LedgerFilter, Depends()]


@tourist_router.get("/point-transactions", response_model=ResourcePage[PointEntry])
async def my_ledger(account: CurrentAccount, db: DbSession, page: Page, filters: LedgerQuery):
    return await filters.read(db, page, account.id)


@admin_router.get("", response_model=ResourcePage[MemberSummary])
async def member_list(
    db: DbSession, page: Page, username: Annotated[str, Query(max_length=50)] = "",
    start: date | None = None, end: date | None = None,
):
    return await members.list_members(
        db, username=username.strip(), start=start, end=end, offset=page.offset, limit=page.limit,
    )


@admin_router.get("/{member_id}", response_model=MemberDetail)
async def member_detail(member_id: str, db: DbSession):
    return await members.member_detail(db, member_id)


@admin_router.get("/{member_id}/point-transactions", response_model=ResourcePage[PointEntry])
async def member_ledger(member_id: str, db: DbSession, page: Page, filters: LedgerQuery):
    await members.ensure_tourist(db, member_id)
    return await filters.read(db, page, member_id)
