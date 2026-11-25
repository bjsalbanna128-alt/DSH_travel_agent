import type { ProductType } from './adminResources'

export type TemplateVisibility = 'draft' | 'published' | 'unpublished'
export type ActivityCategory = 'sightseeing' | 'dining' | 'accommodation' | 'transport' | 'other'

// Keep these limits aligned with app/schemas/itinerary_templates.py.
export const templateLimits = {
  title: 160, destination: 100, tags: 12, tag: 30, description: 2000, tips: 3000,
  days: 30, theme: 120, activities: 30, notes: 1500, time: 60, name: 160, activityDescription: 1000,
}

export const visibilityLabels: Record<TemplateVisibility, string> = {
  draft: '草稿', published: '已上线', unpublished: '已下架',
}

export const activityLabels: Record<ActivityCategory, string> = {
  sightseeing: '游览', dining: '餐饮', accommodation: '住宿', transport: '交通', other: '其他',
}

export interface ActivityDraft {
  time: string
  name: string
  category: ActivityCategory | null
  description: string
  product_id: string | null
}

export interface DayDraft {
  theme: string
  notes: string
  activities: ActivityDraft[]
}

export interface TemplateDraft {
  title: string
  destination: string
  tags: string[]
  description: string
  tips: string
  days: DayDraft[]
}

export interface TemplateSummary {
  id: string
  title: string
  destination: string
  days_count: number
  visibility: TemplateVisibility
  revision: number
  published_version: number
  has_unpublished_changes: boolean
  updated_at: string
}

export interface LinkedProduct {
  id: string
  name: string
  type: ProductType
}

export interface TemplateDetail extends TemplateSummary {
  draft: TemplateDraft
  linked_products: LinkedProduct[]
  published_at: string | null
  message: string | null
}

export interface TemplateContent extends Omit<TemplateDraft, 'days'> {
  days: (Omit<DayDraft, 'activities'> & {
    day: number
    activities: (Omit<ActivityDraft, 'product_id'> & { product: LinkedProduct | null; missingProduct?: string })[]
  })[]
}

export interface PublishedTemplate extends TemplateContent {
  id: string
  version: number
  days_count: number
  published_at: string
}
