# Сайт для организаторов: Firebase Hosting + Cloud Run

Frontend публикуется как статическая сборка Vite на Firebase Hosting. API работает
в Cloud Run; организатору нужны ссылка и приватно переданный логин аналитика.
Backend получает Firebase Admin ADC через отдельную прикреплённую service account.
Приватный JSON-файл не нужен Cloud Run и не передаётся организаторам.
Локальные Docker-инструкции остаются доступным способом проверки исходного кода.

Blaze подтверждён владельцем. **15 октября владелец выполнил deployment через
Cloud Shell:** https://saq-qurylys.web.app и
https://saq-qurylys-api-722228028571.europe-west1.run.app.
Начальный образ: `api:20261015-155826`, digest
`sha256:6df8d7aa451fcb4cac034f9ee27176d7c952410ff7bf20b5fe73055d7d6afa1f`.
Вход аналитика, seed, новое объявление, настоящий Gemini на одном русском тексте
и подтверждение R2 (10 → 35/YELLOW) проверены владельцем. Позднее владелец
опубликовал `effb87f` (revision `saq-qurylys-api-00003-sxb`), развернул индексы,
проверил историю/PDF/screenshot flow и сообщил об успешном завершении проверок.
Это результаты владельца на прежней версии, не новая облачная приёмка Codex.

В живой конфигурации выбрана `gemini-3.5-flash-lite`: generateContent прежней
`gemini-2.5-flash-lite` вернул 404 «no longer available to new users», хотя metadata
GET вернул 200. Это наблюдение в данном проекте, не гарантия доступности, качества
или цены модели для другого аккаунта. Модель на сервере выбирается явно, без fallback.

17 октября PR #6 (дизайн), #7 (рекламный след), #11 (диагностика/PDF)
включены в main; код приложения — `2ac51b7`. Позднее владелец сообщил об
обновлении baseline и открытии собранного сайта. Это не проверка MON:
мониторинг из feature-ветки **ещё не опубликован**, Job/Scheduler не настроены.
У процесса Codex отсутствуют Google Cloud ADC/CLI credentials и указанный файл
Firebase credentials. Авторизация в отдельной вкладке Cloud Shell сюда не переносится.
Настройки среды Codex не переносятся в Cloud Run/Hosting автоматически. Команды
ниже выполняет владелец в своём авторизованном Cloud Shell; разделы 1–4 — первоначальная настройка,
раздел 6 — продолжение уже опубликованного проекта.

## 1. Cloud Shell и API

Открыть https://console.cloud.google.com/?project=saq-qurylys → значок `>_`
«Activate Cloud Shell» → подтвердить авторизацию, если Google её запросит.

```bash
gcloud config set project saq-qurylys
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
```

Биллинг — по фактическому использованию; расходы Gemini, Cloud Build, Artifact
Registry/Storage и Cloud Run не следует считать общим фиксированным бюджетом $5.
На Cloud Run используем min instances 0, max instances 1. Это ограничение масштаба,
не денежный hard cap; budget alerts уведомляют, но не останавливают расходы.

## 2. Исходники и права

Взять проверенный commit актуального `main` по `docs/WORK_LOG.md`,
а не старый ZIP G0 или отдельную архивную backend-ветку. Для приватного GitHub использовать штатный GitHub login
в Cloud Shell либо скачать ZIP ветки в GitHub и загрузить **исходники без секретов**
через меню Cloud Shell Upload. Распаковать и перейти в папку с `firebase.json`.
Ключи/`.env` в этот архив не добавлять.

Создать runtime account `saq-api@saq-qurylys.iam.gserviceaccount.com`:

```bash
gcloud iam service-accounts create saq-api --display-name="SAQ API runtime"
gcloud projects add-iam-policy-binding saq-qurylys --member="serviceAccount:saq-api@saq-qurylys.iam.gserviceaccount.com" --role="roles/datastore.user"
gcloud projects add-iam-policy-binding saq-qurylys --member="serviceAccount:saq-api@saq-qurylys.iam.gserviceaccount.com" --role="roles/firebaseauth.viewer"
gcloud storage buckets add-iam-policy-binding gs://saq-qurylys.firebasestorage.app --member="serviceAccount:saq-api@saq-qurylys.iam.gserviceaccount.com" --role="roles/storage.objectAdmin"
```

