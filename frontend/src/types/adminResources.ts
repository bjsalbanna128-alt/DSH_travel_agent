export type SupplierStatus = 'active' | 'inactive'
export type ProductType = 'hotel_room' | 'attraction_ticket' | 'vehicle'
export type ProductStatus = 'on_shelf' | 'off_shelf'
export type PoiKind = 'hotel' | 'attraction' | 'service_point'
export type OfferStatus = 'available' | 'stopped'

export interface SupplierFields {
  name: string
  settlement_name: string
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
  source: 'amap' | 'chroma'
  id: string
  name: string
  city: string
  type: PoiKind
}

export type ProductAttributes =
  | { room_name: string; occupancy: number; breakfast: string }
  | { ticket_name: string; audience: string }
  | { vehicle_name: string; passenger_capacity: number }

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
}

export type UnavailableReason =
  'supplier_inactive' | 'product_off_shelf' | 'unquoted' | 'offer_stopped'

export interface OfferDay {
  service_date: string
  quote: (OfferValues & { below_cost: boolean }) | null
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

export const poiSourceLabels: Record<PoiReference['source'], string> = { amap: '高德', chroma: '本地种子' }

export const offerReasons: Record<UnavailableReason, string> = {
  supplier_inactive: '供应商停用', product_off_shelf: '商品下架',
  unquoted: '未报价', offer_stopped: '当日停售',
}
