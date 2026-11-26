from datetime import date

from fastapi import APIRouter, Depends

from app.api.deps import CurrentAccount, WriteDbSession
from app.api.support import no_store, require_tourist
from app.schemas.fleet import FleetQuoteRequest
from app.services import checkout, fleet_sales, orders

router = APIRouter(prefix="/v1/checkout", dependencies=[Depends(no_store), Depends(require_tourist)])


@router.get("/options")
async def checkout_options(trip_id: str, account: CurrentAccount, db: WriteDbSession, departure_date: date | None = None):
    trip = await checkout.load_trip(db, account.id, trip_id)
    await orders.expire_due(db)
    return await checkout.options(db, trip, departure_date, orders._today())


@router.post("/vehicle-quote")
async def vehicle_quote(payload: FleetQuoteRequest, account: CurrentAccount, db: WriteDbSession):
    trip = await checkout.load_trip(db, account.id, payload.trip_id)
    await orders.expire_due(db)
    clock = orders.now_utc()
    start, _ = checkout._start(trip, payload.departure_date, clock.astimezone(orders.BEIJING).date())
    result = await fleet_sales.quote(db, trip, start, payload, clock)
    result["selected_product_id"] = payload.product_id
    return result
