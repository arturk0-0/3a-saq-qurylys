# Материалы и единая проверка · согласованный hand-off v1

20 октября 2026. **Реализовано в B / PR #32; совместимо с исходным hand-off v1.**
Additive фасад над существующими находками/объявлениями. B реализует backend,
A — TypeScript клиент. Детали совместимых дополнений фиксировать здесь прежде
использования; не менять существующие API/Firestore коллекции разрушительно.

## Маршруты

| Метод | Путь | Поведение |
| --- | --- | --- |
| GET | `/api/v1/materials` | Единая выборка сгруппированных материалов |
| GET | `/api/v1/materials/{id}` | Текущая ревизия, оригиналы, гипотезы, решения |
| GET | `/api/v1/materials/{id}/occurrences` | Пагинация оригинальных публикаций |
| GET | `/api/v1/materials/{id}/occurrences/{occurrenceId}` | Конкретный оригинал гипотезы вне первой страницы |
| GET | `/api/v1/materials/{id}/history` | История решений без UID; cursor, limit 1–50 |
| POST | `/api/v1/materials/{id}/review` | Одна операция проверки |
| POST | `/api/v1/materials/{id}/retry-analysis` | Повтор только для failed, с идемпотентностью/квотой |

Список: `q`, `review=all|needs_review|reviewed|dismissed`,
`origin=all|automatic|manual`, `platform` (необязательная строка), `complexId`,
`sort=priority|recent`, `cursor`, `limit` 1–50. По умолчанию review=all,
sort=priority: сначала needs_review, затем по серверному score (null после
рассчитанных), lastSeenAt и стабильному id. Проверенные материалы не скрываются
неявным фильтром «Все материалы». Ответ `{items: MaterialSummary[], nextCursor: string|null}`.
Неподходящий фильтрам cursor не использовать. Никаких client-side total/полноты
по первой странице; нужны стабильный tie-break и непропадающие элементы.

## DTO (представление JSON)

`Priority`: `{score:number|null, level:'unknown'|'low'|'medium'|'high', reasons:string[]}`.
Score серверный, 0–100; null означает приоритет пока не рассчитан, не нулевой риск.
Это не confidence модели и не вероятность нарушения. Нельзя преобразовывать его
в RiskResult. Формула — B, отдельная документированная функция; A не изобретает
пороги/веса. Названия уровней в UI: «Ещё не оценено / Низкий / Средний / Высокий».

`Analysis`: `{status:'queued'|'running'|'ready'|'failed'|'unsupported',
errorCode:string|null, canRetry:boolean, updatedAt:string|null}`.
Ожидание квоты: status=queued + errorCode=AI_DAILY_LIMIT. Ошибки использовать
через существующие safe error mapping; нет сырых provider payload/credentials.

`MaterialSummary`:
- `id:string`, `version:number`, `title:string`, `textPreview:string`;
- `reviewState:'needs_review'|'reviewed'|'dismissed'`;
- `origins:('automatic'|'manual')[]`, `platforms:string[]`;
- `occurrenceCount:number`, `firstSeenAt:string`, `lastSeenAt:string`;
- `complex:{id:string,name:string,version:number}|null` (подтверждённая/однозначная связь);
- `priority:Priority`, `analysis:Analysis`.

`MaterialDetail` расширяет Summary:
- `text:string`, `revisionId:string`;
- `occurrences:Occurrence[]`, `nextOccurrenceCursor:string|null` — первые 20 оригиналов;
  оставшиеся через occurrences endpoint (`cursor`, `limit` 1–50), формат Page<Occurrence>;
- `hypotheses:Hypothesis[]`, `complexCandidates:{id:string,name:string,address:string}[]`;
- `confirmedRisk:RiskResult|null` — прежний серверный DTO R1–R6, без смены весов;
- `review:{notes:string,reviewedAt:string,reviewerDisplayName:string|null}|null`.

`Occurrence`: `{id:string, origin:'automatic'|'manual', platform:string,
account:string, originalUrl:string|null, publishedAt:string|null,
capturedAt:string, text:string, media:Media[], legacyKind:'monitoring'|'advertisement',
legacyId:string}`. Не переписывать оригинал для дедупликации.

`Media`: `{id:string,kind:'image'|'video'|'thumbnail',url:string|null,
availability:'private'|'external'|'unavailable', analyzed:boolean}`.
Private файл загружается существующим авторизованным механизмом, не через
неавторизованный img src с bearer-токеном в URL. Внешняя ссылка ≠ анализ видео.

