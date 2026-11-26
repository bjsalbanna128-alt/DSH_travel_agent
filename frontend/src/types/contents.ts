export type ContentKind = 'attraction' | 'hotel'
export type ContentStatus = 'draft' | 'published' | 'unpublished'

export const contentKindLabels: Record<ContentKind, string> = {
  attraction: '景点', hotel: '酒店',
}

export const contentStatusLabels: Record<ContentStatus, string> = {
  draft: '草稿', published: '已上线', unpublished: '已下架',
}

export interface BoundProduct {
  id: string
  name: string
  type: string
  status: string
}

export interface ContentRecord {
  id: string
  kind: ContentKind
  city: string
  name: string
  category: string
  rating: number | null
  visit_duration_hours: number | null
  opening_hours: string
  ticket_price_hint_cny: number | null
  star_rating: number | null
  landmark_hint: string
  lat: number | null
  lng: number | null
  tags: string[]
  suitable_for: string[]
  description: string
  highlights: string[]
  cover_image_url: string
  source: string
  status: ContentStatus
  created_at: string
  updated_at: string
  products: BoundProduct[]
}

export interface ContentFields {
  kind: ContentKind
  city: string
  name: string
  category: string
  rating: number | null
  visit_duration_hours: number | null
  opening_hours: string
  ticket_price_hint_cny: number | null
  star_rating: number | null
  landmark_hint: string
  lat: number | null
  lng: number | null
  tags: string[]
  suitable_for: string[]
  description: string
  highlights: string[]
  cover_image_url: string
}

export interface ContentPage {
  items: ContentRecord[]
  total: number
}

export interface SyncResult {
  added: number
  updated: number
  removed: number
}
