# Company API / B contract

Additive contract, Issue #21. All routes require the existing authenticated analyst
session. No client access to Firestore is added. Fields use camelCase JSON.

## Read and explicit collection

- `GET /api/v1/companies?limit=20&cursor=...`: saved profiles only; `items`,
  `nextCursor`. Stable document-ID pagination, no new composite index.
- `GET /api/v1/companies/{id}`: saved `CompanyRecord` plus
  `foundCompletedCount: number|null`, `coverage`. Historical `demo-developer-*`
  remains readable with `version:0`, no fabricated external facts/citations.
- `GET /api/v1/company-projects/search?q=...`: explicit Homeportal query,
  3–100 characters; `items` are candidates, not automatically imported.
- `GET /api/v1/company-projects/{numericId}`: public-source preview,
  `{project, savedVersion, canImportToRegistry}`. No database snapshot is saved.
- `POST /api/v1/company-projects/{numericId}`:
  `{expectedVersion, expectedDocumentSha256, importToRegistry:false}`.
  Re-reads the source and rejects changed material. Returns
  `{companyIds, registryId:null|string, savedVersion}`.
- `POST /api/v1/companies/{id}/refresh`: `{expectedVersion}`; refreshes at most
  three known Homeportal project cards and one ADATA registration date by BIN.
  Returns the updated profile, including partial failure state.

Opening a page reads saved state only. External reads require explicit search,
preview, save or refresh. Public reads share the existing registry quota of
100 operations per UTC day, including failed attempts. A project operation can
read detail + bounded first catalog page (two HTTP requests); save additionally
looks up at most two unique company BINs. A refresh reads at most three projects
in parallel plus one company page. No portfolio crawler/background task,
SearchAPI, Gemini, geocoder, arbitrary URL fetch or browser scraping is used.
HTTP reader: no redirects, 2 MB decoded body, 15s streaming deadline,
10s read / 3s connect timeout. Stored snapshots are the durable read cache.

## Identity, facts, source semantics

`CompanyRecord`: `id=bin-{12 digits}`, `bin`, `name`, `demo:false`, `facts[]`,
`projects[]`, `version`, `updatedAt`, `lastAttemptAt`, `lastError`.
`lastError` is a safe code, never a provider body. A failed refresh keeps old
facts and their original source dates. `updatedAt` is the last successful partial
collection, not the source's own data timestamp. `lastAttemptAt` includes failures.
Different values remain separate, source-attributed observations.

`CompanyFact`: `field`, `value`, `source`, `status:source_reported`.
Fields: name/bin/registrationDate/status/legalAddress/website. Currently name,
BIN and optional website are from Homeportal; registrationDate (ISO date) from
ADATA with exact BIN match. Status/legalAddress remain unknown without a source.

`source`: `{publisher, url, retrievedAt, effectiveDate:null|string,
responseSha256}`. URL points to the actual public card. It is not an archived
permalink; retrieval time does not promise reproduction of historical content.
The response SHA permits comparison, not reconstruction of a document.
Registration date is a fact value, not the date of source freshness.

`SourceProject`: `recordId`, name/address/city, `parties[]`, `source`,
`stage:null|under_construction|commissioned`, `stageSource`,
`coordinates:null|{latitude,longitude}`, `coordinateStatus`,
`commissioningReference`, `commissioningDate`, `documentSha256`.
Each party has `{bin,name,website:null|string,role}`. Roles are
`developer|authorized_company`; one BIN can occupy both. Different BINs are never
merged by name. Counts cover saved source cards only, with duplicate act/date/
normalised-address references removed, and do not certify a whole portfolio.

## Compatibility and failures

Existing `developerId`/`Developer` and seed unchanged. Complex detail adds nullable
`authorizedCompany`, `authorizedCompanyId`, `partySnapshots[]` with project-specific
names/roles/source, `participantSource`, `coordinateSource`, `coordinateStatus`.
Coordinates retain their old optional shape for map A. No coordinate is inferred
from a sales office or a city centre. A coarse city envelope rejects obvious
misplacements; source-point accuracy is not cadastral verification.

Real registry creation additionally requires server `DEMO_ONLY=false`, a known
source developer and stage. It creates a separate `homeportal-{id}` complex with
unknown legal basis, zero confirmed factors and source-attributed coordinates.
It refuses to overwrite an existing complex or mix real/demo company identities.
Profile saves alone are allowed separately from the fictional registry.

409: stale version, changed source fingerprint, existing registry card or bounded
record-history capacity; refresh preview/reload and review again. 403: real
registry creation disallowed in demo scope. 422: source/card identity or required
project facts invalid. 503: bounded source read/schema failure. Optional ADATA
failure does not discard usable Homeportal information; previous registration
facts remain, with `lastError`. No missing source becomes R1 or a legal approval.

Persistence: `companies`, `companyProjects`, existing `developers`, `complexes`
and `auditLogs`. Company/profile/project/optional registry creation is atomic;
all network calls complete outside retried Firestore transactions. Existing
client-deny rules, audit and registry-screening endpoints remain intact.
