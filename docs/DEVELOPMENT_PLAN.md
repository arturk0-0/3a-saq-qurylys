# SAQ QURYLYS — development plan and team checklist

**Sprint:** 14–21 October 2026 | **Code review cutoff in case (recommended):** 20 October, 23:59 (confirm with organisers) | **Scope:** East Kazakhstan Region, demonstration data only.

> Checkboxes are editable Markdown tasks, compatible with GitHub preview and Codex. After completing one, change `[ ]` to `[x]`, add a PR or commit link in the corresponding GitHub issue, and obtain a second person's review. Do not mark mockups, stubs or hardcoded model responses as working functionality.

## 0. People, links and responsibilities

| Role | Member | Primary ownership | Reviews |
| --- | --- | --- | --- |
| **A — Frontend & product** | **[fill name]** | UI/UX, navigation, forms, client integration, demo/pitch | C's AI UX, B's API clarity |
| **B — Backend & infrastructure** | **[fill name]** | FastAPI, Firebase, Auth, Storage, CI, Docker, PDF, security | A's integration |
| **C — AI & risk** | **[fill name]** | Gemini, parsing ads/images, matching, scoring/tests, seed | B's backend rules |

- **GitHub:** https://github.com/arturk0-0/3a-saq-qurylys
- **Firebase project ID:** `saq-qurylys` | Console: https://console.firebase.google.com/u/0/project/saq-qurylys/overview
- **Team Google Doc:** https://docs.google.com/document/d/1eYBn-ltrjPkazSOaTd_clNj0nd6jjZ-CabE2-lNsr8E/edit
- **Figma (optional):** [add link]
- **Team communication:** [add link]
- **Repo visibility:** private during team work; **public before the organiser cutoff**. The running product stays auth-protected.

**Task labels:** P0 essential, P1 after mandatory flow, P2 bonus. Keep one assignee per task even if two people help. Daily sync: completed / today's task / blocker; do not hide blockers until the end of a day.

## 1. Plan by day / milestones

### Implementation hand-off · 15 October

Before taking an unchecked task, read this table and `docs/WORK_LOG.md`, then inspect
remote branches. An unchecked box can mean **awaiting live verification/review**, not
missing code. Do not reimplement these modules from scratch.

| Implementation | Branch / merged commit | Remaining verification |
| --- | --- | --- |
| FE-01–03, FE-05–11; BE-01–12; RISK-01–04; AI extraction/review; signal/PDF | `main` at `0f7c23a`, including preceding feature branches | Live Firebase/Gemini, second-person review, second Windows machine |
| QA-01–03, DOC-01–04 | `main` at `0f7c23a` | CI result via GitHub UI; live AI measurements and clean-device run |
| FE-04 map; FE-12 keyboard tabs / fallback checks | `feat/FE-04-complex-map` · Codex | Feature-branch checks and review before merge |
| QA-04 diagnostics; AI-06/08 reproducible evaluation inputs/runner | `feat/QA-04-connection-diagnostics` · Codex; based on map branch | Live credentials and measured responses still missing; merge map first |
| FE-12 form failures, progress-source rejection, overlapping map pins | `fix/FE-12-review-form-recovery` · Codex; based on diagnostics branch | 134 backend / 16 frontend tests; fixture-backed browser flow passed; review still required |
| AI-05 read-only name/alias candidates and human comparison | `feat/AI-05-complex-candidates` · Codex; includes preceding three branches | Review additive aliases/API contract; no automatic relinking; live extraction still unverified |
| AI-06/08 measured live extraction | Not complete | Do not treat mocked output or evaluation inputs as live measurements |
| FE-08 public-source shortcuts and source provenance | `feat/FE-08-public-registry-sources` · Codex; based on AI-05 | Manual links only; registry records/API not validated; see public-sources.md |
| Optional hosted demo: Hosting + Cloud Run | `feat/DEPLOY-01-hosting-cloud-run` · Codex; based on public sources | Blaze confirmed by owner; deployment/IAM/Secret Manager/login require owner's Google authorization |
| Backend error handling, SDK/contention and private uploads | PR #1, #3, #4; included in `release/demo-candidate` | Branch checks passed; independent review, main merge and owner deployment remain |
| Review UX and release browser/organiser package | PR #2 + `test/night-release-readiness` at `8dce105`; included in `release/demo-candidate` | Local Linux/Chromium checks passed; live/Windows and independent review remain |
| Unified candidate + real SDK local integration | `release/demo-candidate`; see `docs/release-candidate-report.md` | Local emulator is QA only; does not prove production indexes/IAM/Storage or Gemini quality |
| LINK-01–05, DRONE tasks, release/publication | Not started | Mandatory live workflow and release gates first |

