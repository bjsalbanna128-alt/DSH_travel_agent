import type { UserProfile } from './profile'

export type DocumentType = 'id_card' | 'passport' | 'hong_kong_macau' | 'taiwan' | 'other'
export type Gender = 'female' | 'male' | 'other' | 'undisclosed'
export type PointKind = 'payment' | 'refund' | 'expiry'

export const documentLabels: Record<DocumentType, string> = {
  id_card: '身份证', passport: '护照', hong_kong_macau: '港澳证件', taiwan: '台湾证件', other: '其他证件',
}
export const genderLabels: Record<Gender, string> = { female: '女', male: '男', other: '其他', undisclosed: '不公开' }
export const pointLabels: Record<PointKind, string> = { payment: '支付入账', refund: '退款冲回', expiry: '积分过期' }

export interface ContactView {
  real_name: string | null
  phone_mask: string | null
  document_type: DocumentType | null
  document_mask: string | null
  document_filled: boolean
}

export interface MemberProfile extends ContactView {
  exists: boolean
  nickname: string | null
  avatar_url: string | null
  birthday: string | null
  gender: Gender | null
}

export interface Traveler extends ContactView {
  id: string
  relationship: string
  is_default: boolean
}

export interface MemberSummary {
  id: string
  username: string
  registered_at: string | null
  profile_complete: boolean
  effective_balance: number
}

export interface PointOverview {
  effective_balance: number
  demo_balance?: number
  demo_payments?: number
  demo_refunds?: number
  as_of: string
  expiring: { order_id: string; remaining_points: number; expires_at: string }[]
}

export interface PointEntry {
  id: string
  kind: PointKind
  order_id: string
  refund_id: string | null
  delta: number
  amount_fen: number | null
  occurred_at: string
  recorded_at: string
  book_balance_after: number
}

export interface MemberDetail extends MemberSummary {
  profile: MemberProfile
  travelers: Traveler[]
  preferences: UserProfile | null
  points: PointOverview
}

export interface ContactChanges {
  phone: string
  documentType: DocumentType | ''
  documentNumber: string
  clearPhone: boolean
  clearDocument: boolean
}

export function contactChanges(contact?: ContactView): ContactChanges {
  return { phone: '', documentType: contact?.document_type ?? '', documentNumber: '', clearPhone: false, clearDocument: false }
}

export function contactPayload(form: ContactChanges, contact?: ContactView) {
  const phone = form.phone.trim()
  const documentNumber = form.documentNumber.trim()
  if (!form.clearDocument && (
    (documentNumber && !form.documentType)
    || (!documentNumber && form.documentType !== (contact?.document_type ?? ''))
  )) throw new Error('更新证件时请同时选择类型和填写完整号码。')
  return {
    phone: form.clearPhone ? null : phone || undefined,
    document_type: !form.clearDocument && documentNumber ? form.documentType : undefined,
    document_number: !form.clearDocument && documentNumber ? documentNumber : undefined,
    clear_document: form.clearDocument || undefined,
  }
}

const formatter = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai' })
export const memberTime = (value: string | null) => value ? formatter.format(new Date(value)) : '—'
