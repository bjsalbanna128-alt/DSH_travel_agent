"""Tourist-owned profiles, masked operator views and points read queries."""

from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import and_, func, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.membership_models import MemberProfile, PointLot, PointTransaction, Traveler
from app.db.models import User, UserProfile, UserRole
from app.schemas.admin_resources import ResourcePage
from app.schemas.membership import (
    ContactPatch, ExpiringLot, MemberDetail, MemberSummary, PointEntry, PointKind, PointOverview,
    ProfilePatch, ProfileView, TravelerCreate, TravelerPatch, TravelerView,
)
from app.services.member_points import BEIJING, utc_now
from app.services.member_privacy import MemberPrivacy, mask_name, mask_number, normalize_document, normalize_phone

PROFILE_FIELDS = {"nickname", "avatar_url", "birthday", "gender", "real_name"}
TRAVELER_FIELDS = {"real_name", "relationship", "is_default"}


def _public_contact(row: MemberProfile | Traveler, *, masked: bool) -> dict:
    return dict(
        real_name=mask_name(row.real_name) if masked else row.real_name, phone_mask=row.phone_mask,
        document_type=row.document_type, document_mask=row.document_mask, document_filled=bool(row.document_mask),
    )


def _profile_view(row: MemberProfile | None, *, masked: bool = False) -> ProfileView:
    if row is None:
        return ProfileView()
    return ProfileView(
        exists=True, nickname=row.nickname, avatar_url=row.avatar_url, birthday=row.birthday,
        gender=row.gender, **_public_contact(row, masked=masked),
    )


def _traveler_view(row: Traveler, *, masked: bool = False) -> TravelerView:
    return TravelerView(
        id=row.id, relationship=row.relationship, is_default=row.is_default,
        **_public_contact(row, masked=masked),
    )


def contact_context(user_id: str, record: str, field: str) -> bytes:
    return f"{user_id}\0{record}\0{field}".encode()


async def _write_contact(
    db: AsyncSession, row: MemberProfile | Traveler, patch: ContactPatch, record: str,
) -> None:
    if "phone" in patch.model_fields_set:
        if patch.phone is None:
            row.phone_ciphertext = row.phone_mask = None
        else:
            phone = normalize_phone(patch.phone.get_secret_value())
            row.phone_ciphertext = MemberPrivacy().encrypt(phone, context=contact_context(row.user_id, record, "phone"))
            row.phone_mask = mask_number(phone)
    if patch.clear_document:
        row.document_type = row.document_ciphertext = row.document_mask = row.document_digest = None
    elif patch.document_number is not None:
        kind = patch.document_type
        number = normalize_document(patch.document_number.get_secret_value())
        privacy = MemberPrivacy()
        digest = privacy.document_digest(kind, number)
        if isinstance(row, Traveler):
            duplicate = await db.scalar(select(Traveler.id).where(
                Traveler.user_id == row.user_id, Traveler.id != row.id,
                Traveler.document_type == kind, Traveler.document_digest == digest,
            ))
            if duplicate:
                raise HTTPException(409, "该证件已登记为常用出行人。")
        row.document_type, row.document_digest, row.document_mask = kind, digest, mask_number(number)
        row.document_ciphertext = privacy.encrypt(number, context=contact_context(row.user_id, record, "document"))


async def ensure_tourist(db: AsyncSession, user_id: str, *, lock: bool = False) -> User:
    query = select(User).where(User.id == user_id, User.role == UserRole.TOURIST)
    user = await db.scalar(query.with_for_update() if lock else query)
    if user is None:
        raise HTTPException(404, "游客账号不存在。")
    return user


def _validate_profile(patch: ProfilePatch) -> None:
    if patch.avatar_url is not None:
        try:
            url = urlsplit(patch.avatar_url)
            valid_url = url.scheme == "https" and url.hostname and url.username is None and url.password is None
        except ValueError:
            valid_url = False
        if not valid_url or any(char.isspace() for char in patch.avatar_url):
            raise HTTPException(422, "头像请填写有效的 HTTPS 图片地址。")
    if patch.birthday and patch.birthday > utc_now().astimezone(BEIJING).date():
        raise HTTPException(422, "生日不能晚于今天。")


