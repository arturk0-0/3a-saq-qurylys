# Данные и API рабочего места

Все рабочие `/api/v1` endpoints требуют Firebase ID token и роль analyst/admin.
Исключение — публичный `/health`. Firestore/Storage закрыты для прямых клиентов.

Коллекции: `developers`, `complexes`, `advertisements`, `evidence`, `auditLogs`,
`seedRuns`, `analysisRuns`, `aiHypotheses`, `signals`, `signalRevisions`,
`usageLimits`, `adLinks`; `users` зарезервирована адаптером, роль берётся из проверенного
Firebase ID token, а не доверяется пользовательскому документу.
Мониторинг добавляет отдельные `monitorSources`, `monitorItems`, `monitorRuns`,
`monitorEvents`, `monitorLimits`, `monitorAiRuns`; квоты Gemini общие через
`usageLimits`. [Полный контракт и границы реальной очереди](monitoring.md).
Source.kind дополнен `instagram_ads`, finding.contentKind — `instagram_ad`;
adArchiveId/adStartedAt/adActive/platforms/media и run.unreadable/providerCreditsBefore
описаны в [SearchAPI контракте](instagram-searchapi.md). Начало показа не дата поста.
Для импортированной находки `Advertisement.publishedAt` может быть null, если
источник не указал дату. Ручное создание объявления продолжает требовать дату.
JSON использует camelCase, даты ISO 8601 с часовым поясом, идентификаторы — ASCII.
DEMO scope проверяется сервером. Исходный текст объявления не редактируется.

R1–R6 встроены в документ ЖК: так версия карточки, ссылки на доказательства и
решение аналитика изменяются одной Firestore-транзакцией с audit event.
Баллы вычисляет `services/risk.py`, отдельного изменяемого score в Firestore нет.
Это реализация логической сущности riskFactors без отдельной коллекции.
Решение по источнику и решение по фактору — два отдельных действия.

## Контракты

Дополнение AI-05: необязательное поле ЖК `aliases` — до 20 явно заданных командой
альтернативных названий, каждое до 500 символов. При чтении старых документов
значение по умолчанию `[]`; миграция и перезапись существующего seed не нужны.
`POST /complexes` принимает это поле. AI не редактирует его. Расширение проверяется
в общей frontend/backend ветке и остаётся предметом командного review перед merge.

- `GET /complexes?q=&city=&zone=&sort=risk&limit=50&cursor=0` — список, total,
  nextCursor. Поиск и сортировка ограничены 500 записями DEMO-каталога после
  фильтра города; `catalogLimited` сообщает достижение границы. Для большого
  реестра потребуется отдельный поисковый индекс.
- `GET /complexes/{id}` — карточка, застройщик, вычисленный risk.
- `GET /complexes/{id}/risk` — баллы и вклады шести факторов.
- `GET /advertisements`, `/complexes/{id}/advertisements`,
  `/complexes/{id}/evidence` — страничные списки, limit 1–100, cursor = ID.
- `POST /advertisements` — complexId, platform, account, sourceUrl, text,
  publishedAt. createdBy/capturedAt задаёт сервер.
- `POST /evidence` — complexId, type, sourceUrl/sourceReference, excerpt,
  capturedAt, необязательный advertisementId. Цитата объявления должна точно
  встречаться в оригинальном тексте.
- `POST /evidence/{id}/decision` — expectedVersion, decision, notes и явные
  проверенные признаки. Не изменяет скоринг автоматически.
- `POST /complexes/{id}/factors/decision` — expectedVersion, code, decision,
  evidenceIds, notes. Подтверждение требует подходящих проверенных источников.
- `PATCH /complexes/{id}/legal-basis` — expectedVersion, basis. Подтверждённое
  основание нельзя совместить с подтверждённым R1.
- `GET /complexes/{id}/history` — история по убыванию createdAt, ID как tie-breaker.
  Перед запуском развернуть индексы из firestore.indexes.json.
