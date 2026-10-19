# План SAQ QURYLYS

Актуализирован **19 октября 2026** по поручению владельца. Регион — ВКО.
Команда: **A — друг, frontend/материалы; B — владелец, backend/AI/выпуск**.
Для MON-задачи владелец отдельно разрешил B одновременно реализовать необходимый
frontend, не ожидая A. Это ограниченное исключение, а не передача всего frontend.


**Текущее состояние, 19 октября:** main `6cd5db0` содержит мониторинг и улучшения
интерфейса. Владелец опубликовал API `release-34eab8a`, Hosting и индексы,
проверил Instagram → AI → решение/историю. Job/Scheduler созданы; подтверждены
heartbeat worker и успешное выполнение по Scheduler. Фактический повторный сбор
источника после истечения интервала ещё требуется проверить. Новая сверка
разрешений разрабатывается в `feat/registry-basis-screening`; это ещё не live-релиз.


## Новая очередь: карта и участники ЖК · 19 октября

B подготовил реализацию ORG-01–06/GEO-01 в [PR #23](https://github.com/arturk0-0/3a-saq-qurylys/pull/23) поверх #19; это не merge и не облачный выпуск.
[Отчёт и проверки B](company-profiles-report.md), [контракты](company-api.md).
Чекбоксы интеграции остаются открыты до merge и совместной проверки с картой A.
[Разделение и промпты](tasks/map-company-split.md).
A работает без облачных кабинетов/ключей; B делает всю сложную интеграцию и frontend компаний.

- [ ] **MAP-01–06 · A** — [#20](https://github.com/arturk0-0/3a-saq-qurylys/issues/20):
  вторичный сворачиваемый блок в реестре ЖК, Leaflet/OSM, одинаковые объёмные здания
  на известных координатах, адрес/переход к ЖК. Без процентов готовности. Lazy loading,
  mobile/keyboard/empty/error, тесты и handoff; backend/компании A не меняет.
- [ ] **ORG-01–05 · B** — [#21](https://github.com/arturk0-0/3a-saq-qurylys/issues/21):
  исследование открытых источников, идентификация по БИН, отдельные роли юридического
  застройщика/уполномоченной компании, provenance каждого факта, ограниченные адаптеры,
  хранение/защищённый API. Количество завершённых объектов только с перечнем/границами охвата.
- [ ] **ORG-06 · B** — блок двух организаций в карточке ЖК, отдельные страницы компаний,
  компактные ссылки на конкретные источники возле значений, даты/неизвестное/расхождения.
- [ ] **GEO-01 · B** — достоверные реальные ЖК/адреса/координаты с источником и точностью;
  не привязывать реальные компании к DEMO-записям и не подменять стройку офисом продаж.
- [ ] **ORG-07–08 · B** — проверки, отчёт, review/CI и интеграция с картой A.
  Публикация API/Hosting — отдельный шаг. Сохранить открытый PR #19 со сверкой реестров;
  не повторять готовую реализацию и не считать наличие PR облачным выпуском.

Общие frontend файлы разделены явно: A — city-map/** и ComplexList.tsx,
B — company frontend, ComplexDetail.tsx, routes и shared types. Старые A-01–04 выполнены.
R1–R6/auth/rules не меняются, платные AI/SearchAPI запросы не нужны.

## 1. Главный результат и фактическое состояние

Цель продукта: **находить публичную рекламу → сохранять оригиналы/ревизии →
выделять возможные признаки риска → передавать эксперту → подтверждать факты →
формировать сигнал/PDF**. Ручной ввод — дополнительный путь, не замена мониторингу.
ИИ не устанавливает незаконность; отсутствие данных не становится R1.

- Базовые модули, Gemini text/image, ручные решения, сигналы/PDF, читаемый UI и
  «Рекламный след» уже в `main` / `ed38f00`: PR #5/#6/#7/#11/#10/#12.
  Повторно их не разрабатывать. CI main зелёный, 345 backend + 11 SDK tests,
  64 frontend tests, локальный Chromium — 16 групп/658 запросов.
- Владелец сообщил, что выполнил команды обновления и открыл собранный сайт
  17 октября. Это сообщение владельца, не автоматическая облачная приёмка Codex.
- Мониторинг опубликован владельцем 18 октября: источники, Instagram/SearchAPI,
  очередь, AI и экспертное решение проверены на живом сайте. Полный охват Instagram
  не гарантируется. [Фактическая проверка Instagram](instagram-feasibility.md).
- Старые P0-задачи закрыты ниже по существующей реализации и проверкам;
  полноценные RU/KZ-измерения, независимый чистый запуск и выпуск остаются открыты.

Обозначения: `[x]` — результат реализован/проверен с указанными ограничениями;
`[ ]` — незавершённая работа или внешний prerequisite. Feature-ветка не означает
публикацию сайта; моки/эмуляторы не означают облачную проверку.

## 2. Сейчас: автоматический мониторинг (P0, B + разрешённый frontend B)

- [x] **MON-IG-01** — проверить официальные способы сбора Instagram-таргета по
  Казахстану, ограничения Meta API и фактический доступ из среды; записать источники.
- [x] **MON-IG-02** — SearchAPI реально вернул KZ/Instagram:16 карточек по общему
  запросу, включая предоставленный ID;4 по «квартиры Өскемен»,3 с пригодным текстом
  ВКО. Ровно2 поиска, остаток98 из100. Адаптер/UI/защита резерва20 реализованы;
  [факты и границы](instagram-searchapi.md). Cloud активация — открытый MON-09.
- [x] **MON-01** — источники, ревизии публикаций, отдельная реальная очередь,
  неизменяемый оригинал/ссылка/время/hash, серверные контракты и доступ аналитика.
- [x] **MON-02** — рабочие публичные адаптеры: интернет-поиск и Telegram; строгие
  лимиты/таймауты/ошибки, никакого обхода login/CAPTCHA. Поисковый фрагмент явно
  отличается от полного поста и не объявляется таргетированной рекламой.
- [x] **MON-03** — устранение дублей и сохранение изменённых версий; фильтр ВКО/жилья
  с объяснениями и видимой неопределённостью, без автоматического юридического вывода.
- [x] **MON-04** — автоматический Gemini по явному opt-in, не более одного анализа
  за запуск источника, общие суточные квоты, идемпотентность и безопасная диагностика.
- [x] **MON-05** — frontend: источники/ошибки/запуски и очередь находок, оригиналы,
  AI-гипотезы, экспертные решения с причиной и сохранением заметок при конфликте.
- [x] **MON-06** — связать подтверждённую экспертом находку с реальным ЖК и прежним
  потоком доказательств, факторов и PDF. Реальные посты не привязывать к DEMO-объектам.
- [x] **MON-07** — worker регулярного запуска, lease/конкурентность/квота, инструкция
  Cloud Run Job/Scheduler и локальный режим без зависимости от открытого браузера.
- [x] **MON-08** — подходящие unit/API/SDK/browser tests, документация и отдельный PR;
  тестовые адаптеры и реальные HTTP-пробы обозначены, сторонние ключи не публикуются.
- [x] **MON-09a** — владелец опубликовал API/Hosting/индексы, создал worker и hourly
  Scheduler; execution `saq-qurylys-monitor-ltms7` завершился успешно, heartbeat виден.
- [ ] **MON-09b** — подтвердить следующий фактический сбор по расписанию после
  наступления nextRunAt и новый run в истории, а не только успешный heartbeat.
- [x] **REG-01 · B** — публичные кандидаты Homeportal/Ashyq, сверка применимого
  разрешения/гарантии и исключение подтверждённой находки из активной очереди.
  [Реализация и границы](registry-screening.md), [PR #19](https://github.com/arturk0-0/3a-saq-qurylys/pull/19).
  Сервер/UI/SDK/Compose проверены; публикация остаётся REG-02.
- [ ] **REG-02 · B + владелец** — после review/CI опубликовать API + Hosting и проверить
  разрешение/гарантию в облаке; факторы R1–R6 остаются прежними.

Реализация MON-01–08: [PR #14](https://github.com/arturk0-0/3a-saq-qurylys/pull/14),
[отчёт с проверками и ограничениями](monitoring-report.md),
[контракты/worker](monitoring.md), [активная задача #13](https://github.com/arturk0-0/3a-saq-qurylys/issues/13).
После SearchAPI: 431 backend, 14 SDK/emulator, 72 frontend, build, 18 browser-групп.
Это закрытие реализации в ветке, не human approval/merge/облачной приёмки.
MON-IG-02 подтверждён коротким live trial и запуском владельца. MON-09b остаётся
открыт. Полный охват Instagram не обещается, media автоматически не скачиваются.

Публичные изображения/видео, Stories и закрытые аккаунты не считаются покрытыми
текстовым сборщиком как файлы. Для Meta сохраняются только media references;
дополнительный медиасбор требует отдельной проверки доступа,
приватного хранения/лимитов и явного перечня поддерживаемых источников.

## 3. Остаток проверок и выпуска

- [x] **UX-01 · B, прямое поручение владельца 18 октября** — Упростить ежедневный UI,
  убрать общий DEMO и надписи о стоимости, перенести Instagram/config из очереди,
  скрыть UID авторов. [Проверки и границы](analyst-ui-report.md); реализация в своей
  ветке, публикация Hosting отдельно. Локальные учебные пометки сохранены.


Это реальные незакрытые пункты прежнего плана, а не отсутствующие CRUD-экраны.

**Интеграция 17 октября:** очередь друга A-01–04 завершена и совмещена с MON
в `release/integrated-monitoring-readiness`; main и живой сайт пока не обновлены.
Сохранены его исправления черновиков/скриншотов, lazy-loading и материалы показа.
[Отчёт интеграции и следующий шаг](integration-readiness-report.md),
[исходный handoff A](frontend-handoff.md). Реализацию этих задач не повторять.

- [ ] **PM-01 · B** — Confirm organisers' exact submission time, judge test procedure, expected drone criteria and any permitted public data sources.
- [ ] **BE-13 · B** — Verify Firestore/Storage access control, no public document uploads, secret scanning, quotas and error handling.
- [ ] **AI-06 · B** — Test Kazakh text, low-quality screenshot and harmless ad to identify false positives; record results.
- [ ] **AI-08 · B** — Describe model/prompt/version, limits and measured behavior on unseen inputs in docs.
- [ ] **QA-04 · B** — Fresh Git clone on a second device/account with Internet; prove `.env`/Firebase/Gemini configuration and local startup.
- [x] **SEC-01 · B, локальная проверка** — Gitleaks 8.30.1 по всем доступным refs/full history не нашёл секретов; исторические пути credentials проверены, `.gitignore` закрывает локальные файлы. [Область проверки](security-release-check.md). Это не проверка cloud IAM или гарантия отсутствия персональных данных; BE-13 остаётся открыт.
- [x] **DOC-01 · B, интеграционная ветка** — Материалы A включены, README указывает проверяемый кандидат, границы источников и актуальные инструкции; показ дополнен отдельным маршрутом MON. Облачная публикация отдельно.
- [ ] **RELEASE-01 · B** — Approve green CI, correct README URLs; record immutable commit SHA; create submission tag.
- [ ] **RELEASE-02 · B** — Switch repo from private to public **before** deadline; verify access without login; submit URL/commit as required.
- [x] **PITCH-01 · A, материалы** — Подготовлены `pitch.md`, `demo-checklist.md`, обновлён runbook; происхождение существующих иллюстраций обозначено. Совмещены в интеграционной ветке.
- [ ] **PITCH-02 · B, живой показ** — Пройти репетицию опубликованного SHA и записать резерв с приватно выданным доступом. Подготовленные тексты и локальный Chromium не закрывают этот пункт.

До завершения MON и приёмки не добавлять новые P1/P2. Точное время сдачи/часовой
пояс подтвердить у организаторов; ранее указанное 20 октября 23:59 — предположение,
не подтверждённый дедлайн. Финальные tag/публичность репозитория — отдельные действия.

## 4. Уже выполнено (baseline до MON)

Доказательства: PR [#5](https://github.com/arturk0-0/3a-saq-qurylys/pull/5),
[#6](https://github.com/arturk0-0/3a-saq-qurylys/pull/6),
[#7](https://github.com/arturk0-0/3a-saq-qurylys/pull/7),
[#11](https://github.com/arturk0-0/3a-saq-qurylys/pull/11), CI и отчёты
[baseline](release-candidate-report.md), [UI](frontend-readability-report.md),
[LINK](advertising-trace.md), [backend](backend-followup-report.md).
Прежняя ручная облачная приёмка подтверждена владельцем. Закрытие реализации
не закрывает оставшиеся измерения AI/проверку нового deployment/чистого устройства.

<details>
<summary>Выполненные задачи: 50</summary>

- [x] **PM-02 · B** — Create initial project issues with owner, priority, acceptance criteria and a branch naming scheme.
- [x] **FE-01 · A** — Set up Vite + React + strict TS, Tailwind, shadcn/ui, React Router, navigation shell and layout.
- [x] **FE-02 · A** — Design reusable controls: risk badge, document status, evidence status, loading/error/empty states, confirmations.
- [x] **FE-03 · A** — Overview dashboard with search, risk-zone filter, sort, quick link to ≥8 demo ЖК.
- [x] **FE-04 · A** — Optional geo pins using Leaflet/OSM for complexes with coordinates; list view remains usable if maps fail.
- [x] **FE-05 · A** — ЖК detail header: name, address, developer/BIN, stage, readiness, documentary basis and source.
- [x] **FE-06 · A** — Advertisement feed with platform, account, date, source URL, screenshot and manual-add modal/form.
- [x] **FE-07 · A** — Evidence tab; show exact AI-highlighted quote and ability to open full original material.
- [x] **FE-08 · A** — Documents tab; basis type, status confirmed/disproved/unknown, reference and last checked time.
- [x] **FE-09 · A** — Risk panel R1–R6 with scores, review statuses, breakdown and evidence links.
- [x] **FE-10 · A** — AI proposal review: accept/reject separately from signal decision; show fresh computed score.
- [x] **FE-11 · A** — Signal card with human Confirm / Return, reason, activity history and print/PDF actions.
- [x] **FE-12 · A** — Verify responsive desktop layout (including 1366×768), keyboard accessibility, meaningful error/empty/loading states.
- [x] **BE-01 · B** — FastAPI with `/api/v1/health`, settings, Pydantic, typed error response and CORS limited to expected local frontend origins.
- [x] **BE-02 · B** — Configure Firebase Admin server-side; document safe credentials via `.env.example`; do not commit private keys.
- [x] **BE-03 · B** — Firestore repository methods for developers, ЖК, advertisements, evidence, factors, signals, audit.
- [x] **BE-04 · B** — Firebase Authentication email/password and server-side ID-token verification; demo analyst and optional admin role.
- [x] **BE-05 · B** — Define `data/seed` and idempotent, non-destructive initialization of ≥8 fictional ЖК and ≥12 ads.
- [x] **BE-06 · B** — List/filter details endpoints; validate VКО geography and missing fields; paginated and bounded queries.
- [x] **BE-07 · B** — Advertisement manual creation and linking, typed request/response; fake source clearly marked DEMO.
- [x] **BE-08 · B** — Private Firebase Storage uploads, file-size/type checks, evidence metadata with source/timestamp and optional SHA-256.
- [x] **BE-09 · B** — Endpoint for proposed/confirmed/rejected factor decisions; verify analyst, evidence and atomic score update.
- [x] **BE-10 · B** — Signals endpoints, human confirmation/return, reviewer+timestamp+reason in audit log.
- [x] **BE-11 · B** — HTML/PDF report with demo watermark, verified factors/links/snapshots/reviewer, graceful font/system dependencies.
- [x] **BE-12 · B** — Docker Compose builds/runs frontend/backend locally and uses *online* Firebase/Gemini; document commands.
- [x] **RISK-01 · B** — Implement pure server-side `calculate_risk(factors)` with official R1–R6 weights; score capped at 100.
- [x] **RISK-02 · B** — Zones GREEN 0–24 / RED ≥60 with R1+R2 / YELLOW otherwise, including ≥60 without R1+R2.
- [x] **RISK-03 · B** — Ensure UNKNOWN/PROPOSED/REJECTED = 0 and inability to verify basis does not imply R1.
- [x] **RISK-04 · B** — Unit tests for A=35/YELLOW, B=70/RED, C=10/GREEN and missing-source exception conditions.
- [x] **AI-01 · B** — Design AI JSON extraction schema, prompting, source quote/candidate/confidence/uncertainty; Pydantic validation.
- [x] **AI-02 · B** — Gemini server-side client, configurable model/API key, timeouts/retries/quota errors, no raw secrets in logs.
- [x] **AI-03 · B** — Analyze **new** Russian ad text and detect paid reservation/deposit as *proposal* with exact excerpt.
- [x] **AI-04 · B** — Analyze screenshot/image with Gemini; return structured terms, amount, source quote and uncertainty.
- [x] **AI-05 · B** — Candidate match to known ЖК by name/aliases; ambiguous matches require analyst selection.
- [x] **AI-07 · B** — Integrate proposal→review→confirmed factor; model must never automatically set legal confirmation/score.
- [x] **INT-01 · B** — Freeze basic complex/ad/evidence/AI-result/score JSON contracts with sample fixtures.
- [x] **INT-02 · B** — UI calls real backend/Firestore; no hidden stub response falsely presented as AI or live government data.
- [x] **INT-03 · B** — Demonstrate from newly entered ad to reviewed R2, score, signal decision and PDF.
- [x] **INT-04 · B** — Run three mandatory scenarios with corresponding demo objects, screenshots and expected scores.
- [x] **QA-01 · B** — Backend pytest risk/auth/validation; no confirmed risk without evidence/reviewer.
- [x] **QA-02 · A** — Frontend typecheck/build and core interaction tests, errors and empty states.
- [x] **QA-03 · B** — CI checks Python style/tests and TS typecheck/build for each PR to main.
- [x] **DOC-02 · B** — Add `docs/risk-rules.md`, `docs/ai-methodology.md` and API examples.
- [x] **DOC-03 · B** — Add `docs/data-model.md`, `docs/architecture.md`, Firebase index/rules setup and system diagram.
- [x] **DOC-04 · A** — Add `docs/demo-scenarios.md` with step-by-step clicks and expected results.
- [x] **LINK-01 · B** — Normalize shared phone numbers (+7/8), WhatsApp URLs, website domains and alias names. Review/merge: [#7](https://github.com/arturk0-0/3a-saq-qurylys/pull/7); локальный сценарий с тестовыми адаптерами, облачный rollout отдельно.
- [x] **LINK-02 · B** — Propose ad-to-ad links with explicit evidence; optionally add image perceptual hashes / embedding similarity. Review/merge: [#7](https://github.com/arturk0-0/3a-saq-qurylys/pull/7); локальный сценарий с тестовыми адаптерами, облачный rollout отдельно.
- [x] **LINK-03 · B** — Persist proposed/confirmed/rejected links with provenance and reviewer/audit metadata. Review/merge: [#7](https://github.com/arturk0-0/3a-saq-qurylys/pull/7); локальный сценарий с тестовыми адаптерами, облачный rollout отдельно.
- [x] **LINK-04 · A** — Show related ads/accounts in a graph or clear list; navigate directly to shared evidence. Review/merge: [#7](https://github.com/arturk0-0/3a-saq-qurylys/pull/7); локальный сценарий с тестовыми адаптерами, облачный rollout отдельно.
- [x] **LINK-05 · B** — Demonstrate two fictional accounts sharing a number; do not infer common ownership or change base R1–R6 scoring. Review/merge: [#7](https://github.com/arturk0-0/3a-saq-qurylys/pull/7); локальный сценарий с тестовыми адаптерами, облачный rollout отдельно.

</details>

## 5. Отложено, не часть текущего P0

- [ ] **DRONE-01 · B** — Own private Storage/backend upload contract; A implements its frontend only after the criteria and API are agreed.
- [ ] **DRONE-02 · B** — Define configurable checklist pending organisers' criteria; Gemini classifies `visible / not_visible / uncertain`.
- [ ] **DRONE-03 · A** — Show marked results and human review; no claim of confirmed noncompliance on one photograph.
- [ ] **DRONE-04 · B** — Save separate inspection report/evidence trail; do not touch core advertising-law score.

## 6. Работа команды и Git

- База новой работы — свежий `origin/main`, своя feature-ветка, небольшие проверенные
  коммиты, push и PR. Без direct/force push main; review и зелёный CI перед merge.
- B сейчас ведёт всю MON-вертикаль по прямой команде владельца; A может продолжать
  независимые пользовательские материалы/QA, не менять одновременно MON-файлы.
- Новые источники/API описывать честно. Нет доступа/403/пустая выдача — разные
  состояния. Не записывать «объявлений нет», когда источник не прочитан.
- В `WORK_LOG.md` — фактический итог/проверки/следующий шаг, в этом плане — статус.
  Завершение MON в feature-ветке и публикация в облаке отмечаются раздельно.
- R1–R6 и сценарии A=35/YELLOW, B=70/RED, C=10/GREEN не меняются.

Контекст и границы: [PROJECT_SPEC](PROJECT_SPEC.md), [AGENTS](../AGENTS.md),
[команда](two-person-team.md), [публикация](cloud-deployment.md).
Полный прежний план с историческими датами/инструкциями сохранён в
[архиве](archive/DEVELOPMENT_PLAN-2026-10-17-before-monitoring.md);
его старые чекбоксы не являются активной очередью.