async def my_profile(db: AsyncSession, user_id: str) -> ProfileView:
    return _profile_view(await db.get(MemberProfile, user_id))


async def update_profile(db: AsyncSession, user_id: str, patch: ProfilePatch) -> ProfileView:
    _validate_profile(patch)
    await ensure_tourist(db, user_id, lock=True)
    row = await db.get(MemberProfile, user_id)
    if row is None:
        if not patch.model_fields_set or not any(
            getattr(patch, key) is not None for key in patch.model_fields_set - {"clear_document"}
        ):
            return ProfileView()
        row = MemberProfile(user_id=user_id)
        db.add(row)
    await _write_contact(db, row, patch, "profile")
    for key in PROFILE_FIELDS & patch.model_fields_set:
        setattr(row, key, getattr(patch, key))
    await db.flush()
    return _profile_view(row)


async def list_travelers(db: AsyncSession, user_id: str, *, masked: bool = False) -> list[TravelerView]:
    result = await db.scalars(select(Traveler).where(Traveler.user_id == user_id).order_by(
        Traveler.is_default.desc(), Traveler.real_name, Traveler.id,
    ))
    return [_traveler_view(row, masked=masked) for row in result]


async def _traveler(db: AsyncSession, user_id: str, traveler_id: str) -> Traveler:
    row = await db.scalar(select(Traveler).where(Traveler.user_id == user_id, Traveler.id == traveler_id))
    if row is None:
        raise HTTPException(404, "出行人不存在。")
    return row


async def get_traveler(db: AsyncSession, user_id: str, traveler_id: str) -> TravelerView:
    return _traveler_view(await _traveler(db, user_id, traveler_id))


async def _update_traveler(db: AsyncSession, row: Traveler, patch: TravelerPatch) -> TravelerView:
    await _write_contact(db, row, patch, f"traveler/{row.id}")
    if patch.is_default:
        await db.execute(update(Traveler).where(
            Traveler.user_id == row.user_id, Traveler.id != row.id, Traveler.is_default.is_(True),
        ).values(is_default=False))
    for key in TRAVELER_FIELDS & patch.model_fields_set:
        setattr(row, key, getattr(patch, key))
    await db.flush()
    return _traveler_view(row)


async def add_traveler(db: AsyncSession, user_id: str, patch: TravelerCreate) -> TravelerView:
    await ensure_tourist(db, user_id, lock=True)
    row = Traveler(id=str(uuid4()), user_id=user_id, real_name=patch.real_name,
                   relationship=patch.relationship, is_default=False)
    db.add(row)
    return await _update_traveler(db, row, patch)


async def update_traveler(db: AsyncSession, user_id: str, traveler_id: str, patch: TravelerPatch) -> TravelerView:
    await ensure_tourist(db, user_id, lock=True)
    return await _update_traveler(db, await _traveler(db, user_id, traveler_id), patch)


async def delete_traveler(db: AsyncSession, user_id: str, traveler_id: str) -> None:
    await ensure_tourist(db, user_id, lock=True)
    await db.delete(await _traveler(db, user_id, traveler_id))
    await db.flush()


def _date_filters(column, start: date | None, end: date | None, *, naive: bool = False) -> list:
    if start and end and start > end:
        raise HTTPException(422, "开始日期不能晚于结束日期。")

    def midnight(day: date) -> datetime:
        clock = datetime.combine(day, time.min, tzinfo=BEIJING).astimezone(timezone.utc)
        return clock.replace(tzinfo=None) if naive else clock

    filters = []
    if start and start > date.min:
        filters.append(column >= midnight(start))
    if end and end < date.max:
        filters.append(column < midnight(end + timedelta(days=1)))
    return filters


def _active(now: datetime):
    return and_(PointLot.expires_at > now, PointLot.remaining_points > 0)