The implementation table is not a claim that release gates or all task acceptance
criteria have passed. Checkboxes below retain the plan's review/merge requirements.
Owner-reported hosted results: login/DEMO, new-ad Gemini analysis and explicit R2
confirmation changed 10→35. No automated cloud verification is implied. Cloud signal
history/index readiness, PDF, screenshot analysis and second-device checks remain.

| Date | Must be demonstrated by end of day | Main owner |
| --- | --- | --- |
| **14 Oct** | Repo and permissions, agreed contracts, frontend/backend skeleton, dev commands | A+B+C |
| **15 Oct** | Firebase config + initial DEMO collections/seed + ЖК list + pure scoring engine/tests | A+B+C |
| **16 Oct** | Complex/details, advertisement manual add, evidence & documents, Gemini text extraction | A+B+C |
| **17 Oct** | Screenshot analysis, AI hypotheses, reviewer accept/reject, 3 correct score scenarios | A+B+C |
| **18 Oct** | End-to-end flow, signal review/return and PDF, first smoke test on clean machine | A+B+C |
| **19 Oct** | QA / security / CI / docs; only if stable, «Рекламный след» and limited drone bonus | A+B+C |
| **20 Oct** | Verify fresh clone, demo credentials, source/documentation, publish repo, record commit SHA before cutoff | A+B+C |
| **21 Oct** | Live demo/pitch using fixed reviewed version, backup recording | A+B+C |

**Release gates:** G0 skeleton runs; G1 data & scoring; G2 AI new-input flow; G3 analyst signal/PDF; G4 secure reproducible reviewer build. Do not start P2 before G3.

## 2. P0 task checklist — all mandatory modules

### A. Product and frontend

- [ ] **PM-01 · A · 14 Oct:** Confirm organisers' exact submission time, judge test procedure, expected drone criteria and any permitted public data sources.
- [ ] **PM-02 · A · 14 Oct:** Create initial project issues with owner, priority, acceptance criteria and a branch naming scheme.
- [ ] **FE-01 · A · 14–15 Oct:** Set up Vite + React + strict TS, Tailwind, shadcn/ui, React Router, navigation shell and layout.
- [ ] **FE-02 · A · 15 Oct:** Design reusable controls: risk badge, document status, evidence status, loading/error/empty states, confirmations.
- [ ] **FE-03 · A · 15–16 Oct:** Overview dashboard with search, risk-zone filter, sort, quick link to ≥8 demo ЖК.
- [ ] **FE-04 · A · 16 Oct:** Optional geo pins using Leaflet/OSM for complexes with coordinates; list view remains usable if maps fail.
- [ ] **FE-05 · A · 16 Oct:** ЖК detail header: name, address, developer/BIN, stage, readiness, documentary basis and source.
- [ ] **FE-06 · A · 16–17 Oct:** Advertisement feed with platform, account, date, source URL, screenshot and manual-add modal/form.
- [ ] **FE-07 · A · 17 Oct:** Evidence tab; show exact AI-highlighted quote and ability to open full original material.
- [ ] **FE-08 · A · 17 Oct:** Documents tab; basis type, status confirmed/disproved/unknown, reference and last checked time.
- [ ] **FE-09 · A · 17–18 Oct:** Risk panel R1–R6 with scores, review statuses, breakdown and evidence links.
- [ ] **FE-10 · A · 18 Oct:** AI proposal review: accept/reject separately from signal decision; show fresh computed score.
- [ ] **FE-11 · A · 18–19 Oct:** Signal card with human Confirm / Return, reason, activity history and print/PDF actions.
- [ ] **FE-12 · A · 19 Oct:** Verify responsive desktop layout (including 1366×768), keyboard accessibility, meaningful error/empty/loading states.

