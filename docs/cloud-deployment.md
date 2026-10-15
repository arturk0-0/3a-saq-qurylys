# Сайт для организаторов: Firebase Hosting + Cloud Run

Frontend публикуется как статическая сборка Vite на Firebase Hosting. API работает
в Cloud Run; организатору нужны ссылка и приватно переданный логин аналитика.
Backend получает Firebase Admin ADC через отдельную прикреплённую service account.
Приватный JSON-файл не нужен Cloud Run и не передаётся организаторам.
Локальные Docker-инструкции остаются доступным способом проверки исходного кода.

Blaze подтверждён владельцем. Реальный deployment **пока не выполнен**: у процесса
Codex нет авторизованного gcloud/Firebase CLI. Настройки среды Codex не переносятся
автоматически в Cloud Run или в сборку Hosting. Следующие операции выполняет
владелец в Google Cloud Shell, где Google запрашивает его авторизацию напрямую.

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

Взять актуальную feature-ветку по `docs/WORK_LOG.md`, включающую предыдущие этапы,
а не старый ZIP G0/main. Для приватного GitHub использовать штатный GitHub login
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
client rules/индексы развернуть по `docs/firebase-setup.md` с учётом существующих
клиентов проекта. DEMO seed и роль аналитика назначает владелец один раз, используя
CLI seed/role из того же документа (локальные owner credentials либо ADC в
авторизованной среде). Публичного endpoint назначения ролей/инициализации нет.

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
Эти облачные IAM-команды здесь не выполнялись и не считаются проверенными.
Регион `europe-west1` — выбранный стартовый вариант; при требованиях к размещению
данных или другой локации Firestore согласовать регион до создания ресурсов.

Cloud Run принимает сетевые запросы браузера; FastAPI проверяет Firebase ID token
и роль на каждом business endpoint. `--allow-unauthenticated` относится к сетевому
IAM-вызову Cloud Run, не отменяет auth приложения. `/health` публичен. API отвечает
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

Фактические URL, commit/image, дата и результаты фиксируются после реального
deployment. Локальные tests/build не доказывают рабочие IAM, billing или deployment.

Источники: [Hosting/Cloud Run timeout](https://firebase.google.com/docs/hosting/cloud-run),
[Cloud Run service identity](https://cloud.google.com/run/docs/configuring/services/service-identity).