Права Storage ограничены bucket. Для необязательного metadata-пробника CLI check
дополнительно нужно `storage.buckets.get`, например bucket-scoped
`roles/storage.legacyBucketReader`; без него диагностика metadata может отказать
даже при работающей загрузке. Не выдавать Editor/Owner runtime account.
Firebase Auth Viewer даёт чтение пользователей для check_revoked; смена custom
claims требует отдельных owner/provisioning credentials, не прав runtime сервера.

В Google Cloud Console → Secret Manager создать секрет `saq-gemini-api-key` и
внести ключ Gemini там. Никаких значений ключа в Git, командной строке или чате.
Дать runtime account доступ только к этому секрету:

```bash
gcloud secrets add-iam-policy-binding saq-gemini-api-key --member="serviceAccount:saq-api@saq-qurylys.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

Убедиться, что Firestore и Storage созданы, Email/Password включён. Закрытые
client rules развернуть по `docs/firebase-setup.md` с учётом существующих
клиентов проекта. Индексы — отдельный шаг (публикация Hosting их не создаёт):

```bash
npx firebase-tools@15.34.0 deploy --only firestore:indexes --project saq-qurylys
```

Дождаться готовности **всех нужных индексов** в Firebase Console → Firestore →
Indexes: завершение CLI не означает окончания построения. Не соглашаться удалять
неизвестные индексы других клиентов без проверки. В файле есть индексы auditLogs
для entityId/complexId, с/без DEMO: createdAt DESC и явный __name__ ASC.

DEMO seed и роль аналитика назначает владелец один раз, используя
CLI seed/role из того же документа (локальные owner credentials либо ADC в
авторизованной среде). Публичного endpoint назначения ролей/инициализации нет.
Cloud Shell ADC можно настроить без JSON-ключа:

```bash
gcloud auth application-default login --no-launch-browser --scopes=openid,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/userinfo.email
gcloud auth application-default set-quota-project saq-qurylys
```

Все три scope указаны явно: у владельца gcloud прерывался при изменении набора
scope OAuth-ответом. На странице Google разрешить запрошенные scopes; код вводить
только в терминал. Owner ADC используется для разовой CLI-инициализации;
не выдавать Firebase Auth Admin аккаунту runtime ради назначения одной роли.

## 3. Сборка и Cloud Run

Скопировать `deploy/cloud-run.env.example.yaml` в `deploy/cloud-run.env.yaml`.
Заполнить GEMINI_MODEL реально доступной multimodal-моделью; проверить bucket.
Ключ Gemini в YAML не добавлять. Путь GOOGLE_APPLICATION_CREDENTIALS /
FIREBASE_CREDENTIALS_PATH в Cloud Run не задавать: используется service identity.

```bash
gcloud artifacts repositories create saq-qurylys --repository-format=docker --location=europe-west1
SAQ_IMAGE="europe-west1-docker.pkg.dev/saq-qurylys/saq-qurylys/api:$(date -u +%Y%m%d-%H%M%S)"
gcloud builds submit . --config=deploy/cloudbuild.yaml --substitutions="_IMAGE=$SAQ_IMAGE"
gcloud run deploy saq-qurylys-api --image="$SAQ_IMAGE" --region=europe-west1 --port=8000 --service-account=saq-api@saq-qurylys.iam.gserviceaccount.com --env-vars-file=deploy/cloud-run.env.yaml --set-secrets=GEMINI_API_KEY=saq-gemini-api-key:latest --min-instances=0 --max-instances=1 --concurrency=4 --cpu=1 --memory=1Gi --timeout=120 --allow-unauthenticated
gcloud run services describe saq-qurylys-api --region=europe-west1 --format='value(status.url)'
```

Если repository/service account уже созданы, повторять create не нужно. Cloud
Build использует свой build account; при IAM-ошибке нужно установить конкретный
отказавший principal/permission и выдать ему необходимые build/repository права.
Первоначальную сборку/deployment владелец выполнил успешно. Это не означает,
что команда сработает у другого build account без проверки его прав.
Регион `europe-west1` — выбранный стартовый вариант; при требованиях к размещению
данных или другой локации Firestore согласовать регион до создания ресурсов.

Cloud Run принимает сетевые запросы браузера; FastAPI проверяет Firebase ID token
и роль на каждом business endpoint. `--allow-unauthenticated` относится к сетевому
IAM-вызову Cloud Run, не отменяет auth приложения. `/api/v1/health` публичен. API отвечает
`Cache-Control: no-store`. CORS разрешает два стандартных Hosting origin проекта.

## 4. Сборка сайта и Hosting

В корне создать игнорируемый `.env.production.local` только с public browser config:

```dotenv
VITE_FIREBASE_API_KEY=from_firebase_web_config
VITE_FIREBASE_AUTH_DOMAIN=from_firebase_web_config
VITE_FIREBASE_PROJECT_ID=saq-qurylys
VITE_FIREBASE_APP_ID=from_firebase_web_config
VITE_API_BASE_URL=https://ACTUAL_CLOUD_RUN_SERVICE_URL
```

В VITE_API_BASE_URL вставить реальный origin из предыдущей команды, без `/api/v1`.
В Authentication → Settings → Authorized domains проверить домены
`saq-qurylys.web.app` и `saq-qurylys.firebaseapp.com`.
Нужен Node.js 24 (либо поддерживаемый package.json Node.js); затем:

```bash
cd frontend
npm ci
npm run build:hosting
cd ..
npx firebase-tools@15.34.0 login --no-localhost
npx firebase-tools@15.34.0 deploy --only hosting --project saq-qurylys
```

Hosting использует `frontend/dist` и SPA fallback из firebase.json.
`build:hosting` останавливает сборку без обязательной browser config/HTTPS API origin;
он не делает облачных запросов и не подтверждает доступность введённого адреса.
API вызывается напрямую по HTTPS Cloud Run с Bearer token; публичный ключ Firebase не является
Admin credential. Gemini/Admin secrets в Vite не попадают.
Прямой вызов нужен из-за 60-секундного лимита dynamic rewrites Hosting, тогда как
клиент допускает до 90 секунд анализа. CORS custom domain нужно добавить отдельно.

## 5. Проверка до передачи ссылки

- Реальный URL Cloud Run: health JSON, business запрос без token → 401.
- Сайт Hosting: вход созданным аналитиком с назначенной ролью, восемь DEMO ЖК.
- Новый RU/KZ текст/скриншот → настоящий Gemini → review источника → R2 → сигнал/PDF.
- Обновить страницу `/complexes/{id}` напрямую: SPA должна открыться без 404.
- Выйти: данные защищённых API не должны читаться без токена.
- Выключить компьютер владельца и повторить вход с другого устройства.

Фактические URL/image и частичные результаты владельца указаны в начале документа.
Незавершённые пункты нельзя считать прошедшими по локальным tests/build.

## 6. Обновление существующего сайта из проверенного main

Команды публикации в живом проекте Codex здесь **не выполнял**: для них нужен
авторизованный Google Cloud Shell владельца. Исходники этой версии —
`1373d0daec5939df8211d10d6ba52721b4988221`: дизайн #6, рекламный след #7,
исправления API/PDF #11 и распределение команды #10. Секреты в исходники
не добавлять; Cloud Run сохраняет настроенную service identity и Secret Manager.

В Cloud Shell получить свежие исходники приватного GitHub можно через штатную
авторизацию `gh` (если login уже есть, повторять его не нужно):

```bash
gh auth status || gh auth login --hostname github.com --git-protocol https --web
SAQ_RELEASE_SHA=1373d0daec5939df8211d10d6ba52721b4988221
SAQ_RELEASE_DIR="$HOME/saq-release-$SAQ_RELEASE_SHA"
gh repo clone arturk0-0/3a-saq-qurylys "$SAQ_RELEASE_DIR"
cd "$SAQ_RELEASE_DIR"
git checkout --detach "$SAQ_RELEASE_SHA"
git rev-parse HEAD
```

Последний вывод должен совпасть с `SAQ_RELEASE_SHA`. При повторном запуске
используйте уже созданный каталог только после проверки чистого `git status`
и нужного SHA; не перезаписывайте изменённые файлы. Если `gh` недоступен,
скачать [ZIP этого commit](https://github.com/arturk0-0/3a-saq-qurylys/archive/1373d0daec5939df8211d10d6ba52721b4988221.zip)
в GitHub, загрузить через Cloud Shell Upload и распаковать в новую папку.
Войти в корень с `firebase.json` и задать тот же `SAQ_RELEASE_SHA`.
Старый каталог `saq-release-effb87f` новой версии не содержит.

### 6.1 Индексы и диагностика истории

Индексы ранее опубликованы владельцем, история на `effb87f` уже проверена.
Новая версия не меняет `firestore.indexes.json`: не нужно повторять index deploy
только ради обновления API/Hosting. Если индексы меняются в следующей версии
или API сообщает об отсутствующем индексе, выполнить раздел 2 и дождаться
готовности в Console. На сайте открыть историю и «Повторить». Если ошибка ушла,
это подтверждает исправление deployment, но не завершает проверки PDF/Storage.
Если не ушла — получить безопасные диагностические записи (не все логи подряд):

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="saq-qurylys-api" AND (textPayload:"Firestore query failed:" OR textPayload:"Gemini request failed:" OR textPayload:"PDF render failed:" OR textPayload:"Request failed:")' --project=saq-qurylys --freshness=1h --limit=30 --format='table(timestamp,textPayload)'
```