### B. Backend, Firestore and security

- [ ] **BE-01 · B · 14 Oct:** FastAPI with `/api/v1/health`, settings, Pydantic, typed error response and CORS limited to expected local frontend origins.
- [ ] **BE-02 · B · 14–15 Oct:** Configure Firebase Admin server-side; document safe credentials via `.env.example`; do not commit private keys.
- [ ] **BE-03 · B · 15 Oct:** Firestore repository methods for developers, ЖК, advertisements, evidence, factors, signals, audit.
- [ ] **BE-04 · B · 15 Oct:** Firebase Authentication email/password and server-side ID-token verification; demo analyst and optional admin role.
- [ ] **BE-05 · B · 15 Oct:** Define `data/seed` and idempotent, non-destructive initialization of ≥8 fictional ЖК and ≥12 ads.
- [ ] **BE-06 · B · 16 Oct:** List/filter details endpoints; validate VКО geography and missing fields; paginated and bounded queries.
- [ ] **BE-07 · B · 16 Oct:** Advertisement manual creation and linking, typed request/response; fake source clearly marked DEMO.
- [ ] **BE-08 · B · 16–17 Oct:** Private Firebase Storage uploads, file-size/type checks, evidence metadata with source/timestamp and optional SHA-256.
- [ ] **BE-09 · B · 17 Oct:** Endpoint for proposed/confirmed/rejected factor decisions; verify analyst, evidence and atomic score update.
- [ ] **BE-10 · B · 17–18 Oct:** Signals endpoints, human confirmation/return, reviewer+timestamp+reason in audit log.
- [ ] **BE-11 · B · 18 Oct:** HTML/PDF report with demo watermark, verified factors/links/snapshots/reviewer, graceful font/system dependencies.
- [ ] **BE-12 · B · 18–19 Oct:** Docker Compose builds/runs frontend/backend locally and uses *online* Firebase/Gemini; document commands.
- [ ] **BE-13 · B · 19 Oct:** Verify Firestore/Storage access control, no public document uploads, secret scanning, quotas and error handling.

### C. Gemini analysis and deterministic risk

- [ ] **RISK-01 · C · 15 Oct:** Implement pure server-side `calculate_risk(factors)` with official R1–R6 weights; score capped at 100.
- [ ] **RISK-02 · C · 15 Oct:** Zones GREEN 0–24 / RED ≥60 with R1+R2 / YELLOW otherwise, including ≥60 without R1+R2.
- [ ] **RISK-03 · C · 15 Oct:** Ensure UNKNOWN/PROPOSED/REJECTED = 0 and inability to verify basis does not imply R1.
- [ ] **RISK-04 · C · 15–16 Oct:** Unit tests for A=35/YELLOW, B=70/RED, C=10/GREEN and missing-source exception conditions.
- [ ] **AI-01 · C · 16 Oct:** Design AI JSON extraction schema, prompting, source quote/candidate/confidence/uncertainty; Pydantic validation.
- [ ] **AI-02 · C · 16 Oct:** Gemini server-side client, configurable model/API key, timeouts/retries/quota errors, no raw secrets in logs.
- [ ] **AI-03 · C · 16–17 Oct:** Analyze **new** Russian ad text and detect paid reservation/deposit as *proposal* with exact excerpt.
- [ ] **AI-04 · C · 17 Oct:** Analyze screenshot/image with Gemini; return structured terms, amount, source quote and uncertainty.
- [ ] **AI-05 · C · 17 Oct:** Candidate match to known ЖК by name/aliases; ambiguous matches require analyst selection.
- [ ] **AI-06 · C · 17 Oct:** Test Kazakh text, low-quality screenshot and harmless ad to identify false positives; record results.
- [ ] **AI-07 · C · 17–18 Oct:** Integrate proposal→review→confirmed factor; model must never automatically set legal confirmation/score.
- [ ] **AI-08 · C · 18 Oct:** Describe model/prompt/version, limits and measured behavior on unseen inputs in docs.

