import type { TemplateVisibility } from './itineraryTemplates'

export interface RecommendationFields {
  title: string
  place: string
  short_text: string
  display_order: number
}

export interface CoverInfo {
  id: string
  url: string
  mime: string
  width: number
  height: number
  size_bytes: number
}

export interface RecommendationDraft extends RecommendationFields {
  id: string
  cover: CoverInfo | null
  visibility: TemplateVisibility
  revision: number
  published_version: number
  has_unpublished_changes: boolean
  updated_at: string
  message: string | null
}

export interface PublishedRecommendation {
  id: string
  version: number
  title: string
  place: string
  short_text: string
  cover_url: string
}
