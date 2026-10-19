export interface Citation {
  publisher: string; url: string; retrievedAt: string; effectiveDate: string | null; responseSha256: string;
}
export interface Party {
  bin: string; name: string; website: string | null; role: 'developer' | 'authorized_company';
}
export interface SourceProject {
  recordId: string; name: string; address: string; city: string; parties: Party[];
  source: Citation; stage: 'under_construction' | 'commissioned' | null; stageSource: Citation | null;
  coordinates: { latitude: number; longitude: number } | null;
  coordinateStatus: 'source_point' | 'unavailable' | 'outside_city';
  commissioningReference: string | null; commissioningDate: string | null; documentSha256: string;
}
export interface Company {
  id: string; bin: string; name: string; demo: boolean; version: number;
  facts: { field: string; value: string; source: Citation; status: 'source_reported' }[];
  projects: SourceProject[]; updatedAt: string | null; lastError: string | null;
  foundCompletedCount: number | null; coverage: 'saved_source_projects_only' | 'legacy_internal_record';
}
export interface Preview { project: SourceProject; savedVersion: number; canImportToRegistry: boolean }
export interface Candidate { recordId: string; name: string; address: string; developer: string; holder: string; sourceUrl: string }