- `GET /advertisements/{id}/matching-candidates?run_id={id}` — read-only кандидаты
  для названий из сохранённого завершённого AI-запуска этого объявления. Чужой
  ad/run — 422, незавершённый run — 409, нет доступа/DEMO-scope — стандартный отказ.
  Возвращает runId, advertisementId, currentComplexId, catalogLimited и groups:
  mention, ambiguous, candidateCount, candidatesLimited, candidates (complexId,
  name, city, matchedBy=name|alias|partial_name, matchedName, demo). Не имеет поля
  выбранного/подтверждённого совпадения и ничего не пишет в Firestore.
- `POST /advertisements/{id}/screenshots?expected_version={n}` — raw bytes
  статического PNG/JPEG/WebP с соответствующим Content-Type, до 6 MiB и
  20 мегапикселей. Ответ — Evidence; версия объявления увеличивается.
- `GET /evidence/{id}/file` — контролируемая загрузка после auth/DEMO-проверки
  и проверки размера/SHA-256; публичный Storage URL не создаётся.
- `POST /advertisements/{id}/analyze` — requestId UUID, expectedVersion,
  необязательный screenshotId этого объявления. Сохраняет запуск, извлечённые
  данные, proposed-гипотезы и proposed-доказательства, не подтверждая факторы.
  Повтор того же успешного requestId возвращает сохранённый результат;
  незавершённая/неуспешная попытка или чужой requestId — 409, без нового AI-вызова.
- `GET /advertisements/{id}/analysis`, `/advertisements/{id}/hypotheses` —
  страничные запуски и гипотезы. `POST /hypotheses/{id}/decision` —
  expectedVersion, accepted/rejected и notes; решение не подтверждает источник.
- `GET/POST /signals`, `GET /signals/{id}`, `POST /signals/{id}/decision` —
  список/создание/детали и submit/return/confirm с expectedVersion и notes.
  Создание требует expectedComplexVersion; submit обновляет снимок, confirm
  устаревшего снимка отклоняется. Изменение статуса атомарно с audit и ревизией.
- `GET /signals/{id}/revisions/{version}`, `/signals/{id}/history` —
  неизменяемые ревизии и страничная история, с проверкой доступа к сигналу.
- `GET /signals/{id}/report?format=pdf|html` — закрытый отчёт из сохранённого
  снимка, `no-store`; HTML экранируется, локальные/внешние ресурсы PDF запрещены.

Конфликт версии возвращает 409, неверный ввод 422; обновите карточку и пересмотрите
решение. UI никогда не присылает reviewer и не считает баллы самостоятельно.
Источник, используемый подтверждённым фактором, нельзя изменить до явного
пересмотра фактора. События аудита не имеют endpoint редактирования/удаления.

MemoryStore используется только явно обозначенными тестами и opt-in QA runner.
Отдельный локальный набор проверяет настоящий SDK с изолированным эмулятором.
Реальное приложение работает через Firebase SDK; отсутствие конфигурации
возвращает ошибку, а не тестовые данные.


## P1: рекламные совпадения

Дополнительные read-only preview, сохранение proposed-снимка и отдельное решение
аналитика: [контракт adLinks и границы выборки](advertising-trace.md#дополнение-api-и-данных).
Действующие документы/контракты R1–R6 не мигрируются; новая коллекция закрыта
прежними правилами и доступна через авторизованный backend. Новые контракты
и их frontend/backend реализация требуют совместного review перед merge.


## Сверка разрешения в мониторинге

Необязательный `monitorItems.basisReview` и событие `item.basis.confirm`:
[контракт и ограничения](registry-screening.md#контракты-и-ограничения).
Доказательство относится к версии находки и дате рекламы, не является
общим whitelist ЖК и не изменяет LegalBasis/факторы карточек ЖК.

## Source-attributed companies (Issue #21)

Additive model in [company API](company-api.md): `companies/bin-{BIN}` stores
source facts, bounded source-card portfolio and optimistic version;
`companyProjects/homeportal-{id}` stores the saved preview/version. Both are
server-only collections under existing deny-by-default client rules.

Complex retains developerId/coordinates and adds nullable authorizedCompanyId,
per-role partySnapshots (companyId/name/bin/role/source), participantSource and
coordinateSource/status. Old seed stays unchanged. New SignalSnapshot optionally
contains authorizedCompany and freezes the project-specific participant names;
old signals do not re-resolve current company names. No migration or new index
is required for ID-ordered company pagination. Sources do not modify legal basis
or any confirmed factor.
