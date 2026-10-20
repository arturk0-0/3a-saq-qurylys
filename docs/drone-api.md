# Drone inspections API

All routes below require the existing analyst/admin Auth. No public file URLs or
new secrets. Server uses existing `GEMINI_MODEL`, `GEMINI_API_KEY` and Firebase
Storage configuration. No source URL fetching or automatic/background AI.

## Workflow and routes

1. `GET /api/v1/drone-inspections/checklist` — starter examples, not approved law.
2. `POST /api/v1/drone-inspections`:
   `{requestId:UUID,title,complexId:null|id,capturedAt:null|ISO-with-zone,checklist}`.
   Checklist 1–8 `{id,label,sourceUrl:null|http(s)}`; IDs unique, capture time not
   future, URLs without credentials. Source references are user-supplied and
   neither fetched nor certified. Creates a metadata card; does not call AI.
3. `POST /api/v1/drone-inspections/{id}/photo?expected_version=N`: raw image body
   + Content-Type image/jpeg|image/png|image/webp. Static, max **6 MiB / 20 MP**,
   decoded before storage, originals preserved. One immutable photo per card.
4. `POST /api/v1/drone-inspections/{id}/analyze`:
   `{requestId:UUID,expectedVersion}` — explicit Gemini call. Schema validates
   every checklist ID exactly once, visible/not_visible/uncertain, explanation,
   summary and limitations. Unknown/extra fields and incomplete output rejected.
5. `POST /api/v1/drone-inspections/{id}/review`:
   `{expectedVersion,runId,decision:accepted|needs_followup|rejected,notes}`.
   Current succeeded run only. Accepted means observations considered; no formal
   finding of compliance or violation. Review history persists across reanalysis.

Read endpoints:

- `GET /api/v1/drone-inspections?limit=20&cursor=...`: workspace-scoped newest-first
  list. `items`, `nextCursor`; ordered createdAt DESC / document-ID ASC.
- `GET /api/v1/drone-inspections/{id}`: card, `latestRun`, `canAnalyze`.
- `GET /api/v1/drone-inspections/{id}/photo`: protected original, SHA/size checked,
  no-store / nosniff / attachment. Storage path is omitted from card JSON.
- `GET /api/v1/drone-inspections/{id}/runs?limit=20&cursor=...`: scoped through the
  parent card, stable newest-first analysis history with frozen checklist/photo SHA.

## Persistence, versions and isolation

New `droneInspections` and `droneRuns`; existing `auditLogs` and shared
`usageLimits`. `workspaceScope=demo|live` follows server registry scope, including
unlinked cards. Linked complex is checked on every protected operation. A photo
without a known complex can stay unlinked; no automatic matching to fictional
DEMO records. No writes to complexes, evidence, factors, legal basis or signals.

Metadata create is idempotent for the same UUID/payload/actor. Upload increments
card version. Analysis reserves run + shared daily global/user quota + card
version atomically before storage download/Gemini; provider failures count as
attempts. Replayed succeeded request returns saved state; running/failed request
UUID never triggers another model call. At most 20 analyses and 20 reviews/card.
Existing shared Gemini adapter retains one retry only for explicit 502/503/504,
no retry of ambiguous timeouts, no model fallback and safe error codes.

A running attempt older than five minutes can be replaced by a **new explicit**
analysis request. The old run becomes failed/DRONE_INTERRUPTED. Completion checks
latestRunId + saved running status, so late old output cannot replace a new run.
Review uses card version + current succeeded run ID. Old review records stay
visible as previous-analysis decisions, not approval of the new result.

Private objects: `drone-inspections/{scope}/{inspectionId}/{randomPhotoId}`.
Definite pre-write upload rejection cleans only that attempt's unique object.
Uncertain Firestore commit retains it; never delete a possibly referenced photo.
Reconcile private orphan objects administratively if necessary. Existing deny-all
Firestore/Storage client rules remain intact; no public/signed URL is created.

## Errors and rollout

409 stale version/UUID reuse/current-run mismatch; reload saved state. DRONE_BUSY
means an existing running analysis; no automatic repeat. DRONE_PHOTO_REQUIRED
means upload first. DRONE_INVALID_RESPONSE means no observations accepted; the
original stays. DRONE_LIMIT bounds card history. Existing AI quota/config/model/
network/provider errors and FILE_SIZE/INVALID_IMAGE/FILE_INTEGRITY remain safe.

Two declared indexes cover list/history: workspaceScope + createdAt DESC/name ASC
and inspectionId + createdAt DESC/name ASC. They require the usual later index
release and READY state. No index deployment occurs during development.

Local verification: [QA runner](../frontend/qa/drone/README.md),
[actual results/limits](drone-inspection-report.md). Cloud acceptance later:
Auth and both scopes; private bucket permissions for the new prefix; original
integrity; real approved drone photo; configured model's checklist output;
review/history after refresh; required indexes READY. Do not mistake local
MockTransport/emulator tests for cloud or real-image model validation.
