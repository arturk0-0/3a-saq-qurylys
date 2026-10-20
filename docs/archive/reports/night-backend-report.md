# Backend reliability — ночная задача 15 октября 2026

Ветка: `fix/backend-demo-reliability`. База: `dbeecb3`
(`feat/DEPLOY-01-hosting-cloud-run`). Начало: 16:49 UTC; предельное время
работы — 21:49 UTC. Изменения только в разрешённой backend/deploy/docs области.
Frontend независимо ведёт другой участник. Main и живая инфраструктура не меняются.

## Подтверждённое состояние перед работой

- Владелец развернул Hosting: https://saq-qurylys.web.app и Cloud Run:
  https://saq-qurylys-api-722228028571.europe-west1.run.app.
- По результатам владельца работают вход, DEMO seed, новое объявление,
  реальный анализ Gemini и отдельное подтверждение R2: 10 → 35/YELLOW.
- Metadata GET для `gemini-2.5-flash-lite` вернул 200, но generateContent — 404:
  модель недоступна новым пользователям. После выбора владельцем
  `gemini-3.5-flash-lite` анализ завершился успешно. Это проверка одного текста,
  не измерение качества/стоимости или проверка скриншотов.
- История сигнала показала общую ошибку. Причина не установлена; deployment
  Firestore indexes и облачные PDF/Storage/screenshot проверки не подтверждены.
- В Codex нет подтверждённых owner credentials Cloud Shell. Платных AI-запросов
  и изменений живого проекта в этой задаче не будет.

## Ход работы и продолжение

1. Проверены удалённые heads: feature-база `dbeecb3`, main `0f7c23a`.
2. Изучены AGENTS, PROJECT_SPEC, DEVELOPMENT_PLAN, WORK_LOG и существующий код.
3. Baseline: 140 passed / 4 failed. Все четыре сбоя в readiness-тестах:
   `_env_file=None` отключает dotenv, но не настройки процесса. Тестовый helper
   теперь явно задаёт пустые credentials/model/bucket и выключенный Firebase;
   настройки рабочего приложения не менялись.
4. Готова классификация Gemini: `AI_NOT_CONFIGURED`, `AI_CREDENTIALS`,
   `AI_ACCESS_DENIED`, `AI_MODEL_UNAVAILABLE`, `AI_PROVIDER_QUOTA`, `AI_TIMEOUT`,
   `AI_NETWORK`, `AI_TEMPORARY`, `AI_REQUEST_REJECTED`, `AI_INVALID_RESPONSE`.
   Логи содержат только фиксированный код/HTTP-статус; provider body, exception
   text, source text, ключи и URL не выводятся. Нет fallback-модели; один повтор
   только явных 502/503/504, без повтора timeout/неопределённого сетевого сбоя.
   Некорректные формы JSON-конверта больше не приводят к необработанному 500.
   Readiness прямо говорит: успешная metadata не подтверждает generateContent.
5. Проверка этапа: 61 passed (Gemini errors / analysis / readiness / evaluation),
   Ruff по изменённым файлам прошёл. Только MockTransport/тестовые адаптеры.
6. Проверены реальные protobuf-запросы Firestore SDK с заменённым stream RPC:
   обе истории (entityId/complexId), DEMO/non-DEMO фильтры, createdAt DESC +
   document name ASC, курсор из даты и DocumentReference, limit+1. Все четыре
   запроса соответствуют существующим определениям `firestore.indexes.json`;
   лишние индексы не добавлялись. Это не проверка фактического deployment индексов.
7. Исправлен подтверждённый edge case: курсор на audit-документ без createdAt
   раньше давал KeyError/500, теперь 409 с предложением обновить страницу.
   Удалённый курсор, другой сигнал или non-DEMO scope также отклоняются.
   Missing/building-index FailedPrecondition получает `FIRESTORE_INDEX_REQUIRED`
   (503), без provider body/console URL. Другие precondition/permission/network
   ошибки не объявляются отсутствием индекса.
