# SAQ QURYLYS — Project specification

**Version:** 1.0 | **Hackathon:** Codemasters 8.0 (14–21 October 2026) | **Region:** East Kazakhstan Region (ВКО)

**Status key:** `REQUIRED` = source hackathon case; `TEAM DECISION` = agreed implementation choice; `OPTIONAL` = enhancement, not a replacement for mandatory MVP.

## 1. Problem, users and boundaries

**Problem (REQUIRED).** Advertisements for apartments in partially built residential complexes can solicit payments before the legal basis has been checked. Information about objects, documents, advertisements and complaints is fragmented. A regional analyst needs a consolidated record and explainable prioritisation.

**User (REQUIRED).** Analyst at an authorised regional/municipal unit in East Kazakhstan Region. The system assists a human; it neither proves a violation nor sends findings to a governmental agency automatically.

**Outcome (REQUIRED).** A locally runnable web app that works with demonstration data and produces a traceable signal record which can be confirmed/returned by an analyst and exported to PDF/print.

**Territory (TEAM DECISION).** Scope all records, search, map and statistics to modern administrative borders of **East Kazakhstan Region**. Do not assume Semey/Abai Region is part of VКО. Use invented housing complexes in Ust-Kamenogorsk, Ridder and other VКО settlements.

**Data limitations.** Organisers will not give closed registries or state API credentials. The app must provide its own **internal** housing-complex database built from marked demo/seed data, manual documents and optional lawful public-source imports. No interface should misleadingly label fictional permit records as confirmed government data.

**Additional sources, 15 Oct (user-supplied hackathon chat context).** Public links
including Homeportal, E-License, Qazreestr and an Ashyq Data dataset are catalogued
in [public-sources.md](public-sources.md). They support optional manual verification;
they do not imply a working API, complete dataset or a change to R1–R6. The original
six-page PDF was reread and its mandatory scenarios remain consistent with this spec.

**Open source vs access.** For code assessment the repository must be publicly accessible by the deadline; the **running application** is login-protected and not publicly deployed by default. Judges may run the client and FastAPI locally with internet connectivity. Firebase (hosted DB/auth/storage) and Gemini API are remote. Local ML/LLM is not required.

## Owner workflow update · 20 October (TEAM DECISION)

New implementation queue: one Advertising section with All materials and Sources
and schedule; automatic analysis of supported new revisions; grouped duplicate
publications preserving originals; one-page human review/one save. Separate
preliminary review priority from confirmed R1–R6 score. This supersedes the old
multi-step UI, not the hard scoring/evidence rules. Automatic analysis does not
confirm legal findings or fabricate matches/permissions. Unsupported media and
quota queues are explicit. Construction progress visuals/columns remain removed.
[Implementation split](tasks/unified-advertising-split.md),
[target contract](material-workflow-contract.md). These changes are planned,
not yet implemented or deployed.

## 2. Mandatory end-to-end journey (REQUIRED)

**Product scope update requested by owner, 17 October (TEAM DECISION):** complete
the intake with automatic public-source monitoring, revision/deduplication and an
expert queue. Manual entry remains a fallback. Investigate Instagram targeted ads
first; supported-source coverage and access restrictions must be explicit. This
extends the implementation scope; it does not invent an organiser-provided API.
See [current plan](DEVELOPMENT_PLAN.md) and [Instagram access findings](instagram-feasibility.md).

1. **Overview:** analyst searches and filters a list/map of local residential complexes by risk zone and opens an object.
2. **Object check:** object card displays developer/BIN, address, coordinates when available, construction status/completion, claimed or verified funding basis and source/status of verification.
3. **Advertisement:** analyst adds or reviews a social media publication with URL, platform, account, date, text/screenshot; publication is linked to an object. AI highlights an excerpt that *may* solicit funds.
4. **Risk:** system computes score solely from verified factors, shows each weight and underlying evidence, and correctly handles unknown status.
5. **Decision:** analyst confirms a signal or returns it for clarification; the system records actor/time/status and exports a traceable PDF or printable card.

> A *working connected flow* is more important than many disconnected demo pages.

## 3. Minimum delivery scope (REQUIRED)