После обновления backend `FIRESTORE_INDEX_REQUIRED` точно указывает на ответ
провайдера о missing/building query index. Другой FailedPrecondition, IAM или
network error этим кодом не помечается. Отсутствие записи в логах не доказывает,
что индекс есть: сопоставить время запроса, service/revision и requestId ответа.
Новая версия пишет `Request failed: request_id=… code=…` для 5xx/429 без заголовков,
body или текста исключений; requestId совпадает с JSON/X-Request-ID ответа.

### 6.2 Собрать и обновить только backend

В корне проверенных исходников в Cloud Shell:

```bash
gcloud config set project saq-qurylys
SAQ_IMAGE="europe-west1-docker.pkg.dev/saq-qurylys/saq-qurylys/api:release-${SAQ_RELEASE_SHA:?Сначала выполните раздел 6}"
gcloud builds submit . --project=saq-qurylys --config=deploy/cloudbuild.yaml --substitutions="_IMAGE=$SAQ_IMAGE"
```

**Только после STATUS: SUCCESS**:

```bash
gcloud run services update saq-qurylys-api --project=saq-qurylys --region=europe-west1 --image="$SAQ_IMAGE"
```

Этот update сохраняет настроенные environment, Secret Manager references,
runtime identity и ресурсные лимиты. Не копировать пустой env example поверх
рабочих настроек; не использовать `--set-env-vars`, который заменяет набор.
API и Hosting публикуются из одного проверенного SHA; после проверки API
выполнить раздел 6.4 для Hosting. Не брать отдельную старую backend-ветку.
Сохранить image/digest, commit и выведенное имя новой revision для проверки/отката.