async def overview(db: AsyncSession, user_id: str, now: datetime | None = None) -> PointOverview:
    as_of = now or utc_now()
    # A single statement gives both totals and expiring lots the same database snapshot.
    active = _active(as_of)
    balance = select(func.coalesce(func.sum(PointLot.remaining_points), 0)).where(
        PointLot.user_id == user_id, active,
    ).scalar_subquery()
    due = select(PointLot.order_id, PointLot.remaining_points, PointLot.expires_at).where(
        PointLot.user_id == user_id, active, PointLot.expires_at <= as_of + timedelta(days=30),
    ).subquery()
    anchor = select(balance.label("effective_balance")).subquery()
    rows = (await db.execute(
        select(anchor.c.effective_balance, due.c.order_id, due.c.remaining_points, due.c.expires_at)
        .select_from(anchor.outerjoin(due, true()))
        .order_by(due.c.expires_at, due.c.order_id)
    )).all()
    return PointOverview(
        effective_balance=int(rows[0].effective_balance), as_of=as_of,
        expiring=[ExpiringLot.model_validate(row) for row in rows if row.order_id is not None],
    )


async def ledger(
    db: AsyncSession, user_id: str, *, order_id: str, kind: PointKind | None,
    start: date | None, end: date | None, offset: int, limit: int,
) -> ResourcePage[PointEntry]:
    filters = [PointTransaction.user_id == user_id, *_date_filters(PointTransaction.occurred_at, start, end)]
    if order_id:
        filters.append(PointTransaction.order_id == order_id)
    if kind:
        filters.append(PointTransaction.kind == kind)
    total = await db.scalar(select(func.count()).select_from(PointTransaction).where(*filters))
    rows = await db.scalars(select(PointTransaction).where(*filters).order_by(
        PointTransaction.sequence.desc(),
    ).offset(offset).limit(limit))
    return ResourcePage(items=[PointEntry.model_validate(row) for row in rows], total=total)


def _complete(row: MemberProfile | None) -> bool:
    return bool(row and row.nickname and row.real_name and row.phone_mask)


async def list_members(
    db: AsyncSession, *, username: str, start: date | None, end: date | None, offset: int, limit: int,
) -> ResourcePage[MemberSummary]:
    filters = [User.role == UserRole.TOURIST, *_date_filters(User.created_at, start, end, naive=True)]
    if username:
        filters.append(User.username.icontains(username, autoescape=True))
    total = await db.scalar(select(func.count()).select_from(User).where(*filters))
    points = select(PointLot.user_id, func.sum(PointLot.remaining_points).label("balance")).where(
        _active(utc_now()),
    ).group_by(PointLot.user_id).subquery()
    rows = await db.execute(
        select(User.id, User.username, User.created_at, MemberProfile, func.coalesce(points.c.balance, 0))
        .outerjoin(MemberProfile, MemberProfile.user_id == User.id).outerjoin(points, points.c.user_id == User.id)
        .where(*filters).order_by(User.created_at.desc().nulls_last(), User.id.desc()).offset(offset).limit(limit)
    )
    return ResourcePage(items=[MemberSummary(
        id=account_id, username=name, registered_at=registered_at, profile_complete=_complete(profile), effective_balance=int(balance),
    ) for account_id, name, registered_at, profile, balance in rows], total=total)


async def member_detail(db: AsyncSession, user_id: str) -> MemberDetail:
    user = await ensure_tourist(db, user_id)
    row = await db.get(MemberProfile, user_id)
    ai = await db.get(UserProfile, user_id)
    preferences = None if ai is None else {field: getattr(ai, field) for field in (
        "interest_tags", "pace_preference", "preferred_hotel_stars", "cuisine_preferences", "dietary_restrictions",
        "avg_budget_per_day_cny", "frequent_destinations", "feedback_scores", "travel_count",
    )}
    if preferences is not None:
        preferences.update(user_id=user_id, updated_at=ai.updated_at)
    points = await overview(db, user_id)
    return MemberDetail(
        id=user_id, username=user.username, registered_at=user.created_at, profile_complete=_complete(row),
        effective_balance=points.effective_balance, profile=_profile_view(row, masked=True),
        travelers=await list_travelers(db, user_id, masked=True), preferences=preferences, points=points,
    )