### D. Integration, demonstration and release

- [ ] **INT-01 · A+B+C · 14–15 Oct:** Freeze basic complex/ad/evidence/AI-result/score JSON contracts with sample fixtures.
- [ ] **INT-02 · A+B+C · 16–17 Oct:** UI calls real backend/Firestore; no hidden stub response falsely presented as AI or live government data.
- [ ] **INT-03 · A+B+C · 18 Oct:** Demonstrate from newly entered ad to reviewed R2, score, signal decision and PDF.
- [ ] **INT-04 · A+B+C · 18–19 Oct:** Run three mandatory scenarios with corresponding demo objects, screenshots and expected scores.
- [ ] **QA-01 · B+C · 18 Oct:** Backend pytest risk/auth/validation; no confirmed risk without evidence/reviewer.
- [ ] **QA-02 · A · 19 Oct:** Frontend typecheck/build and core interaction tests, errors and empty states.
- [ ] **QA-03 · B · 19 Oct:** CI checks Python style/tests and TS typecheck/build for each PR to main.
- [ ] **QA-04 · A+B+C · 19–20 Oct:** Fresh Git clone on a second device/account with Internet; prove `.env`/Firebase/Gemini configuration and local startup.
- [ ] **SEC-01 · B · 19–20 Oct:** Ensure `.gitignore` and entire Git history do not expose private service-account JSON, Gemini keys or user information; rotate any exposed keys.
- [ ] **DOC-01 · B · 19 Oct:** Complete `README.md` (why, capabilities, tech stack, architecture, setup, env, seed, demo, known limitations).
- [ ] **DOC-02 · C · 19 Oct:** Add `docs/risk-rules.md`, `docs/ai-methodology.md` and API examples.
- [ ] **DOC-03 · B · 19 Oct:** Add `docs/data-model.md`, `docs/architecture.md`, Firebase index/rules setup and system diagram.
- [ ] **DOC-04 · A · 19 Oct:** Add `docs/demo-scenarios.md` with step-by-step clicks and expected results.
- [ ] **RELEASE-01 · A+B+C · 20 Oct:** Approve green CI, correct README URLs; record immutable commit SHA; create submission tag.
- [ ] **RELEASE-02 · A · 20 Oct:** Switch repo from private to public **before** deadline; verify access without login; submit URL/commit as required.
- [ ] **PITCH-01 · A+B+C · 20 Oct:** Practice timed live demo; prepare backup recording for outage, never substitute prerecorded results for live AI without disclosure.

## 3. P1 differentiator — «Рекламный след» (after P0)

- [ ] **LINK-01 · C · 18–19 Oct:** Normalize shared phone numbers (+7/8), WhatsApp URLs, website domains and alias names.
- [ ] **LINK-02 · C · 18–19 Oct:** Propose ad-to-ad links with explicit evidence; optionally add image perceptual hashes / embedding similarity.
- [ ] **LINK-03 · B · 19 Oct:** Persist proposed/confirmed/rejected links with provenance and reviewer/audit metadata.
- [ ] **LINK-04 · A · 19 Oct:** Show related ads/accounts in a graph or clear list; navigate directly to shared evidence.
- [ ] **LINK-05 · A+C · 19 Oct:** Demonstrate two fictional accounts sharing a number; do not infer common ownership or change base R1–R6 scoring.

## 4. P2 optional drone inspection (only with spare time)

- [ ] **DRONE-01 · A+B · after P0:** Add photo upload to selected ЖК with private Storage handling.
- [ ] **DRONE-02 · C · after P0:** Define configurable checklist pending organisers' criteria; Gemini classifies `visible / not_visible / uncertain`.
- [ ] **DRONE-03 · A · after P0:** Show marked results and human review; no claim of confirmed noncompliance on one photograph.
- [ ] **DRONE-04 · B · after P0:** Save separate inspection report/evidence trail; do not touch core advertising-law score.