| Module | Required features | Acceptance |
| --- | --- | --- |
| Overview/map | ЖК list, risk badge/score, zone filter, direct object navigation; map pins if geo provided | Filters work on backend data; list usable without map tiles |
| Internal registry | Name, address, developer and BIN, phase/readiness, legal basis, verification source and status, linked ads/events | Data persists in Firestore; missing data is explicit |
| Advertisement monitoring | Publication feed with source URL/account/platform/date/text/image; manual add or accessible-source import; assign to ЖК; highlight potentially paid booking | Add a previously unseen text/screenshot at demo time |
| Risk scoring | R1–R6, status per factor, score, zone, evidence drill-down | All three specified scoring scenarios pass |
| Signal card | Object summary, score/factors, evidence references, review status; Confirm/Return; PDF/print | Decisions persist with actor/time; report loads and exports |

**Required demo data:** at least **8 complete fake ЖК cards**, **12 ad publications** and three contrasting case scenarios A/B/C. All synthetic data is marked `demo: true` and clearly labeled in UI.

## 4. Risk factors and legal caution (REQUIRED)

| Code | Weight | Condition for *confirmed* factor |
| --- | ---: | --- |
| R1 | 35 | Documented/verified absence of an **applicable** lawful basis for fundraising; lack of access/data does **not** establish absence |
| R2 | 25 | Original ad text/image provides direct payment invitation: paid reservation, deposit, initial payment or analogous scheme |
| R3 | 10 | Confirmed active advertising of uncommissioned housing |
| R4 | 15 | Verified collective complaint alleging fundraising connected to the project |
| R5 | 10 | Claimed vs verified construction readiness differs by **at least 20 percentage points**, with sources and dates for both figures |
| R6 | 5 | Documented significant stoppage or missed timeline |

`score = min(100, Σ weight of factors whose status == CONFIRMED)`.

- GREEN: score 0–24.
- RED: score >= 60 **and** R1 + R2 are both confirmed.
- YELLOW: everything else (including 60+ with no simultaneous R1+R2).
- Unknown or merely AI-proposed factors count **0**.
- A guarantee from the legally relevant operator can serve as an applicable lawful basis; a missing separate regional permit is not automatically R1.
- Model weights can be discussed later, but the **baseline algorithm and three required scenarios must remain reproducible**.

### Mandatory scenarios

- **Scenario A:** legal basis **not checked**, confirmed paid booking and active advertising → R2 + R3 = **35, YELLOW**. R1 remains UNKNOWN.
- **Scenario B:** proven lack of applicable legal basis, deposit offer and active advertising → R1 + R2 + R3 = **70, RED**. Human confirmation of the signal remains necessary.
- **Scenario C:** confirmed applicable guarantee and ordinary active advertising → R3 = **10, GREEN**. Missing separate MИО permit does not create R1.

**Scoring invariants:** A rejected factor never scores. Editing a verified factor triggers recomputation on backend. Identical confirmed facts always yield identical results. Include unit tests for score=60+ without both R1/R2 → YELLOW; missing source → cannot confirm R1; empty factors → GREEN.

## 5. Data model (TEAM DECISION, Firebase Firestore)

Recommended canonical collections:

```text
developers/{developerId}
complexes/{complexId}
advertisements/{adId}
evidence/{evidenceId}
riskFactors/{factorRecordId}
signals/{signalId}
investigations/{investigationId}       # optional enhancement
adLinks/{linkId}                      # optional enhancement
droneInspections/{inspectionId}       # optional enhancement
auditLogs/{logId}
users/{uid}
```

**Developer:** name, fictional BIN, optional public business details, `demo`.

**Complex:** unique ID, name, city, region `ВКО`, postal address, optional coordinates, developer reference, stage, stated/readiness-verified percentages, evidence/source dates, basis type (`guarantee | regional_permit | other_applicable | unknown`), basis status (`confirmed | disproved | unknown`), reference details, linked ads, derived risk score and zone, `demo`.

**Advertisement:** source platform/account/URL, published/captured time, text, optional private Storage path of screenshot/media, structured extracted indicators, complex linkage status (`proposed | confirmed | rejected`), analysis version/result, `demo`.

**Evidence:** object/ad references, original source URL, excerpt, capture timestamp, file Storage path, cryptographic hash if captured, evidence type, validation/reviewer status/actor/time.

**Risk factor record:** `complexId`, `code`, `status` (`unknown | proposed | confirmed | rejected`), `evidenceIds`, reviewer/time and source notes. Weight always comes from backend constant, not editable Firestore document.

**Signal:** `complexId`, score/factors snapshot, evidence IDs, state (`draft | pending_review | confirmed | returned`), creator, timestamps, reviewer, note/return reason, generated report path.

