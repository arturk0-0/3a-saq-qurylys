export type FactorCode = 'R1' | 'R2' | 'R3' | 'R4' | 'R5' | 'R6'
export type VerificationStatus = 'unknown' | 'proposed' | 'confirmed' | 'rejected'
export type RiskZone = 'GREEN' | 'YELLOW' | 'RED'
export interface RiskFactor {
  code: FactorCode; status: VerificationStatus; evidenceIds: string[]
  reviewer: string | null; reviewedAt: string | null; notes: string
}
export interface RiskResult {
  score: number; zone: RiskZone
  factors: { code: FactorCode; status: VerificationStatus; weight: number; points: number; evidenceIds: string[] }[]
}
export interface LegalBasis {
  type: 'guarantee' | 'regional_permit' | 'other_applicable' | 'unknown'
  status: 'confirmed' | 'disproved' | 'unknown'
  reference: string; source: string; checkedAt: string | null; reviewer: string | null; validUntil: string | null
}
export interface Complex {
  id: string; name: string; city: string; region: string; address: string; developerId: string
  aliases?: string[]
  stage: 'planning' | 'under_construction' | 'commissioned'
  coordinates: { latitude: number; longitude: number } | null
  progress: { claimedPercent: number | null; verifiedPercent: number | null; claimedAt: string | null;
    verifiedAt: string | null; claimedSource: string; verifiedSource: string }
  legalBasis: LegalBasis; factors: RiskFactor[]; demo: boolean; scenario: 'A' | 'B' | 'C' | null
  version: number; createdAt: string; updatedAt: string; risk: RiskResult
  authorizedCompany?: { id: string; name: string; bin: string; demo: boolean } | null
  partySnapshots?: { companyId: string; name: string; bin: string; role: 'developer' | 'authorized_company'; source: import('@/features/companies/types').Citation }[]
  participantSource?: import('@/features/companies/types').Citation | null
  coordinateSource?: import('@/features/companies/types').Citation | null
  coordinateStatus?: string | null
  developer?: { id: string; name: string; bin: string; demo: boolean }
}
export interface Advertisement {
  id: string; complexId: string; platform: string; account: string; sourceUrl: string; text: string
  publishedAt: string | null; capturedAt: string; createdBy: string; attachmentIds: string[]; demo: boolean; version: number
}
export interface Evidence {
  id: string; complexId: string; advertisementId: string | null
  type: 'advertisement' | 'legal_basis_review' | 'complaint' | 'progress_report' | 'work_status' | 'document' | 'screenshot'
  sourceUrl: string | null; sourceReference: string; excerpt: string; capturedAt: string
  status: VerificationStatus; reviewer: string | null; reviewedAt: string | null; version: number
  storagePath: string | null; sha256: string | null; demo: boolean
  legalAbsenceVerified: boolean; applicableBasesChecked: boolean; activeAdvertisingVerified: boolean
  constructionVerified: boolean; paymentOfferVerified: boolean; collectiveComplaintVerified: boolean
  workStoppageVerified: boolean; claimedPercent: number | null; verifiedPercent: number | null
  claimedAt: string | null; verifiedAt: string | null; claimedSource: string; verifiedSource: string
}
export interface AuditEvent {
  id: string; entityType: string; entityId: string; complexId: string | null
  action: string; actorUid: string; createdAt: string; demo: boolean; details: Record<string, unknown>
}
export interface Page<T> { items: T[]; nextCursor: string | null; total?: number; catalogLimited?: boolean }