## 5. GitHub workflow for teammates who have not used Git

### 5.1 One-time setup

1. Install **Git** and **VS Code**. Make a GitHub account; ask repo owner to invite you under **Settings → Collaborators** (accept invitation).
2. Open VS Code terminal and configure your identity (replace names/email):

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
git clone https://github.com/arturk0-0/3a-saq-qurylys.git
cd 3a-saq-qurylys
git status
```

3. Only work from a fresh branch. Never create secrets or `.env` in a commit. Ensure `.env` is in `.gitignore`.

### 5.2 Start a task (example FE-05)

```bash
git switch main
git pull origin main
git switch -c feat/FE-05-ads-feed
```

**Branch convention:** `feat/FE-05-ads-feed`, `fix/RISK-02-zone`, `test/QA-01-score`, `docs/README-setup`. One task or tightly related change per PR, one owner per branch.

### 5.3 Edit, test, commit, push

Edit only the files related to the task. Run relevant tests and inspect changes:

```bash
git status
git diff
# Stage intentionally: don't blindly stage .env or generated outputs.
git add frontend/src
# Or: git add backend/app backend/tests
git commit -m "feat(FE-05): add ads feed view"
git push -u origin feat/FE-05-ads-feed
```

On GitHub open **Compare & pull request** → target `main`. Add: task ID, short summary, how to run, test output, screenshots (for UI), limitations. Request review from another teammate. The reviewer inspects code/tests; author resolves comments with further commits and pushes. When approved and CI passes, use **Squash and merge**, then delete the branch remotely.

### 5.4 Sync your working directory after merge

```bash
git switch main
git pull origin main
git branch -d feat/FE-05-ads-feed
```

Create the next feature branch from the updated `main`, not from an outdated feature branch.

### 5.5 Merge conflicts

If someone changed the same lines, notify them; don't delete their code. In your **feature branch**:

```bash
git fetch origin
git merge origin/main
# Resolve conflict markers in your editor, run tests, then:
git add path/to/resolved/file
git commit
git push
```

Never use `git push --force` to `main`; do not attempt a conflict resolution on `main` without review. If you have uncommitted work, commit it or intentionally stash it before merging.

### 5.6 Branch protection and PR quality

Repo owner should use GitHub branch rulesets to block force pushes and (when supported by plan and verified to work) require PRs and green CI on `main`. If a ruleset blocks all merges for a small/private repo plan, fix the ruleset rather than bypassing normal code review. Keep `main` runnable. Assign reviewers and keep PRs small.

**Definition of Done:** code really runs (not mock-only), relevant tests pass, safe errors, new input processed if AI feature, docs updated, PR merged/reviewed, checklist item marked `[x]` with PR link. A deadline does not justify claiming false verification.

## 6. Developer environment and Firebase/Gemini configuration

- Frontend: `React + Vite + TypeScript + Tailwind + shadcn/ui`; backend: `FastAPI`; Firebase project: `saq-qurylys`.
- Backend Gemini API key and Firebase Admin credentials are **server-only**, never in React `VITE_...` variables, source files, Issues, commits, or Docs.
- `firebaseConfig` web values may be used by frontend for Firebase Auth, but secure client access is enforced by Firebase Security Rules; do not put Admin credentials in the frontend.
- `GEMINI_MODEL` must be configurable. Model ID and availability should be validated when implementing, not assumed in advance.
- Prepare `.env.example` with placeholders for Firebase project ID, credentials path or runtime credentials, Gemini key, CORS origins and frontend web config. Do not distribute real `.env` in the repository.
- Judges should be given **private** demo credentials and connection instructions. If they use a shared demo project, segregate per-judge demo accounts/data to avoid interference; do not overwrite data during re-seeding.
- Developers run frontend/backend locally while connecting via Internet to Google/Firebase. No need to install Firestore, local LLM, Ollama or a dedicated OCR ML model on judge machines.
- Provide one-command Docker startup plus README instructions for missing billing/permissions/API quotas/network failure.

## 7. Test cases and expected results

| ID | Input | Expected |
| --- | --- | --- |
| A | UNKNOWN legal basis; R2 paid booking + R3 active under-construction ad confirmed | **35, YELLOW** |
| B | Confirmed R1 no applicable basis; confirmed R2 deposit; confirmed R3 ad | **70, RED**; reviewer still must approve signal |
| C | Valid applicable guarantee, confirmed R3 ordinary ad | **10, GREEN** |
| D | 60+ points but R1+R2 not both confirmed | **YELLOW**, never RED |
| E | AI predicts R2 but nobody verifies evidence | **0** from R2; score unchanged |
| F | R2 marked rejected | 0 from R2; score recomputed |
| G | R1 source unknown, or state 'not found in demo dataset' | R1 remains UNKNOWN, **not** CONFIRMED |
| H | Input a newly written text or unseen screenshot | Real Gemini request; structured hypothesis/uncertainty, no hardcoded output |
| I | Reviewer returns signal with reason | Status `returned` + actor, date/time, reason persisted |
| J | Login missing or low privilege | Protected data/API denied; no secret leaked |
| K | Unreachable external AI | Informative retry/failure; existing evidence/records remain accessible |
| L | Clone on another computer | README setup works; local UI/backend, cloud data/AI; seed reproduces A/B/C |

Keep tests in `backend/tests/` and `frontend` test location. Document manual verification steps in `docs/demo-scenarios.md`.

## 8. GitHub submission, README and demo readiness

**Required repo contents:** actual working source, `README.md`, `.env.example` without secrets, example seed/import procedure, `docs/PROJECT_SPEC.md`, `docs/DEVELOPMENT_PLAN.md`, `AGENTS.md`, test suite, CI config and meaningful limitations statement.

README should include: problem, territory, who uses app, module list, tech stack, diagram, prerequisites, environment variables, access configuration, startup (`docker compose up --build`), seed, login, A/B/C reproducible test procedures, run tests, provenance of demo data, known limitations, safety/legal disclaimer, cited third-party software and AI provider details.

**Final dry run:** from blank folder on a second PC, clone repo, configure secrets privately, start app, see ≥8 ЖК and ≥12 ads, add new text/screenshot, receive AI proposed excerpt, approve it, observe correct risk, create/review PDF report. Copy final commit SHA and tag e.g. `hackathon-submission-2026-10-20`. Verify repo becomes public without signing in before official code-review cutoff; do not assume PR merges after cutoff update the judged commit.

**Pitch order:** user/problem → workflow demo → traceability and human verification → risk model legality → unique «Рекламный след» if ready → why architecture is reproducible/secure → limitations. Drone is a short extra only if implemented and validated. Keep a backup screen recording in case of Internet outage; disclose when showing recorded material.

## 9. Blockers and change log

| Date | Issue | Owner | Action | Status |
| --- | --- | --- | --- | --- |
| 14 Oct | Precise final GitHub cutoff and access hand-off | A | Ask organisers | OPEN |
| 14 Oct | No official property permit registry/API | B+C | Demo internal records with explicit provenance | ACCEPTED |
| 14 Oct | Gemini cost/quotas and Firebase Storage billing | B+C | Validate budget, usage limits and account setup | OPEN |
| 14 Oct | Drone inspection checklist not specified | A | Obtain official criteria before promising full compliance detection | OPEN |
| 14 Oct | Repo currently private; public for assessment | A | Switch before code-review cutoff, verify anonymously | OPEN |

**Decision log:**
- 14 Oct: East Kazakhstan only; internal protected UI; public GitHub source at submission; React/Vite/TS + FastAPI + Firebase Auth/Firestore/Storage + Gemini API; backend/front-end locally runnable with internet.
- 14 Oct: AI proposes; reviewer confirms; scoring algorithm deterministic; no fake government API; demo data only.
- 14 Oct: Base five modules before ad-network graph; drone optional.

**Rule for changing plan:** create/annotate GitHub Issue, inform affected owner, adjust specs/tests, and record rationale here; don't silently modify legally significant scoring or security decisions.