`Hypothesis`: `{id:string,code:'R2'|'R3',quote:string,explanation:string,
occurrenceId:string,decision:'pending'|'confirmed'|'rejected'|'insufficient'}`.
Существующий AI извлекает R2/R3. Не придумывать автоматические R1/R4–R6.
Другие документальные факторы сохраняют свой прежний контракт/проверку.

## Одно сохранение

Review body: `{requestId:string, expectedVersion:number, revisionId:string,
complexId:string|null, expectedComplexVersion:number|null,
decisions:{hypothesisId:string,decision:'confirmed'|'rejected'|'insufficient'}[],
notes:string, disposition:'reviewed'|'needs_review'|'dismissed'}`.

- Все существующие role/validation/source/document checks сохраняются.
- Комплекс можно выбрать здесь без отдельного attach action. Подтверждение
  рекламного фактора требует допустимой связи с ЖК и конкретным оригиналом.
- При смене ЖК нельзя молча перенести старые подтверждённые факторы на другой ЖК.
- Сохранение явно выбранных решений; нет скрытого «подтвердить всё».
- 200: актуальный MaterialDetail с итоговым confirmedRisk. Повтор того же
  requestId/payload не создаёт повторов аудита/баллов. Иной payload с тем же ID — конфликт.
- 409: устаревшая версия/ревизия/ЖК; никакого частичного применения. UI сохраняет
  черновик, предлагает обновить данные, не отправляет его повторно автоматически.
- 422: недостаточное доказательство/невалидное решение, без частичных баллов.
- 401/403/429: сохраняются прежние значения авторизации/квоты.

Retry body: `{requestId:string,expectedVersion:number}`; 200 — актуальный Detail.
Анализ выполняет worker; повтор HTTP-запроса не означает новый платный вызов.

Прежние create/upload API остаются точками поступления ручных материалов:
после успешного сохранения backend ставит поддерживаемую ревизию в очередь.
Прежние routes/deep links работают до завершения совместной миграции UI.
В ответ ЖК B добавляет `reviewPriority:Priority`; прежнее поле `risk` сохраняется.
Не привязанная к однозначному ЖК находка не увеличивает приоритет случайного ЖК.

## Проверка интеграции

Новый текст → queued → ready → гипотезы → одно review → подтверждённый балл.
Дубль из другой платформы → одна карточка/два оригинала/без второго AI запроса.
Новые существенные условия → новая ревизия/повторная проверка, старое решение
остаётся в истории. Квота/ошибка/неподдерживаемое видео/конфликт/частично недоступный
источник видимы и не превращаются в подтверждение. Только синтетические QA/local
адаптеры при разработке, production не подменяется ими.


## Совместимые уточнения реализации B

- Detail ЖК теперь возвращает `version`; она нужна в expectedComplexVersion при
  выборе кандидата. GET `/complexes?sort=priority` сортирует по reviewPriority.
- Приоритет: нерешённый R2=25, R3=10, код учитывается один раз; low <10,
  medium 10–24, high >=25. При текущем наборе максимум 35. Подтверждённая
  оценка R1–R6 имеет прежнюю формулу. Баллы разных материалов не суммируются
  повторно по одному коду для одного ЖК.
- Внешние video/image/thumbnail не скачиваются и не анализируются. После
  анализа текста такой материал имеет status=unsupported,
  errorCode=EXTERNAL_MEDIA_NOT_ANALYZED. Доступные текстовые гипотезы сохраняются.
- История: `{items:[{id,action,createdAt,reviewerDisplayName,details}],nextCursor}`;
  details содержат revisionId, decisions, notes, disposition. Не отображать
  технические ID в качестве имени человека. Старый журнал остаётся в прежних API.
- Cursor связан с фильтрами и снимком выборки. При изменении данных — 409:
  загрузить первую страницу, не продолжать устаревший cursor.
- Приватные ручные реальные данные, публичные находки и учебные данные имеют
  разные scope. Они намеренно не склеиваются между scope: публичная копия не
  должна открывать приватный файл или учебную карточку реальному источнику.
- Одинаковые входы внутри scope используют общий кэш Gemini; отдельные ЖК
  сохраняют собственные jobs/версии/решения. Успешные старые результаты
  подхватываются по точному тексту и фактическому SHA изображения.
