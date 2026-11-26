export type SupplierStatus = 'active' | 'inactive'
export type SupplierKind = 'hotel' | 'ticket' | 'vehicle_fleet' | 'other'
export type ProductType = 'hotel_room' | 'attraction_ticket' | 'vehicle'
export type ProductStatus = 'on_shelf' | 'off_shelf'
export type PoiKind = 'hotel' | 'attraction' | 'service_point'
export type OfferStatus = 'available' | 'stopped'

export const supplierKindLabels: Record<SupplierKind, string> = {
  hotel: '酒店', ticket: '景区票务', vehicle_fleet: '车队', other: '其他',
}

export interface SupplierFields {
  name: string
  settlement_name: string
  kind: SupplierKind
  fleet_city?: string
  contact_name: string
  contact_info: string
  notes: string
}

export interface Supplier extends SupplierFields {
  id: string
  status: SupplierStatus
  created_at: string
  updated_at: string
}

export interface PoiReference {
  source: 'amap' | 'chroma' | 'seed'
  id: string
  name: string
  city: string
  type: PoiKind
  lat?: number | null
  lng?: number | null
}

export type ProductAttributes =
  | { room_name: string; occupancy: number; breakfast: string }
  | { ticket_name: string; audience: string }
  | { vehicle_name: string; passenger_capacity: number; model_code?: string | null;
      purpose?: import('./checkout').VehiclePurpose | null; luggage_capacity?: number | null }

export interface ProductFields {
  supplier_id: string
  name: string
  type: ProductType
  city: string
  attributes: ProductAttributes
  poi: PoiReference | null
}

export interface Product extends ProductFields {
  id: string
  status: ProductStatus
  supplier_name: string
  supplier_status: SupplierStatus
  price_unit: string
  offer_count: number
}

export interface PageResult<T> {
  items: T[]
  total: number
}

export interface OfferValues {
  cost_fen: number
  sale_fen: number
  status: OfferStatus
  total_quantity: number | null
  trip_priced?: boolean
}

export interface OfferQuote extends OfferValues {
  below_cost: boolean
  reserved_quantity: number
  confirmed_quantity: number
  remaining: number | null
  stock_verified: boolean
}

export type UnavailableReason =
  | 'supplier_inactive' | 'product_off_shelf' | 'unquoted' | 'offer_stopped'
  | 'unverified_stock' | 'sold_out' | 'unverified_trip_price' | 'vehicle_configuration'

export interface OfferDay {
  service_date: string
  quote: OfferQuote | null
  can_sell: boolean
  reasons: UnavailableReason[]
}

export interface HotelStay {
  check_in: string
  check_out: string
  nights: number
  can_sell: boolean
  cost_fen: number | null
  sale_fen: number | null
  unavailable: OfferDay[]
}

export interface OfferPage extends PageResult<OfferDay> {
  stay: HotelStay | null
}

export const productLabels: Record<ProductType, string> = {
  hotel_room: '酒店房型', attraction_ticket: '景点门票', vehicle: '用车车型',
}

export const poiTypes: Record<ProductType, PoiKind> = {
  hotel_room: 'hotel', attraction_ticket: 'attraction', vehicle: 'service_point',
}

export const poiSourceLabels: Record<PoiReference['source'], string> = {
  amap: '高德', chroma: '本地种子', seed: '自建种子',
}

export const offerReasons: Record<UnavailableReason, string> = {
  supplier_inactive: '供应商停用', product_off_shelf: '商品下架',
  unquoted: '未报价', offer_stopped: '当日停售',
  unverified_stock: '库存未核定', sold_out: '已售罄',
  unverified_trip_price: '按趟售价未核定',
  vehicle_configuration: '车队、车型或用途待补齐',
}