Если нужно явно сменить модель после проверки доступности/цены владельцем:

```bash
gcloud run services update saq-qurylys-api --region=europe-west1 --update-env-vars=GEMINI_MODEL=gemini-3.5-flash-lite
```

Пример runtime YAML оставлен без default model, чтобы не обещать доступность.
Readiness `--online` делает только metadata GET, не тестирует платную генерацию.
Даже HTTP 200 metadata и наличие generateContent в supportedGenerationMethods
не гарантируют возможность вызова. Дневные счётчики учитывают попытки анализа,
включая неуспешные; один requestId повторно не генерирует и не списывает счётчик.
Это лимиты приложения, не денежный hard cap Google Cloud/Gemini.

### 6.3 Проверки владельца после обновления

```bash
curl --fail-with-body --max-time 60 https://saq-qurylys-api-722228028571.europe-west1.run.app/api/v1/health
curl -sS -o /dev/null -w '%{http_code}\n' https://saq-qurylys-api-722228028571.europe-west1.run.app/api/v1/complexes
```

Ожидание: health JSON status=ok, а второй запрос без token — 401. Они не проверяют
доступ к Firestore/Storage/Gemini. Затем в браузере:

1. История ЖК и сигнала открывается, «Далее» не повторяет/теряет события.
2. Новый DEMO RU/KZ текст и PNG/JPEG screenshot обрабатываются настоящим Gemini.
   Это платные вызовы; выполнять явно и ограниченно, фиксировать модель/результат.