**Audit log:** entity, event, actor UID, date/time, before/after status (no secrets). Prefer UTC in storage and display local Kazakhstan time on UI.

**Access-control principle:** JWT/ID tokens from Firebase Auth verified by FastAPI. Server-side Firebase Admin accesses Firestore/Storage under well-defined role checks. Client SDK read/write operations should be restricted by security rules; never trust `role` or `verified=true` from frontend requests. Provide concise index definitions as queries become concrete.

## 6. Architecture and APIs (TEAM DECISION)

```text
React + Vite + TypeScript (local browser app)
  -> HTTPS/localhost HTTP to FastAPI REST backend (local process)
     -> Firebase Authentication token verification
     -> Firestore (remote data / evidence metadata)
     -> Firebase Storage (private screenshots, PDF, drone images)
     -> Gemini API (remote extraction and image analysis)
```

Suggested endpoints (freeze schemas early):

```text
GET    /api/v1/health
GET    /api/v1/complexes?q=&city=&zone=&cursor=
GET    /api/v1/complexes/{id}
POST   /api/v1/complexes
GET    /api/v1/complexes/{id}/advertisements
POST   /api/v1/advertisements
POST   /api/v1/advertisements/{id}/attachments
POST   /api/v1/advertisements/{id}/analyze
POST   /api/v1/ai-hypotheses/{id}/decision
GET    /api/v1/complexes/{id}/risk
POST   /api/v1/signals
POST   /api/v1/signals/{id}/decision
GET    /api/v1/signals/{id}/pdf
```

Shared JSON objects should have stable typed contracts. Use `GET /health` without authentication but protect all business endpoints. Use consistent typed errors `{code,message,requestId,details?}`. Pagination and bounded uploads are required. Data validation must prevent writing to outside-VКО objects by accident.

**Run requirements:** clone repo; get required demo connection parameters **privately**; configure `.env` (not in Git); `docker compose up --build`; open specified localhost UI; sign in; perform mandatory scenarios. Docker must not need to run Firebase emulator or local LLM. Supply a non-Docker path as a fallback if feasible. Provide seeded demo data and idempotent setup. The environment requires Internet, and external API outages must be handled without silent fake responses.

## 7. AI module (REQUIRED)

At least one meaningful **real** AI use case operates on a **new input**, not a canned demonstration:

1. Input: text or screenshot (possibly Kazakh or Russian) of a real-looking **fictional** advertisement.
2. Gemini multimodal API extracts structured candidate fields: name aliases, ad platform, contact, amounts and terms, construction references, possible paid reservation/deposit, quoted text spans, confidence/uncertainty and candidate complex matches.
3. Validate output schema server-side. Preserve the exact evidence excerpt, source and timestamp; do not invent unreadable text or documents.
4. Present AI suggestions to analyst as `PROPOSED`; analyst chooses accept/reject and can override incorrect matches.
5. Only `CONFIRMED` factors backed by evidence change scoring. Record AI provider/model and analysis timestamp, without storing secrets or unnecessary raw sensitive input in logs.

For screenshots, multimodal Gemini can replace local OCR for MVP; still inspect failure cases (low contrast, partial frames, multilingual variants). Model is configurable (`GEMINI_MODEL`), not baked into API contracts. AI can be temporarily unavailable, and a user must still be able to view/edit existing records manually.

## 8. UX structure (REQUIRED)

Left navigation: **Overview**, **ЖК registry**, **Advertisements**, **Signals**, plus **Investigations** (P1) and **Drone inspections** (P2) only if implemented. Top bar: search, region ВКО, signed-in analyst, logout.

**Complex details tabs:**
- `Overview` — name, city/address, developer/BIN, construction/readiness and evidence provenance.
- `Advertisements` — list with original source, screenshot preview, highlighted payment language, add/import action.
- `Documents` — guarantee/permit type, number/date, verification status, source file/date; unknown is visible.
- `Evidence` — evidence artifacts, provenance, linked factor, human review state.
- `History` — analyst decisions, edits and score changes in a chronological audit list.

Keep risk strip/panel visible on desktop: score, color zone, R1–R6 with drill-down to linked evidence; never present AI hypothesis as a verified legal fact. Confirming/rejecting AI suggestions and confirming/returning a **signal** are **two distinct workflow steps**.

**PDF signal report:** object/fictional developer details, factors/scores, source references, capture dates, verified vs AI-only status, reviewer and decision, disclaimer that this is a preliminary risk signal, distinct DEMO watermark for synthetic data.

