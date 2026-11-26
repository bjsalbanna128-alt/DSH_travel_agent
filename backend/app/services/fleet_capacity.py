"""Serialize fleet changes and check each distinct overlapping interval."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from app.db.fleet_models import FleetAllocation
from app.db.order_models import Order
from app.db.resource_models import Driver, Product, Supplier, Vehicle
from app.services.scenic_restrictions import city_key

HELD = ("reserved", "confirmed")


def utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Demand:
    model_code: str
    starts_at: datetime
    ends_at: datetime
    passengers: int
    luggage: int
    vehicle_id: str | None = None
    driver_id: str | None = None

    @classmethod
    def from_row(cls, row):
        return cls(row.model_code, utc(row.starts_at), utc(row.ends_at), row.passengers, row.luggage,
                   row.vehicle_id, row.driver_id)


@dataclass(frozen=True)
class Car:
    id: str
    model_code: str | None
    seats: int
    luggage: int


@dataclass(frozen=True)
class QualifiedDriver:
    id: str
    model_codes: tuple[str, ...]


async def lock_fleets(db, supplier_ids):
    for key in sorted(set(supplier_ids)):
        await db.get(Supplier, key, with_for_update=True, populate_existing=True)


async def lock_product_suppliers(db, product_ids, *, additional=()):
    owners = dict((await db.execute(select(Product.id, Product.supplier_id).where(
        Product.id.in_(product_ids),
    ))).all())
    await lock_fleets(db, [*owners.values(), *additional])
    return owners


async def lock_order_fleets(db, order_ids):
    if order_ids:
        ids = await db.scalars(select(FleetAllocation.supplier_id).where(FleetAllocation.order_id.in_(order_ids)))
        await lock_fleets(db, ids)


async def roster(db, supplier_id):
    vehicles = (await db.scalars(select(Vehicle).where(Vehicle.supplier_id == supplier_id, Vehicle.status == "active"))).all()
    drivers = (await db.scalars(select(Driver).where(Driver.supplier_id == supplier_id, Driver.status == "active"))).all()
    return (
        [Car(row.id, row.model_code, row.seats, row.luggage) for row in vehicles],
        [QualifiedDriver(row.id, tuple(row.model_codes or [])) for row in drivers
         if any(city_key(city) == "北京" for city in (row.service_cities or []))],
    )


async def commitments(db, supplier_id, *, start=None, end=None, now=None):
    clock = now or datetime.now(timezone.utc)
    query = select(FleetAllocation).join(Order, Order.id == FleetAllocation.order_id).where(
        FleetAllocation.supplier_id == supplier_id, FleetAllocation.state.in_(HELD),
        (Order.status != "pending_payment") | (Order.expires_at > clock),
    )
    if start is not None:
        query = query.where(FleetAllocation.ends_at > start)
    if end is not None:
        query = query.where(FleetAllocation.starts_at < end)
    return (await db.scalars(query)).all()


def _covers(choices):
    matched = {}

    def assign(index, seen):
        for resource in choices[index]:
            if resource in seen:
                continue
            seen.add(resource)
            previous = matched.get(resource)
            if previous is None or assign(previous, seen):
                matched[resource] = index
                return True
        return False

    return all(assign(index, set()) for index in sorted(range(len(choices)), key=lambda index: len(choices[index])))


def _overlapping_groups(demands):
    """Separate groups at boundaries where no service spans across."""
    group, latest = [], None
    for index in sorted(range(len(demands)), key=lambda index: demands[index].starts_at):
        demand = demands[index]
        if group and demand.starts_at >= latest:
            yield group
            group, latest = [], None
        group.append(index)
        latest = max(latest, demand.ends_at) if latest is not None else demand.ends_at
    if group:
        yield group


def _keep_resource_for_whole_service(demands, choices):
    # With one common choice set, the overlap count already proves that the
    # services can be assigned without changing resources partway through.
    if len({tuple(ids) for ids in choices}) <= 1:
        return True
    resources = {key: index for index, key in enumerate(sorted({key for ids in choices for key in ids}))}
    options = [[resources[key] for key in ids] for ids in choices]
    pending = [(0, (None,) * len(resources))]
    visited = set()
    while pending:
        index, busy_until = state = pending.pop()
        if index == len(demands):
            return True
        if state in visited:
            continue
        visited.add(state)
        demand = demands[index]
        next_start = demands[index + 1].starts_at if index + 1 < len(demands) else demand.ends_at
        for resource in options[index]:
            if busy_until[resource] is not None:
                continue
            updated = list(busy_until)
            updated[resource] = demand.ends_at
            pending.append((index + 1, tuple(
                end if end is not None and end > next_start else None for end in updated
            )))
    return False


def _fits_group(demands, vehicles, drivers):
    changes = defaultdict(lambda: (set(), set()))
    for index, demand in enumerate(demands):
        changes[demand.starts_at][0].add(index)
        changes[demand.ends_at][1].add(index)
    vehicle_choices = [
        [row.id for row in vehicles if row.model_code == demand.model_code and
         row.seats >= demand.passengers and row.luggage >= demand.luggage
         and (not demand.vehicle_id or row.id == demand.vehicle_id)]
        for demand in demands
    ]
    driver_choices = [
        [row.id for row in drivers if demand.model_code in (row.model_codes or [])
         and (not demand.driver_id or row.id == demand.driver_id)]
        for demand in demands
    ]
    active = set()
    for _, (starting, ending) in sorted(changes.items()):
        active.difference_update(ending)
        active.update(starting)
        if len(active) > min(len(vehicles), len(drivers)):
            return False
        if not _covers([vehicle_choices[key] for key in sorted(active)]) or not _covers(
            [driver_choices[key] for key in sorted(active)]
        ):
            return False
    return _keep_resource_for_whole_service(demands, vehicle_choices) and _keep_resource_for_whole_service(demands, driver_choices)


def fits(demands, vehicles, drivers, *, affected_after=None):
    return all(
        _fits_group([demands[index] for index in group], vehicles, drivers)
        for group in _overlapping_groups(demands)
        if affected_after is None or any(index >= affected_after for index in group)
    )


async def can_add(db, supplier_id, added, *, now=None):
    if not added:
        return True
    clock = now or datetime.now(timezone.utc)
    existing = await commitments(db, supplier_id, start=clock, now=clock)
    segments = [Demand.from_row(row) for row in existing]
    vehicles, drivers = await roster(db, supplier_id)
    return fits([*segments, *added], vehicles, drivers, affected_after=len(segments))


async def verify_roster_change(db, supplier_id, before, *, now=None):
    clock = now or datetime.now(timezone.utc)
    active = await commitments(db, supplier_id, start=clock, now=clock)
    if not active:
        return
    vehicles, drivers = await roster(db, supplier_id)
    # A changed resource can affect services linked through other overlaps.
    affected = set()
    demands = [Demand.from_row(row) for row in active]
    for group in _overlapping_groups(demands):
        overlap = [demands[index] for index in group]
        if _fits_group(overlap, *before) and not _fits_group(overlap, vehicles, drivers):
            affected.update(active[index].order_id for index in group)
    if affected:
        raise HTTPException(409, {"message": "此修改会使已预订的用车缺少可用车辆或司机。",
                                  "order_ids": sorted(affected)})