8. Добавлены API-проверки tie timestamps и страниц без повторов, изоляции историй,
   неизменности аудита при чтении, отсутствующих/скрытых сигналов, приватности
   revisions/report/history, typed index error с requestId/no-store и auth.
   Проверка этапа: 52 passed (Firestore queries / workspace / signals), Ruff прошёл.
9. PDF: OSError/RuntimeError рендерера теперь дают безопасный `PDF_RENDER_FAILED`
   (503) вместо общего 500; слот рендеринга освобождается и данные не меняются.
   Проверены занятые слоты (429 без запуска рендера), запрет local/network/data
   resources, инертность пользовательской HTML/CSS-разметки, attachment/nosniff,
   реальные PDF-байты, старый снимок после изменения ЖК и новый после resubmit.
   Серверные переходы draft → pending → returned → pending → confirmed и
   неизменяемые revisions проходили существующий тест и продолжают проходить.
10. Проверены screenshot bytes/MIME/provenance через MockTransport: источник
    остаётся proposed, без reviewer и без подтверждения платежа; это не оценка OCR.
    Non-DEMO файл скрыт до обращения к Storage. Ошибки модели/ключа/прав/квоты
    сохраняют только errorCode, не меняют факторы и не вызывают повторную генерацию
    при повторном requestId; дневной счётчик расходуется один раз.
11. Проверка этапа: 40 passed (signals / full vertical flow / analysis), Ruff прошёл.
    Начата сборка локального backend Docker-образа. Следующее: проверка контейнера,
    итоговый suite и deployment-инструкции. В живом проекте ничего не менялось.

## Итог проверки

- Backend: **203 passed**, Ruff `app tests`, `ruff format --check .` (65 файлов)
  и compileall прошли. Один существующий
  StarletteDeprecationWarning о httpx TestClient; зависимости/lockfile не менялись.
- Docker build прошёл с frozen lockfile. Первая попытка не имела доступа к
  deb.debian.org:80 из build sandbox; повтор со штатными proxy build args/host
  network прошёл. TLS и подписи пакетов не отключались, Dockerfile не менялся.
- Финальный локальный image: `saq-backend-reliability:night`, ID
  `sha256:5fd1ce3d8617ebb5aee5151685eebf5b328807aa3390498c206aef7e245bdc4a`.
  Это локальный образ, не Artifact Registry/Cloud Run deployment.
- В образе (non-root, read-only root filesystem, `--network=none`) запущен Uvicorn:
  health 200, закрытые registry/history/revisions/report/file без token дают 401,
  no-store и точный CORS проверены. Полный API flow нового объявления → AI
  гипотеза → ручной source/factor review → 35 → confirmed signal → настоящий
  WeasyPrint PDF прошёл с **явными MemoryStore/MockTransport**, без Google-запросов.
- Отдельный реальный PDF с русским и казахским текстом сгенерирован в образе;
  pdftotext подтвердил ӘҒҚҢӨҰҮҺІ, DEMO, score 70/100, источники и reviewer.
  Временный артефакт: `/tmp/saq-night-artifacts/kazakh-demo.pdf` (не коммитится).
- Для 5xx/429 API пишет фиксированный код и requestId, совпадающий с JSON и
  X-Request-ID; не пишет body, headers, токены или текст исключения. Отдельный тест
  проверяет, что тестовый токен/объявление в лог не попадают.
- Frontend, R1–R6, API payload schemas, dependencies, Firebase rules, main и
  живая инфраструктура не изменены. Индексы уже соответствовали запросам;
  менять определения без причины не потребовалось.

## Что остаётся владельцу / другому участнику

1. Review этой ветки и зелёный CI через GitHub; сам факт локальных тестов не CI.
   Backend-PR направлять в `feat/DEPLOY-01-hosting-cloud-run`, чтобы не включать
   в его diff всю цепочку feature-веток относительно старого main.
2. История в живом проекте всё ещё требует проверки: развернуть существующие
   индексы, дождаться готовности, повторить запрос и при ошибке прочитать только
   диагностические логи. Причина исходного 503 **не установлена** этой задачей.
