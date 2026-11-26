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
  sellable_count: number
  undated_count: number
  total_fen: number
}

export const kindLabels = { hotel: '住宿', ticket: '门票' }
export const offerLabels: Record<string, string> = {
  sellable: '可订', sold_out: '售罄', needs_date: '待选日', reference: '参考价',
  unquoted: '所选日期无报价', unverified_stock: '库存待核定', product_unavailable: '商品已下架',
  offer_stopped: '所选日期已停售', past_service_date: '服务日已过', price_changed: '价格已变化',
  not_in_itinerary: '当前行程已无此项目', reservation_missing: '占用与冻结明细不符',
}

export { formatFen } from './orders'
