export interface CheckoutItem {
  kind: 'hotel' | 'ticket'
  product_id: string
  name: string
  service_date: string
  check_in: string | null
  check_out: string | null
  quantity: number
  unit_price_fen: number
  remaining: number | null
  sellable: boolean
  needs_date?: boolean
}

export interface CheckoutOptions {
  trip_id: string
  travelers: number
  items: CheckoutItem[]
  sellable_count: number
  undated_count: number
  offer_count: number
  total_fen: number
}

export const kindLabels: Record<'hotel' | 'ticket', string> = { hotel: '住宿', ticket: '门票' }

export const formatFen = (fen: number) => `¥${(fen / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`