## 9. Original differentiator — «Рекламный след» (OPTIONAL P1)

Trace an *advertising campaign* across multiple accounts rather than treating every ad as an isolated item. Normalize +7/8 phone variants, shared WhatsApp URLs/domains, visual perceptual-hash similarity and textual similarities. Display a concise graph/list of links, explanation for each link and reviewer decision. Connections are investigatory hypotheses; they do not imply common ownership or automatically add R1–R6 points. A basic demonstration: two different fictional ad accounts sharing a normalized phone number → proposed link → analyst accepts/rejects.

A useful second enhancement is temporal comparison: detect differences between saved versions of a publication (booking amount, contact number, wording) while keeping original capture snapshots.

## 10. Drone-image inspections (OPTIONAL P2)

An uploaded drone image or frame may be analyzed through Gemini against a **configurable checklist**, pending exact criteria from organisers (examples only: construction fence, waste container, safety signs). Each item can be `visible | not_visible | uncertain` with explanation and reviewer confirmation. **Not visible in photo does not establish absence on site.** Preserve original file and metadata. Produce an *inspection result separate from legal ad-risk scoring*. Do not build autonomous drone control for the hackathon.

## 11. Security, provenance and trust (REQUIRED)

- Test data must have `demo: true`; no fabricated charges against identifiable real companies. Do not publish the internal app or real files openly.
- Use separate Firebase demo environment and least-privileged accounts. Authenticate all business operations, restrict file reads and writes, size-limit uploads, validate MIME/actual content, prevent path traversal and unsafe URL fetch/SSRF. No arbitrary URL fetching from internal/private networks.
- Gemini and Firebase Admin credentials are backend-only and excluded from Git and logs. `.env.example` contains placeholder variable names only. `firebaseConfig` web values are not admin secrets, but client-side access still needs secure Firebase Rules.
- Store provider/source, fetch/upload date and original proof material where permitted; evidence hashes improve reproducibility but do not guarantee authenticity.
- Journal review actions with actor/time. Never make LLM legal conclusions.
- External platform collection must follow API/rate-limit/terms. **Do not promise complete targeted-ad coverage** or scrape closed/private accounts without authorisation.

## 12. Verification, scoring and submission (REQUIRED)

### Automated and manual tests

- Tests for A/B/C, 60+ without R1+R2, missing documentation, rejected AI hypothesis, score recomputation, signal reviewer/time and API authentication.
- Test a **previously unseen** ad in Russian and at least one Kazakh sample; record true/false positives and limitations.
- Validate clone → `.env` → Docker Compose → login → scenario A/B/C → new ad → AI hypothesis → human decision → PDF on a clean second machine.
- Document outages: bad Gemini key, Firestore unavailable, missing source and upload error.

### GitHub deliverable

Public repo with actual source, runnable `README.md`, `.env.example` with **no secrets**, seed/setup scripts, architecture/risk/AI documents, meaningful automated tests and documented use of AI-assisted programming. Team must be able to explain code. Case advises GitHub code-review cutoff **20 October 2026, 23:59**, but confirm exact deadline with organisers. Provide stable submission commit SHA/tag.

### Official evaluation (100 points)

| Criterion | Points |
| --- | ---: |
| Working MVP and connected workflow | 25 |
| AI, data integrity, explainability | 20 |
| Code quality and GitHub | 20 |
| Analyst UI/UX | 10 |
| Problem understanding and presentation | 20 |
| Initiative/originality | 5 |

**Core demo storyboard:** a previously unknown ad → link to a fictional ЖК → AI proposes payment factor with exact quote → analyst verifies → backend deterministic score updates → report confirmation/return and PDF export; show ad-link investigation only if reliable and finished.

## 13. Out-of-scope and open decisions

**Out of scope for MVP:** integration with real confidential state registries, nationwide scope, automatic legal judgement, automated official reporting, full live capture of all Instagram/Facebook/TikTok targeted ads, local AI model, direct drone piloting.

**Open decisions:** organisers' precise code cutoff and access credentials delivery; exact drone compliance checklist; available Gemini budget/quotas; whether demo env is one judge per isolated namespace or separate project; final API route naming. Record decisions in `docs/DEVELOPMENT_PLAN.md` or an ADR.

---
**Source of requirements:** user-supplied `Кейс Codemasters 8.0. SAQ (1).pdf`, 6 pages, sections 1–11. This specification is a team implementation brief; not a replacement for the original case.