3. Проверить реальные screenshot upload/download и Gemini RU/KZ/image, PDF в
   Cloud Run, client rules/bucket IAM, второе устройство. Платные запросы выполняет
   владелец явно; эти проверки за ночь не имитировались.
4. Согласовать frontend-описания новых API error codes с участником frontend;
   пока текущий UI может показывать общий текст для неизвестного кода.
5. Никакие release gates/checklist не отмечены как пройденные и не слиты в main.

## Повторить локальные проверки

```bash
cd backend
uv run --frozen pytest -q
uv run --frozen ruff check app tests
uv run --frozen ruff format --check .
uv run --frozen python -m compileall -q app
cd ..
docker build --tag saq-backend-reliability:night backend
docker run --rm --network=none --read-only --tmpfs /tmp:rw,mode=1777 --env PYTHONPATH=/tmp/saq-tests:/app --env XDG_CACHE_HOME=/tmp/saq-cache --mount type=bind,src="$PWD/backend/tests",dst=/tmp/saq-tests/tests,readonly saq-backend-reliability:night .venv/bin/python -c 'from tests.test_vertical_flow import test_new_ad_to_reviewed_factor_signal_and_pdf; test_new_ad_to_reviewed_factor_signal_and_pdf(); print("Mocked vertical flow and native PDF: passed")'
```

В Codex использовать writable `UV_CACHE_DIR=/tmp/saq-uv-cache`. Если build sandbox
требует прокси, передать штатные HTTP_PROXY/HTTPS_PROXY/http_proxy/https_proxy/
NO_PROXY через одноимённые `--build-arg`, host network при необходимости и
`--secret id=custom_ca,src="$SSL_CERT_FILE"` при наличии trust bundle. Не отключать
TLS/signature verification; эти настройки машины не переносить в runtime Google.

## Публикация после review — только владелец, не выполнялась Codex

В Cloud Shell взять **актуальную эту ветку**, а не исходный ZIP dbeecb3/main.
Из корня исходников с `deploy/cloudbuild.yaml`:

```bash
npx firebase-tools@15.34.0 deploy --only firestore:indexes --project saq-qurylys
```

Дождаться готовности индексов в Firebase Console; создание асинхронное. Затем:

```bash
SAQ_IMAGE="europe-west1-docker.pkg.dev/saq-qurylys/saq-qurylys/api:backend-reliability-$(date -u +%Y%m%d-%H%M%S)"
gcloud builds submit . --config=deploy/cloudbuild.yaml --substitutions="_IMAGE=$SAQ_IMAGE"
```

Только после SUCCESS:

```bash
gcloud run services update saq-qurylys-api --region=europe-west1 --image="$SAQ_IMAGE"
```

Сохраняет текущую модель/Secret Manager/identity/ресурсы. Hosting из этой backend
ветки не публиковать поверх параллельного frontend. Логи, проверки и откат:
[cloud-deployment.md, раздел 6](../../cloud-deployment.md#6-обновление-существующего-сайта-из-проверенного-main).

Промежуточные коммиты, отправленные по ходу задачи: `19f6864` (handoff), `ca18739`
(Gemini), `18632b7` (история), `0827507` (PDF/приватность). Финальный HEAD смотреть
в GitHub/`git rev-parse HEAD`; документация и correlation log добавлены следующим
коммитом. Следующее действие — review/ручная облачная проверка, не новая реализация
уже существующих модулей по старым незакрытым чекбоксам.

PR создан: https://github.com/arturk0-0/3a-saq-qurylys/pull/1
(base `feat/DEPLOY-01-hosting-cloud-run`, head `fix/backend-demo-reliability`).
Результат CI смотреть в Checks этого PR; локальные проверки выше не заменяют CI
или второго reviewer. GitHub API создания PR в этой сессии доступен, в отличие
от исторического ограничения в WORK_LOG. Статус main не менялся.
