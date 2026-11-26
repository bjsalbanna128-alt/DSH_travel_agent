"""Add the Beijing demonstration fleet and a rolling 90-day offer window."""

import argparse
import asyncio
from datetime import date, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db import database
from app.db.fleet_models import FleetModel
from app.db.resource_models import Driver, PriceOffer, Product, Supplier, Vehicle
from app.services.orders import BEIJING


def seed_id(key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"travel-agent/beijing-demo-fleet/{key}"))


SUPPLIER_ID = seed_id("supplier")
MODELS = (
    ("sedan", "5 座轿车", 4, 2, 300, 600),
    ("business", "7 座商务", 6, 4, 450, 900),
    ("bus", "大巴", 20, 10, 800, 1500),
)


async def seed(sessions, start: date) -> dict[str, int]:
    days = [start + timedelta(days=offset) for offset in range(90)]
    created = dict(suppliers=0, models=0, vehicles=0, drivers=0, products=0, offers=0)
    async with sessions.begin() as db:
        insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
        created["suppliers"] = (await db.execute(insert(Supplier).values(
            id=SUPPLIER_ID, name="北京演示车队", settlement_name="北京演示车队", kind="vehicle_fleet",
            fleet_city="北京", contact_name="演示联系人", contact_info="000-00000000",
        ).on_conflict_do_nothing(index_elements=[Supplier.id]))).rowcount
        # Share the roster lock with checkout and the operator APIs.
        await db.scalar(select(Supplier).where(Supplier.id == SUPPLIER_ID).with_for_update())
        for number, (code, name, seats, luggage, pickup, charter) in enumerate(MODELS):
            if await db.get(FleetModel, (SUPPLIER_ID, code)) is None:
                db.add(FleetModel(supplier_id=SUPPLIER_ID, code=code, name=name))
                created["models"] += 1
            for index in range(2):
                key = seed_id(f"vehicle/{code}/{index}")
                if await db.get(Vehicle, key) is None:
                    db.add(Vehicle(id=key, supplier_id=SUPPLIER_ID, plate_no=f"京演示{number}{index}",
                                   model_code=code, model_name=name, seats=seats, luggage=luggage))
                    created["vehicles"] += 1
            for purpose, label, yuan in (("airport_transfer", "接机", pickup), ("charter", "全天包车", charter)):
                key = seed_id(f"product/{code}/{purpose}")
                if await db.get(Product, key) is None:
                    db.add(Product(id=key, supplier_id=SUPPLIER_ID, name=f"{name} · {label}", type="vehicle",
                                   city="北京", status="on_shelf", attributes={
                                       "model_code": code, "vehicle_name": name, "purpose": purpose,
                                       "passenger_capacity": seats, "luggage_capacity": luggage,
                                   }))
                    await db.flush()
                    created["products"] += 1
                existing = set(await db.scalars(select(PriceOffer.service_date).where(
                    PriceOffer.product_id == key, PriceOffer.service_date.between(days[0], days[-1]),
                )))
                new_offers = [PriceOffer(product_id=key, service_date=day, cost_fen=yuan * 70,
                                         sale_fen=yuan * 100, total_quantity=3, status="available", trip_priced=True)
                              for day in days if day not in existing]
                db.add_all(new_offers)
                created["offers"] += len(new_offers)
        for index, codes in enumerate((("sedan", "business"), ("sedan", "business"), ("bus",),
                                       ("sedan", "business", "bus")), start=1):
            key = seed_id(f"driver/{index}")
            if await db.get(Driver, key) is None:
                db.add(Driver(id=key, supplier_id=SUPPLIER_ID, name=f"演示司机 {index}", phone=f"000-0000000{index}",
                              license_type="A1" if "bus" in codes else "C1", service_cities=["北京"], model_codes=list(codes)))
                created["drivers"] += 1
    return created


async def main(start: date) -> None:
    await database.init_db()
    print(await seed(database.async_session, start))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", type=date.fromisoformat, default=datetime.now(BEIJING).date())
    asyncio.run(main(parser.parse_args().start_date))
