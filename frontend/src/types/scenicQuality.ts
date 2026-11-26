import type { PoiReference } from './adminResources'

export const restrictionKinds = { closure: '闭园', reservation: '需预约', admission: '其他入园限制' }
export const restrictionStates = { draft: '草稿', published: '已发布', inactive: '已停用' }
export const qualityRules = { ...restrictionKinds, budget: '超预算', duration: '单日过满', no_attractions: '无景点', lookup: '限制检索' }
export const qualityStatuses = { violation: '违规', verify: '待核实', notice: '提醒', pass: '通过', unchecked: '未质检' }
export const qualityStages = { initial: '初稿', adjusted: '调整稿' }

export interface ScenicDraft {
  poi: PoiReference
  kind: keyof typeof restrictionKinds
  starts_on: string
  ends_on: string | null
  description: string
  source_note: string
}

export interface ScenicRestriction extends ScenicDraft {
  id: string
  revision: number
  published_version: number
  has_unpublished_changes: boolean
  visibility: keyof typeof restrictionStates
}

export interface QualitySummary {
  trip_id: string
  version: number
  destination: string
  stage: keyof typeof qualityStages | null
  checked_at: string | null
  status: keyof typeof qualityStatuses
}

export interface QualityFinding {
  rule: keyof typeof qualityRules
  result: 'violation' | 'verify' | 'notice'
  reason: string
  day: number | null
  visit_date: string | null
  attraction: string | null
  restriction_id: string | null
  restriction_version: number | null
  matched_by: 'id' | 'unique_name' | 'ambiguous' | null
  description: string | null
  source_note: string | null
}

export interface QualityDetail extends QualitySummary {
  findings: QualityFinding[]
}