3. AI review и evidence review сами не меняют score; подтверждённый R2 добавляет
   25 один раз. Проверить источник/оригинальный файл, без публичной Storage-ссылки.
4. Draft → submit → return с причиной → submit → confirm; причины/автор/время
   видны в истории. Изменение ЖК блокирует confirm старого snapshot (409).
5. Скачать PDF из подтверждённого сигнала: оценка/источники/решение/DEMO/кириллица
   читаемы. PDF_BUSY (429) означает занятый рендерер, PDF_RENDER_FAILED (503) —
   сбой системного рендера; повтор не должен менять данные сигнала.
6. После выхода прямые API-файлы/report/revisions/history недоступны (401).
   Firestore/Storage client rules и bucket IAM проверять отдельно от API auth:
   локальные тесты их deployment не подтверждают. Проверить также второе устройство.

Диагностические API-коды Gemini: AI_NOT_CONFIGURED (нет key/model), AI_CREDENTIALS
(неверный key/401), AI_ACCESS_DENIED (403/API access/key restrictions),
AI_MODEL_UNAVAILABLE (404 generation), AI_PROVIDER_QUOTA (429), AI_TIMEOUT,
AI_NETWORK, AI_TEMPORARY (5xx provider), AI_REQUEST_REJECTED (другой отказ запроса),
AI_INVALID_RESPONSE (502, неверный/незавершённый JSON/цитата). Возвращаются только
фиксированные безопасные сообщения, provider body не передаётся клиенту.
Frontend-ветка может пока отображать общий текст: код виден в JSON ответа Network;
UI-сопоставление кодов — отдельный интеграционный шаг с владельцем frontend.

