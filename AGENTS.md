# SAQ QURYLYS — instructions for Codex and contributors

This file is the repository-level operating guide. Read it **before** editing code. Detailed product requirements are in [`docs/PROJECT_SPEC.md`](docs/PROJECT_SPEC.md); task ordering and Git workflow are in [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md). If an instruction conflicts with the source hackathon case, prefer the case and raise the conflict explicitly instead of silently changing requirements.

## Product and scope

- Build **SAQ QURYLYS**, an internal web application for analysts in **East Kazakhstan Region (Восточно-Казахстанская область, ВКО)**. It detects and prioritizes *potential* risks in advertisements for apartments in residential complexes under construction.
- It is a **decision-support tool**, **not** a court, regulator, or automated finding of illegality. No automated transmission of signals to real authorities.
- Hackathon: Codemasters 8.0, 14–21 October 2026. Submission includes **public GitHub source** and instructions to run locally. The application itself is access-controlled and can connect over the Internet to external APIs.
- No access to closed government registries. The mandatory internal registry is made of **clearly labeled synthetic DEMO records** and optional manually entered documentary evidence. Do not fabricate a live registry integration.

## Two-person ownership

**Owner update, 20 October — current unified advertising assignment:**
A (second Codex) owns **all frontend** for [Issue #30](https://github.com/arturk0-0/3a-saq-qurylys/issues/30):
unified Advertising, two tabs, one review page, priority presentation, spacing and QA.
B (this Codex) owns backend/contracts/auto-analysis/dedup/priority/atomic review and
integration for [Issue #29](https://github.com/arturk0-0/3a-saq-qurylys/issues/29).
Read [the new scope/sequence](docs/tasks/unified-advertising-split.md) and
[target API v1](docs/material-workflow-contract.md); these endpoints are planned,
not implemented. B must not concurrently edit frontend owned by A.
This overrides the historical MON/MAP/ORG frontend exceptions below. A needs no
cloud accounts, keys, paid calls or deployment. Preserve PR #25–28 and their fixes.
Confirmed R1–R6 stays deterministic/human-reviewed; preliminary priority is separate.

**Historical owner update, 19 October — MAP/ORG assignment:** A (friend) owns the
secondary city-map feature and minimal ComplexList mount, [Issue #20](https://github.com/arturk0-0/3a-saq-qurylys/issues/20).
B (owner) owns public-source company data, backend/contracts, company pages,
ComplexDetail and routes, [Issue #21](https://github.com/arturk0-0/3a-saq-qurylys/issues/21).
This explicitly overrides blanket frontend ownership below for company pages.
Use [the scoped file boundaries and prompts](docs/tasks/map-company-split.md).
Keep Leaflet/OSM: identical stylized volumetric building markers, no progress
visualisation and no new map platform. The map is a collapsible secondary block.
A requires no cloud accounts, API keys, paid calls or manual owner setup.
These are authorised future implementation tasks; this planning change does not
claim implementation. Completed A-01–04 must not be repeated.


Historical owner update, 17 October: automatic public-ad monitoring was the immediate P0.
The 19 October assignment above defines the current MAP/ORG queue.
For the MON vertical slice the owner explicitly authorizes B to implement both
backend and necessary frontend without waiting for A. This overrides the file
ownership split for MON only. Instagram targeted ads have first priority for
access/coverage investigation; never substitute ordinary post search for ad data.
See `docs/instagram-feasibility.md` and the current development plan.

The team has **two** contributors; current queues and copy/paste prompts are in
[`docs/two-person-team.md`](docs/two-person-team.md), assignments in
[`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md). GitHub queues:
[A / second Codex #30](https://github.com/arturk0-0/3a-saq-qurylys/issues/30),
[B / this Codex #29](https://github.com/arturk0-0/3a-saq-qurylys/issues/29).

- **A = the owner's friend and their Codex:** owns all `frontend/**` and the
  user/demo documents listed in the team guide. Develop/test using the existing
  isolated QA adapters. No Firebase/Google Cloud login, production credentials,
  paid AI calls or deployment is required for this queue.
- **B = the repository owner and their Codex:** owns backend, AI/risk, persistence,
  security, infrastructure, shared contracts and release. The former C role is
  merged into B. B integrates/reviews frontend PRs; avoid parallel frontend edits.
- Follow the role given in the user's prompt; do not ask again when it is known.
  Before taking work inspect remote branches/open PRs and the current role queue.
  A records hand-off in `docs/frontend-handoff.md`; B consolidates `WORK_LOG.md`
  and the shared plan, avoiding simultaneous edits of those files.
- Do not recreate existing features from unchecked acceptance boxes. The team
  guide lists pending PRs and how to choose a base without losing newer work.
  API/schema changes are coordinated between A (consumer) and B (server/AI).

## Locked technology choices

- Web: **React + TypeScript + Vite**, **Tailwind CSS + shadcn/ui**.
- API: **Python + FastAPI + Pydantic**, with clear routers, services, and repositories.
- Persistence: **Firebase Firestore**. Identity: **Firebase Authentication**. Files: **Firebase Storage**.
- AI: **Google Gemini API**, called **only by the backend**, model selected using `GEMINI_MODEL` (do not assume availability of a particular version).
- Map: **Leaflet + OpenStreetMap**. PDF: server-side **WeasyPrint**, subject to runtime/system dependencies; document setup clearly.
- Local runtime: **Docker Compose** for frontend/backend; online Firebase and Gemini allowed and expected.
- Tests: **pytest** for Python/risk logic; **Vitest** and frontend type checking/build; **GitHub Actions** CI.

Do not introduce Supabase, Next.js, Ollama/local LLMs, a second database, or a large new framework unless the team explicitly approves a documented architectural decision.

## Development priorities

1. First deliver a **working end-to-end vertical slice**: create/import a DEMO advertisement → run AI on a *new* text or screenshot → show supported excerpt and an **unconfirmed AI hypothesis** → human confirms/rejects → deterministic risk score changes → create signal → human confirms/returns → printable/PDF export.
2. The five mandatory modules: overview/map, ЖК registry, ad monitoring, explainable scoring, signal card.
3. Minimum seed: **8 complete fictional residential complexes, 12 fictional advertisement records, 3 distinct required scenarios A/B/C**.
4. Only after the mandatory flow works: the signature feature **«Рекламный след»** (links among ads/accounts/phones/images). Drone photo inspection is **optional, separate**, and must not modify the legal risk score.

## Hard scoring rules — DO NOT IMPROVISE

| Factor | Confirmed condition | Points |
| --- | --- | ---: |
| R1 | Verified absence of an applicable legal basis to attract funds | 35 |
| R2 | Evidence of direct offer to pay booking fee, deposit, down payment, etc. | 25 |
| R3 | Verified active advertising of housing still under construction | 10 |
| R4 | Verified collective complaint alleging fundraising for the project | 15 |
| R5 | Documented >=20 percentage-point gap between claimed and verified completion percentages with dates/sources | 10 |
| R6 | Documented meaningful work stoppage or delay | 5 |

`score = min(100, sum(points of confirmed factors))`.

- `UNKNOWN`, `PROPOSED`, `REJECTED` **do not contribute** to the score; AI output by itself is **never** confirmation.
- `GREEN`: 0–24. `RED`: score >= 60 **and BOTH R1 and R2 confirmed**. `YELLOW`: all other scores (including 60+ without the R1+R2 combination).
- No lookup result / missing registry / unknown documentation **must never be converted into R1**.
- A currently valid applicable guarantee may be a legal basis; missing a separate local permit alone is not R1.
- Core tests: A = R2+R3 = 35 YELLOW; B = R1+R2+R3 = 70 RED; C = valid guarantee + R3 only = 10 GREEN.
- Keep scoring in one pure tested backend function, not calculated independently in UI, prompts, or PDF templates. Persist an explicit evidence link and reviewer for each confirmed factor.

## AI, evidence and analyst control

- Use AI to extract *hypotheses*, matching candidates, quotes/excerpts, values, identifiers, uncertainty and (if available) an indicative confidence. Validate Gemini JSON with Pydantic before saving.
- Never let an LLM automatically approve evidence, legal findings, or change confirmed score factors. A human must explicitly confirm or reject a proposed factor.
- Keep original source URL, platform, account, published/capture times, screenshot/file references, text excerpt, reviewer, verification status; compute SHA-256 for uploaded evidence where practical.
- Distinguish **verified fact / AI hypothesis / missing information / fictional DEMO example** in data and interface.
- Store exact user-supplied file/URL evidence faithfully. Avoid ambiguous ad-to-complex matches; request reviewer selection when uncertain.

## Security and quality

- Never commit `.env`, Gemini secrets, Firebase Admin service account JSON/private keys, tokens, local databases, private personal data or real allegation dossiers. Use `.env.example` with empty/placeholder values.
- `firebaseConfig` (browser configuration) is not the Admin private credential. Backend uses Firebase Admin credentials privately, validates Firebase ID tokens and enforces role/permissions on every protected endpoint.
- Require authentication for work surfaces; consider Firestore/Storage rules **deny by default** to clients when all access is mediated by FastAPI. Use private storage objects, limits on upload size/types and signed/controlled download mechanisms.
- Prefer least-privilege accounts, separate DEMO environment, safeguards against overwriting analyst activity in `seed` scripts, safe error handling, rate limits/quotas for external AI.
- No synthetic accusations against identifiable real developers: fictional names, fictional BINs and visible DEMO labels.
- New code must include appropriate typing, validation, error paths, logging without secrets, unit tests, and minimal README updates.
- Avoid large refactors or unrelated code edits. Keep modules small and readable; explain any deliberate deviations.

## Expected source layout

```text
frontend/src/{app,components,features,lib}
backend/app/{api,core,models,schemas,repositories,services}
backend/tests/
data/seed/
docs/{PROJECT_SPEC.md,DEVELOPMENT_PLAN.md,architecture.md,data-model.md,risk-rules.md,ai-methodology.md,demo-scenarios.md}
scripts/
compose.yaml
.env.example
README.md
AGENTS.md
```

This is a target layout, not a reason to generate unused placeholder files. Add modules when real code exists.

## Git/GitHub rules

- `main` must always build and run. Work on focused branches (`feat/FE-04-complex-card`, `fix/RISK-02-zone`, `docs/...`); no direct push or force push to `main`.
- Commit coherent changes, open PRs, ask another teammate for review, require passing CI before squash merge. Update task checkbox and PR link in team plan after merging.
- Before writing code: inspect current repository, read affected interfaces and task spec, propose a brief implementation plan. If the task has ambiguities impacting legality/data security/API compatibility, ask rather than guess.
- Before marking work done: run relevant tests/lint/build; report what changed, how to test, known limitations and PR/commit reference. **Do not claim tests passed if they were not run.**
- API contracts, database shapes and R1–R6 rules need agreement between A (frontend) and B (backend/AI) before they are changed.

## Practical first milestone

Set up repository skeleton, frontend and backend health check, `/api/v1` structure, config validation, Docker Compose and README startup. Then implement demo seed and the scoring engine/tests. Only afterwards implement AI and workflow UI.
