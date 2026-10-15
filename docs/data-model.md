# Данные и API рабочего места

Все рабочие `/api/v1` endpoints требуют Firebase ID token и роль analyst/admin.
Исключение — публичный `/health`. Firestore/Storage закрыты для прямых клиентов.

Коллекции: `developers`, `complexes`, `advertisements`, `evidence`, `auditLogs`,
`seedRuns`; следующие этапы добавляют `analysisRuns`, `aiHypotheses`, `signals`.
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

Конфликт версии возвращает 409, неверный ввод 422; обновите карточку и пересмотрите
решение. UI никогда не присылает reviewer и не считает баллы самостоятельно.
Источник, используемый подтверждённым фактором, нельзя изменить до явного
пересмотра фактора. События аудита не имеют endpoint редактирования/удаления.

Тестовый MemoryStore используется только в pytest. Реальное приложение работает
через Firebase SDK; отсутствие конфигурации возвращает ошибку, а не тестовые данные.
