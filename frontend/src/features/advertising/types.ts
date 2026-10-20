import type { Priority, RiskResult } from '@/lib/types'

export type ReviewState = 'needs_review' | 'reviewed' | 'dismissed'
export type Decision = 'confirmed' | 'rejected' | 'insufficient'
export interface Analysis {
  status: 'queued' | 'running' | 'ready' | 'failed' | 'unsupported'
  errorCode: string | null; canRetry: boolean; updatedAt: string | null
}
export interface MaterialSummary {
  id: string; version: number; title: string; textPreview: string; reviewState: ReviewState
  origins: ('automatic' | 'manual')[]; platforms: string[]; occurrenceCount: number
  firstSeenAt: string; lastSeenAt: string; complex: { id: string; name: string } | null
  priority: Priority; analysis: Analysis
}
export interface Media {
  id: string; kind: 'image' | 'video' | 'thumbnail'; url: string | null
  availability: 'private' | 'external' | 'unavailable'; analyzed: boolean
}
export interface Occurrence {
  id: string; origin: 'automatic' | 'manual'; platform: string; account: string; originalUrl: string | null
  publishedAt: string | null; capturedAt: string; text: string; media: Media[]
  legacyKind: 'monitoring' | 'advertisement'; legacyId: string
}
export interface Hypothesis {
  id: string; code: 'R2' | 'R3'; quote: string; explanation: string; occurrenceId: string
  decision: Decision | 'pending'
}
export interface MaterialDetail extends MaterialSummary {
  text: string; revisionId: string; occurrences: Occurrence[]; nextOccurrenceCursor: string | null
  hypotheses: Hypothesis[]; complexCandidates: { id: string; name: string; address: string }[]
  confirmedRisk: RiskResult | null
  review: { notes: string; reviewedAt: string; reviewerDisplayName: string | null } | null
}
export interface ReviewBody {
  requestId: string; expectedVersion: number; revisionId: string; complexId: string | null
  expectedComplexVersion: number | null; decisions: { hypothesisId: string; decision: Decision }[]
  notes: string; disposition: 'reviewed' | 'needs_review' | 'dismissed'
}
export interface MaterialPage<T> { items: T[]; nextCursor: string | null }
