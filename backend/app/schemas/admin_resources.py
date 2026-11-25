"""Validation and response contracts for operator resource management."""

import re
from datetime import date, datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, model_validator

SupplierStatus = Literal["active", "inactive"]
ProductType = Literal["hotel_room", "attraction_ticket", "vehicle"]
ProductStatus = Literal["on_shelf", "off_shelf"]
PoiKind = Literal["hotel", "attraction", "service_point"]
OfferStatus = Literal["available", "stopped"]
UnavailableReason = Literal["supplier_inactive", "product_off_shelf", "unquoted", "offer_stopped"]
Name = Annotated[str, Field(min_length=1, max_length=160)]
ShortName = Annotated[str, Field(min_length=1, max_length=100)]
ResourceId = Annotated[str, Field(min_length=1, max_length=36)]
People = Annotated[int, Field(strict=True, gt=0)]
MoneyFen = Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)]
MAX_OFFER_DAYS = 366

POI_TYPES_BY_PRODUCT: dict[ProductType, PoiKind] = {
    "hotel_room": "hotel", "attraction_ticket": "attraction", "vehicle": "service_point",
}
PRICE_UNITS: dict[ProductType, str] = {
    "hotel_room": "间夜", "attraction_ticket": "张", "vehicle": "车天",
}


def _read_service_date(value: object) -> date:
    if type(value) is date:
        return value
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("服务日期格式应为 YYYY-MM-DD")
    return date.fromisoformat(value)


ServiceDate = Annotated[date, BeforeValidator(_read_service_date)]


class ResourceBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PartialResourceBody(ResourceBody):
    @model_validator(mode="after")
    def check_explicit_values(self):
        for field in self.model_fields_set - {"poi"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} 不能为空")
        return self


class SupplierCreate(ResourceBody):
    name: Name
    settlement_name: Name
    contact_name: str = Field("", max_length=100)
    contact_info: str = Field("", max_length=160)
    notes: str = Field("", max_length=4000)
    status: SupplierStatus = "active"


class SupplierPatch(PartialResourceBody):
    name: Name | None = None
    settlement_name: Name | None = None
    contact_name: str | None = Field(None, max_length=100)
    contact_info: str | None = Field(None, max_length=160)
    notes: str | None = Field(None, max_length=4000)
    status: SupplierStatus | None = None


class SupplierResponse(SupplierCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_attachment_ref: str | None
    settlement_workflow_ref: str | None
    created_at: datetime
    updated_at: datetime


class PoiReference(ResourceBody):
    source: Literal["amap", "chroma"]
    id: ShortName
    name: Name
    city: ShortName
    type: PoiKind


class PoiSearchResponse(BaseModel):
    items: list[PoiReference]
    warning: str | None = None


class HotelAttributes(ResourceBody):
    room_name: Name
    occupancy: People
    breakfast: Name


class TicketAttributes(ResourceBody):
    ticket_name: Name
    audience: Name


class VehicleAttributes(ResourceBody):
    vehicle_name: Name
    passenger_capacity: People


ProductAttributes = HotelAttributes | TicketAttributes | VehicleAttributes
ATTRIBUTE_TYPES = {
    "hotel_room": HotelAttributes,
    "attraction_ticket": TicketAttributes,
    "vehicle": VehicleAttributes,
}


class ProductCreate(ResourceBody):
    supplier_id: ResourceId
    name: Name
    type: ProductType
    city: ShortName
    attributes: ProductAttributes
    poi: PoiReference | None = None
    status: ProductStatus = "off_shelf"

    @model_validator(mode="after")
    def check_product_type(self):
        if not isinstance(self.attributes, ATTRIBUTE_TYPES[self.type]):
            raise ValueError("商品规格与所选类型不匹配")
        if self.poi and self.poi.type != POI_TYPES_BY_PRODUCT[self.type]:
            raise ValueError("POI 类型与所选商品类型不匹配")
        return self


class ProductPatch(PartialResourceBody):
    supplier_id: ResourceId | None = None
    name: Name | None = None
    type: ProductType | None = None
    city: ShortName | None = None
    attributes: ProductAttributes | None = None
    poi: PoiReference | None = None
    status: ProductStatus | None = None


class ProductResponse(ProductCreate):
    id: str
    supplier_name: str
    supplier_status: SupplierStatus
    price_unit: str
    offer_count: int
    created_at: datetime
    updated_at: datetime


class OfferValues(ResourceBody):
    cost_fen: MoneyFen
    sale_fen: MoneyFen
    status: OfferStatus


class OfferCreate(OfferValues):
    service_date: ServiceDate


class OfferPatch(PartialResourceBody):
    cost_fen: MoneyFen | None = None
    sale_fen: MoneyFen | None = None
    status: OfferStatus | None = None


class OfferBatch(OfferValues):
    start_date: ServiceDate
    end_date: ServiceDate
    overwrite: StrictBool = False


class OfferBatchResult(BaseModel):
    created: int
    updated: int


class OfferQuote(OfferValues):
    below_cost: bool


class OfferDay(BaseModel):
    service_date: date
    quote: OfferQuote | None
    can_sell: bool
    reasons: list[UnavailableReason]


class HotelStay(BaseModel):
    check_in: date
    check_out: date
    nights: int
    can_sell: bool
    cost_fen: int | None
    sale_fen: int | None
    unavailable: list[OfferDay]


T = TypeVar("T")


class ResourcePage(BaseModel, Generic[T]):
    items: list[T]
    total: int


class OfferPage(ResourcePage[OfferDay]):
    stay: HotelStay | None = None
