export interface CheckoutItem {
  key: string
  kind: 'hotel' | 'ticket'
  product_id: string | null
  place_name: string
  name: string
  service_date: string | null
  check_in: string | null
  check_out: string | null
  quantity: number
  unit_price_fen: number | null
  remaining: number | null
  sellable: boolean
  status: 'sellable' | 'sold_out' | 'reference' | 'needs_date'
  reason: string
  days: { day: number; service_date: string | null; price_fen: number | null; token: string | null; reason: string }[]
}

export interface CheckoutOptions {
  trip_id: string
  departure_date: string | null
  today: string
  date_selectable: boolean
  travelers: number
  items: CheckoutItem[]
  vehicle_offers: VehicleOffer[]
  sellable_count: number
  undated_count: number
  total_fen: number
}

export type VehiclePurpose = 'charter' | 'airport_transfer'

export interface VehicleLeg {
  origin: string
  destination: string
  distance_km: number | null
  duration_minutes: number | null
}

export interface VehicleModel {
  product_id: string
  supplier_id: string
  supplier_name: string
  model_code: string
  model_name: string
  passenger_capacity: number
  luggage_capacity: number
}

export interface VehicleOffer {
  service_key: string
  purpose: VehiclePurpose
  day: number
  service_date: string | null
  pickup: string
  dropoff: string
  suggested_start: string | null
  duration_minutes: number
  legs: VehicleLeg[]
  recommended: boolean
  reason: string
  models: VehicleModel[]
}

export interface VehicleSelection {
  service_key: string
  start_time: string | null
  pickup: string
  dropoff: string
  passengers: number
  luggage: number
}

export interface VehicleQuote {
  service_date: string | null
  starts_at: string | null
  ends_at: string | null
  reason: string | null
  recommended_product_id: string | null
  options: (VehicleModel & { price_fen: number | null; token: string | null; sellable: boolean; reason: string })[]
}

export interface VehicleOrderSelection {
  kind: 'vehicle'
  product_id: string
  service_date: string
  quantity: 1
  quotes: { service_date: string; token: string }[]
  vehicle: VehicleSelection
  price_fen: number
}

export const vehicleLabels: Record<VehiclePurpose, string> = { charter: '全天包车', airport_transfer: '接机' }
export function beijingTime(value: string) { return value.slice(0, 16).replace('T', ' ') }

export const kindLabels = { hotel: '住宿', ticket: '门票' }
export const offerLabels: Record<string, string> = {
  sellable: '可订', sold_out: '售罄', needs_date: '待选日', reference: '参考价',
  unquoted: '所选日期无报价', unverified_stock: '库存待核定', product_unavailable: '商品已下架',
  offer_stopped: '所选日期已停售', past_service_date: '服务日已过', price_changed: '价格已变化',
  not_in_itinerary: '当前行程已无此项目', reservation_missing: '占用与冻结明细不符',
  needs_time: '请填写上车时间', past_service_time: '服务开始时间已过',
  unverified_trip_price: '按趟售价待核定', timeslot_full: '该时段没有足够的车辆或司机',
  route_changed: '路线已变化，请刷新行程', price_or_terms_changed: '价格或服务条件已变化',
  passenger_limit: '超过乘客容量', luggage_limit: '行李放不下', invalid_time: '时段无效',
  invalid_airport: '请填写北京的具体机场和航站楼',
  invalid_dropoff: '请填写行程酒店、已登记的北京地点，或写明北京市行政区和详细地址',
  no_supply: '暂无可选车型',
}

export { formatFen } from './orders'
