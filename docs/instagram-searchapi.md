# Instagram Ads через SearchAPI

Актуально 17 октября 2026 (Asia/Qyzylorda). Владелец предоставил SearchAPI key через
секреты среды и разрешил короткий trial, сохранив минимум 20 из 100 запросов.
[PR #14](https://github.com/arturk0-0/3a-saq-qurylys/pull/14).
Это источник **Meta Ad Library**, не Google/Bing выдача сайтов.

## Что проверено на реальном API

Выполнены **ровно два** поисковых вызова, без пагинации и retry:
1. `продажа квартир`, KZ, Instagram, active, all — HTTP 200, **16 карточек**.
   Все 16 содержат INSTAGRAM среди платформ и active=true. Найден ID
   `1573735788124300`, предоставленный владельцем: текст/даты/ссылки на видео
   доступны. У 14 карточек извлечён текст, у 2 его нет.
2. `квартиры Өскемен` с теми же фильтрами — HTTP 200, **4 карточки**;
   echo search_parameters подтверждает engine=meta_ad_library, country=KZ,
   platforms=instagram и этот запрос. У 3 есть текст, все 3 проходят существующий
   лексический фильтр жилья/ВКО; у 1 нет доступного текста.

Account API `GET /api/v1/me`: до поиска remaining_credits=100, после первого 99,
после второго **98**. Дополнительные чтения Account API не изменили search credits.
Генерация Gemini и скачивание чужих медиа не выполнялись.
При дальнейшем тестировании **не выполнять новые live searches** без необходимости:
формат подтверждён, регрессии проверяются MockTransport/MemoryStore/emulator.

Сохранённый настоящий ответ второго поиска прогнан через MonitoringService с
явным локальным cached adapter/MemoryStore: fetched4, unreadable1, relevant3,
created3, duplicates0; DEMO risk не изменился, AI не запускался. Это проверка
реального формата ответа и локального импорта, **не запись в облачный Firebase**.
Чужие объявления/ключ/response tokens не включены в Git или общие логи.

Наличие результата не доказывает полноту покрытия Instagram и не подтверждает
R1–R6. Регион определяется текстовым фильтром, а не проверенным кадастром/
таргетингом. Общий KZ-запрос не дал явных ВКО-упоминаний; региональный запрос
полезнее для нашей очереди. Правильный ad_type для KZ здесь **all**:
отдельный housing_ads не заявлен в country table поставщика.

## Контракт и поведение приложения

Источник `kind=instagram_ads`, target — поисковая фраза. Frontend предлагает
`квартиры Өскемен`; несколько городов не объединяются в одно обязательное
AND-условие. Каждый дополнительный источник/запуск может расходовать запрос.
Клиент не передаёт key/engine/country/provider URL: их определяет backend.

Один сбор:
1. Серверная настройка включена, есть key; транзакционно резервируются обычный
   source lease/fetch counter, общая SearchAPI lease и дневная попытка.
2. Единственный Account API запрос. Неизвестный/нецелый/отрицательный баланс
   блокирует поиск. При remaining<=reserve поискового вызова нет.
3. После Account HTTP — повторная транзакционная проверка владельца source/provider
   lease и времени. До search записывается pendingSearches[runId].
   При `remaining - unsettledAttempts <= reserve` поиск блокируется.
4. Один GET /api/v1/search: engine=meta_ad_library, country=KZ,
   platforms=instagram, ad_type=all, active_status=active. Без API key в URL.
5. До 30 карточек сохраняются как кандидаты после проверки platforms/active/ID/
   доступного текста и прежнего фильтра жилья/ВКО. Дополнительные страницы
   не запрашиваются. Ошибка формата не становится пустой успешной выдачей.
6. Освобождение только своей provider lease. Известный полученный результат
   снимает только свой pending; неизвестный внешний исход сохраняет его.

Account/search host фиксирован `www.searchapi.io`, redirect отключён.
Ключ только Authorization, никогда VITE/JSON ответа/log/source URL.
Отдельные лимиты adapter: до 2 MB распакованного body, connect5 s/read80 s,
контроль потока 85 s между chunks. Локальный JSON/парсер ограничены;
границы времени не являются hard SLA. HTTP/JSON/ключ/квота/сеть/timeout — разные
фиксированные коды SEARCHAPI_*, без provider body. Автоматических повторов нет.

Новая находка:
- contentKind=instagram_ad, originalUrl — canonical Meta Ad Library ID;
- adArchiveId, adActive, platforms, adStartedAt — сохранённые сведения поставщика;
- **publishedAt=null**: начало рекламного показа не подменяет дату исходного поста;
- text — фактический body/card copy, без подстановки вымышленных значений
  в нераскрытые `{{product.*}}` templates;
- media — максимум 12 безопасных HTTPS references image/video/thumbnail.
  Они **не скачиваются**, не рендерятся автоматически и не анализируются AI;
  ссылки могут истекать. Входящий медиа-only материал без текста пока пропускается,
  unreadable в run явно показывает такие/неподходящие записи.
- SHA256 ответа/текста и revisionKey сохраняются как прежде. Для Instagram
  ревизия учитывает также kind/path creative reference без rotating signature/
  CDN host. Это сравнение ссылок, не perceptual/binary hash медиа.

Auto-AI остаётся отдельным opt-in: анализирует доступный текст, не загружает media.
Human review и real→real attach используют прежние проверки; DEMO связывание
запрещено, score не меняется сборщиком/моделью.

## Настройки и резерв

| Backend variable | Default | Назначение |
| --- | --- | --- |
| SEARCHAPI_API_KEY | empty | Только private backend env/Secret Manager |
| SEARCHAPI_ENABLED | false | Явно разрешить даже ручной поиск |
| SEARCHAPI_SCHEDULE_ENABLED | false | Разрешить Meta в регулярном worker отдельно |
| SEARCHAPI_DAILY_LIMIT | 2 | Общие попытки по UTC-day, не на источник |
| SEARCHAPI_CREDIT_RESERVE | 20 | Минимальный остаток; Pydantic запрещает ниже 20 |

Один key/account и одинаковые лимиты у API и Job; состояние блокировок/счётчиков
общее в monitorLimits. Поля searchapi/searchapi-YYYYMMDD не требуют новых indexes.
Счётчик попыток резервируется до HTTP, поэтому ошибки тоже учитываются.
Пауза источника/страница браузера/повтор request не возвращают квоту автоматически.
Резерв защищает запросы этого приложения; параллельные потребители того же
аккаунта вне SAQ не подчиняются его блокировке.

UI status читает **только Firestore**, не вызывает Account/Search API по polling.
Показывается последний баланс **перед** поиском с датой проверки, а не обещание
текущего live balance. На открытие страницы/источника запрос SearchAPI не отправляется.
Достигнутый Meta daily limit пропускается worker, чтобы не блокировать RSS/Telegram.

Для локального backend/.env заполнить private key, SEARCHAPI_ENABLED=true;
SEARCHAPI_SCHEDULE_ENABLED=false оставить до отдельного включения расписания.
Compose передаёт эти поля только backend. При старте ничего не собирается само:
нужен источник и ручной запуск либо opt-in worker.

## Зависшие/неопределённые попытки

Timeout/crash/неизвестный ответ после авторизации search оставляет pendingSearches,
даже если provider lease истечёт. Старый worker не снимает новую lease и не
получает новое разрешение на поиск после потери владения. Учёт pending до нового
HTTP консервативно защищает резерв от позднего выполнения старого процесса.
Возможна ранняя остановка с сохранением большего числа credits, чем 20.

Не удалять pending/счётчики вслепую. Администратор должен остановить/проверить старый
процесс, сверить Account API и private provider history, сохранить аудит и только
после установления исхода выполнить проверяемую administrative transaction.
Не запускать search ради проверки расхода. Публичного recovery endpoint нет.

## Публикация

Codex secret **не попадает автоматически в Cloud Run**. Код внедрён в ветку,
живой API/Hosting/Job этой версии здесь не обновлялись.
[Cloud deployment, Instagram](cloud-deployment.md#8-instagram-searchapi-ручное-включение).
Сначала manual-only, не более одной приёмочной search страницы; до неё проверить
live credits и не расходовать оставшиеся 20. Разрешать schedule — отдельный выбор
владельца после cloud приёмки, с теми же лимитами/аккаунтом.

Справка:
[поиск Meta](https://www.searchapi.io/docs/meta-ad-library-api),
[страны/типы](https://www.searchapi.io/docs/parameters/meta-ad-library/country),
[Account API](https://www.searchapi.io/docs/account-api).
Исторические ограничения прямого доступа:
[первые пробы](instagram-feasibility.md),
[сравнение способов до trial](instagram-access-probes.md).


## Проверки внедрения

- Backend: **431 passed**, из них 28 SearchAPI; Ruff check/format passed.
- Native Firestore SDK/emulator: **14 passed**, включая provider lease/транзакции.
- Frontend: **72 passed**, typecheck и production build passed.
- Chromium: **18 групп / 863 запроса**, без page errors/внешних запросов;
  размеры 1366/375/320, источник → очередь → media links → reserve block.
- Независимый read-only review Codex: blockers не обнаружены; замечание о
  безопасном сообщении при потере ответа исправлено. Это не human GitHub approval.
- Основной JS 545.96 kB / gzip 164.80 kB; прежний large-chunk warning остаётся A-02.

Новые автоматические проверки используют только synthetic MockTransport, fake
identity/MemoryStore и opt-in emulator. Реальных ad fixtures/keys в tests нет.
QA runner удаляет SEARCHAPI_* из дочерней среды и задаёт отдельный synthetic key.
Прежний browser-тест реестра потребовал ожидания завершения навигации при сбросе
поиска перед изменением фильтра; приложение/ожидаемый результат не ослаблялись.

Артефакты текущей среды (не deployment):
`/tmp/saq-meta-live/` — приватные временные ответы и безопасные счётчики,
`/tmp/saq-firestore-integration-u5gfd0wy/`,
`/tmp/saq-instagram-browser-verified/` — явно тестовые screenshots/results.
CI окончательного head смотреть в PR14. Деплой/merge main не выполнялись.