После публикации ветки `fix/B-03-04-ai-diagnostics-pdf` отказ валидации Gemini
содержит безопасную внутреннюю причину и серверный `request_id`; перечень причин
есть в [методологии AI](ai-methodology.md#диагностика-отклонённого-ответа).
В Cloud Shell найти конкретное обращение можно командой ниже: заменить
`REPLACE_WITH_REQUEST_UUID` на UUID из сообщения приложения, без других данных.

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="saq-qurylys-api" AND textPayload:"Gemini request failed:" AND textPayload:"request_id=REPLACE_WITH_REQUEST_UUID"' --project=saq-qurylys --freshness=1h --limit=10 --format='table(timestamp,textPayload)'
```

Лог содержит только фиксированные коды/метаданные, без исходного объявления и
ответа провайдера. Для HTTP/сетевых отказов тот же UUID связывает безопасную
строку Gemini с ответом приложения. Старые revision не содержат новые причины:
публикация не устанавливает причину исторического сбоя задним числом.
Не запускайте платную генерацию только ради появления лога; используйте UUID
следующего обычного анализа, если он завершился ошибкой.

Откат backend при необходимости: выбрать **предыдущую проверенную** revision,
не угадывать latest. Не откатывать Firebase данные или секреты:

```bash
gcloud run revisions list --service=saq-qurylys-api --region=europe-west1
gcloud run services update-traffic saq-qurylys-api --region=europe-west1 --to-revisions=PREVIOUS_REVIEWED_REVISION=100
```

PREVIOUS_REVIEWED_REVISION заменить именем из списка. У первой публикации была
revision `saq-qurylys-api-00001-b6j`, но позднее менялась модель, поэтому она не
считается автоматически подходящей для отката. Откат трафика также не доказывает,
что model/key старой revision ещё доступны. Cloud Run, сборки, образы, Storage,
Firestore и Gemini тарифицируются отдельно; budget alerts не останавливают расходы.

Источники: [Hosting/Cloud Run timeout](https://firebase.google.com/docs/hosting/cloud-run),
[Cloud Run service identity](https://cloud.google.com/run/docs/configuring/services/service-identity).

### 6.4 Обновить Hosting из того же checkout

После успешного Cloud Run update и health-проверки раздела 6.3, из корня
checkout раздела 6. Эта команда получает **только публичную browser config**
у существующего Hosting-сайта, проверяет project ID и передаёт её процессу
сборки; ключи Admin/Gemini не нужны. Значения не печатаются и файл `.env`
не создаётся/не перезаписывается. Для другого проекта сначала согласовать URL.

```bash
cd frontend
npm ci
python3 - <<'PY'
import json
import os
import subprocess
import urllib.request

with urllib.request.urlopen('https://saq-qurylys.web.app/__/firebase/init.json', timeout=30) as response:
    config = json.load(response)
assert config.get('projectId') == 'saq-qurylys', 'Unexpected Firebase project'
fields = {
    'VITE_FIREBASE_API_KEY': 'apiKey',
    'VITE_FIREBASE_AUTH_DOMAIN': 'authDomain',
    'VITE_FIREBASE_PROJECT_ID': 'projectId',
    'VITE_FIREBASE_APP_ID': 'appId',
}
build_env = os.environ.copy()
for variable, field in fields.items():
    value = config.get(field)
    assert isinstance(value, str) and value, 'Missing public Firebase config'
    build_env[variable] = value
build_env['VITE_API_BASE_URL'] = 'https://saq-qurylys-api-722228028571.europe-west1.run.app'
subprocess.run(['npm', 'run', 'build:hosting'], env=build_env, check=True)
PY
```

**Только после успешной сборки**, из `frontend/` вернуться в корень и опубликовать:

```bash
cd ..
npx firebase-tools@15.34.0 deploy --only hosting --project saq-qurylys
```

Если CLI сообщает об отсутствии авторизации, выполнить в Cloud Shell:

```bash
npx firebase-tools@15.34.0 login --no-localhost
```

Затем повторить только Hosting deploy. Не вставлять
OAuth-коды/токены в чат. Затем открыть https://saq-qurylys.web.app и обновить страницу;
проверить новый дизайн, «Рекламный след», прежний путь скриншот → AI → ручной R2 → PDF.
Это ещё не выполненная облачная проверка. Новые Gemini-вызовы платные;
не выполнять их автоматически ради smoke-проверки.

## 7. Мониторинг: Job и расписание

Это последующий MON-09, **не выполненный Codex deployment**. Сначала проверить/
включить MON PR, выбрать его полный reviewed SHA и собрать новый образ по
разделу 6, **заменив его закреплённый baseline SAQ_RELEASE_SHA на выбранный
полный MON SHA**. Не выполнять старый checkout/tag из примера как новый MON-релиз.
Старый baseline-образ не содержит CLI. Опубликовать API/frontend из
того же SHA. Instagram-таргет эти команды не подключают.

1. Развернуть `firestore.indexes.json` этой версии и дождаться ready в Console.
   Добавлены monitorItems (с/без status), monitorRuns и monitorEvents/entityId:
   createdAt DESC, __name__ ASC. Успех эмулятора не проверяет production indexes.
2. Скопировать `deploy/monitor-job.env.example.yaml` в
   `deploy/monitor-job.env.yaml` (ignored). Сверить project, DEMO-only и **одинаковые**
   AI/fetch-квоты с API. Не менять работающий GEMINI_MODEL/secret автоматически.
   Для сбора без AI можно оставить GEMINI_MODEL пустым, autoAnalyze=false.
3. Ниже команды первоначального создания в авторизованном Cloud Shell.
   `SAQ_MON_IMAGE` должен указывать **реально собранный и проверенный** MON-образ,
   не буквальный placeholder. Runtime account уже существует и читает Firestore;
   ADC передаётся через service identity, JSON-ключи не нужны.

```bash
gcloud config set project saq-qurylys
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com
SAQ_MON_IMAGE='europe-west1-docker.pkg.dev/saq-qurylys/saq-qurylys/api:REPLACE_WITH_REVIEWED_MON_IMAGE'
gcloud run jobs create saq-qurylys-monitor \
  --project=saq-qurylys --region=europe-west1 \
  --image="$SAQ_MON_IMAGE" \
  --command=.venv/bin/python --args=-m,app.cli.monitor \
  --service-account=saq-api@saq-qurylys.iam.gserviceaccount.com \
  --env-vars-file=deploy/monitor-job.env.yaml \
  --tasks=1 --parallelism=1 --max-retries=0 \
  --task-timeout=900s --cpu=1 --memory=1Gi
```

Для уже существующего Job использовать `gcloud run jobs update`, а не create.
Для **осознанного включения AI** выбрать ту же доступную модель в приватном YAML
и добавить существующий Secret Manager reference (ключ не выводить):

```bash
gcloud run jobs update saq-qurylys-monitor \
  --project=saq-qurylys --region=europe-west1 \
  --env-vars-file=deploy/monitor-job.env.yaml \
  --set-secrets=GEMINI_API_KEY=saq-gemini-api-key:latest
```

AutoAnalyze у каждого источника всё равно остаётся выключенным до явного opt-in.
Secret accessor требуется только на этот секрет (runtime account уже применялся
для API). Не копировать Admin JSON/API key в image/YAML или browser variables.

4. В UI создать один публичный источник, оставить auto-AI выключенным. Выполнить
   одну проверочную batch и убедиться, что execution завершился успешно,
   появились monitorRuns, heartbeat и ожидаемый текст/либо корректная ошибка:

```bash
gcloud run jobs execute saq-qurylys-monitor --project=saq-qurylys --region=europe-west1 --wait
```

5. Только после приёмки включить периодический запуск. Отдельный Scheduler
   caller получает **job-scoped** run.invoker; runtime и caller — разные роли.

```bash
gcloud iam service-accounts create saq-monitor-scheduler --project=saq-qurylys --display-name="SAQ monitoring schedule caller"
gcloud run jobs add-iam-policy-binding saq-qurylys-monitor \
  --project=saq-qurylys --region=europe-west1 \
  --member=serviceAccount:saq-monitor-scheduler@saq-qurylys.iam.gserviceaccount.com \
  --role=roles/run.invoker
gcloud scheduler jobs create http saq-monitor-every-15-min \
  --project=saq-qurylys --location=europe-west1 \
  --schedule='*/15 * * * *' --time-zone=Asia/Qyzylorda \
  --uri='https://run.googleapis.com/v2/projects/saq-qurylys/locations/europe-west1/jobs/saq-qurylys-monitor:run' \
  --http-method=POST --headers=Content-Type=application/json --message-body='{}' \
  --oauth-service-account-email=saq-monitor-scheduler@saq-qurylys.iam.gserviceaccount.com \
  --oauth-token-scope=https://www.googleapis.com/auth/cloud-platform \
  --max-retry-attempts=0 --attempt-deadline=30s
```

Для Google API endpoint используется OAuth, не OIDC. Создающий schedule principal
должен иметь actAs на caller account; стандартный Scheduler service agent должен
сохранить роль Cloud Scheduler Service Agent. Не выдавать Owner/Editor runtime.
Для существующих caller/schedule не повторять create; inspect/update после
сверки параметров. Job execution success проверяется отдельно от HTTP-успеха
Scheduler: API возвращает операцию запуска раньше окончания сбора.

Расписание раз в 15 минут проверяет до трёх due-источников за batch. Интервал
источника — минимальная задержка, не SLA: очередь/пауза/квота могут её увеличить.
100 fetch/UTC-day — общий предел, не 100 на источник; при 20 источниках он
может закончиться до конца дня. Ошибки также расходуют fetch quota.
Повышать предел только после оценки расходов и покрытия. Cloud Run Job,
Scheduler, Firestore/Storage и Gemini имеют собственное тарифицирование;
операционные квоты и budget alerts не являются денежным hard cap.

Проверка MON-09: два штатных tick при закрытом браузере → дедуп без потери notes →
ручной expert review → доступ без token отклоняется → авто-AI остаётся opt-in →
после deployment нет незавершённых indexes. Реальную привязку/факторы/PDF
проверять только с документированным real registry в согласованной среде;
не смешивать с seed DEMO. Instagram остаётся отдельным MON-IG-02.

Чтобы остановить автоматические запуски (сохранённые данные не удаляются):

```bash
gcloud scheduler jobs pause saq-monitor-every-15-min --project=saq-qurylys --location=europe-west1
```

Уже выполняющееся execution это не отменяет. Восстановление lease/AI и другие
ограничения: [monitoring.md](monitoring.md#восстановление-после-прерывания).
