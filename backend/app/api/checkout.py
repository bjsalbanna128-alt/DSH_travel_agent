from datetime import date

from fastapi import APIRouter, Depends

from app.api.deps import CurrentAccount, WriteDbSession
from app.api.support import no_store, require_tourist
from app.services import checkout, orders

router = APIRouter(prefix="/v1/checkout", dependencies=[Depends(no_store), Depends(require_tourist)])


@router.get("/options")
async def checkout_options(trip_id: str, account: CurrentAccount, db: WriteDbSession, departure_date: date | None = None):
    trip = await checkout.load_trip(db, account.id, trip_id)
    await orders.expire_due(db)
    return await checkout.options(db, trip, departure_date, orders._today())
