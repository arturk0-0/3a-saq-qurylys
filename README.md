# SAQ QURYLYS

Внутреннее приложение для аналитиков ВКО: проверка потенциальных рисков в рекламе
строящихся ЖК. Система поддерживает решение человека и не устанавливает незаконность.
Контекст: [AGENTS.md](AGENTS.md), [спецификация](docs/PROJECT_SPEC.md),
[план разработки](docs/DEVELOPMENT_PLAN.md).

## Текущий этап

Готовы чистый скоринг R1–R6, валидируемые модели доказательств, DEMO-набор из 8 ЖК и
12 объявлений, Firebase Admin и вход через Firebase Authentication. Защищённые запросы
требуют проверенный token с ролью analyst/admin. Без настройки Firebase отображается
экран подключения среды. Реальный вход в облачный проект ещё требует credentials.

Настройка: [Firebase и доступ аналитика](docs/firebase-setup.md).
Правила: [R1–R6](docs/risk-rules.md). Данные: [DEMO seed](data/seed/README.md).
Ход реализации и ограничения: [WORK_LOG](docs/WORK_LOG.md).

## Основа G0

React + TypeScript (strict) + Vite, Tailwind CSS, базовый Button shadcn/ui и React Router.
Навигация: обзор, реестр ЖК, объявления, сигналы. Рабочие разделы ещё не реализованы.
Обзор проверяет настоящий FastAPI через Vite proxy, сообщает об ошибках и позволяет
повторить запрос. API предоставляет `GET /api/v1/health`, настройки CORS, ошибки
`{code, message, requestId}` и заголовок `X-Request-ID`.

Бизнес-страницы, Gemini, карта и PDF находятся на следующих этапах реализации.
Health проверяет процесс API, а не Firebase или Gemini. A/B/C проверены на синтетических данных.

## Запуск через Docker

Требуются Docker Engine и Docker Compose v2. Из корня репозитория:

```bash
cp .env.example .env
docker compose up --build --wait
```

UI: `http://localhost:5173`, API: `http://localhost:8000/api/v1/health`,
OpenAPI: `http://localhost:8000/docs`. Адреса относятся к компьютеру, где запущен Compose.
Порты ограничены loopback. Панель cloud onboarding не предоставляет доступ к этим адресам.
Ожидаемый health: `{"status":"ok","service":"saq-qurylys-api"}`.
Без browser Firebase config появится экран настройки. Остановка: `docker compose down`.
Compose запускает dev-сервер Vite; это локальная среда, не публичный deployment.
После изменения исходников пересоберите контейнеры той же командой.
При сборке за HTTPS-прокси Docker должен иметь доступ к DNS и прокси; передавайте
`HTTP_PROXY`/`HTTPS_PROXY` через стандартные build args. Dockerfile поддерживает
необязательный BuildKit secret `custom_ca` с доверенным CA bundle для pip/uv/npm.
Bundle используется только во время установки и не сохраняется в образе.
Не отключайте проверку TLS при настройке прокси.

## Запуск без Docker

Требуются Python 3.12, [uv](https://docs.astral.sh/uv/getting-started/installation/)
(проверено с 0.12.23), Node.js 24 LTS и npm. Зависимости зафиксированы в `uv.lock`
и `package-lock.json`. Из корня скопируйте `.env.example` в `.env`.

В первом терминале:

```bash
cd backend
uv sync --frozen
uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Во втором:

```bash
cd frontend
npm ci
npm run dev
```

Vite передаёт `/api` на `http://127.0.0.1:8000`. Корневой `.env` позволяет переопределить
`API_PROXY_TARGET`; Docker задаёт `http://backend:8000`.
`CORS_ORIGINS` — JSON-массив явных HTTP(S) origin без путей и wildcard;
по умолчанию разрешены `http://localhost:5173` и `http://127.0.0.1:5173`.
Backend читает корневой `.env` при запуске из `backend/`; неверные настройки останавливают запуск.

## Проверки

В `backend/`:

```bash
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
```

В `frontend/`:

```bash
npm test
npm run build
```

Сборка включает `npm run typecheck`. GitHub Actions повторяет проверки и запуск Compose.
Smoke-проверка работающих сервисов:

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:5173/api/v1/health
```

## Конфигурация и следующие этапы

Health и экран настройки запускаются без секретов. Рабочее пространство требует
Firebase Authentication и серверный Firebase Admin. Firebase project ID — `saq-qurylys`.
Gemini будет использовать серверный `GEMINI_API_KEY` и выбранный `GEMINI_MODEL`.
Настройки `VITE_FIREBASE_*` предназначены
только для browser SDK. Никогда не помещайте Admin credentials или Gemini key в `VITE_*`.
Credentials храните вне Git; для монтирования используйте `compose.firebase.yaml`.
`.env` и `credentials/` исключены из Git.

Следующий этап: защищённый API и UI для ЖК, объявлений и доказательств,
затем AI и рабочий процесс сигналов. Плановые чекбоксы обновляются
после review/merge, а не по наличию каркаса.

Каркас создан с помощью Codex; реализация требует обычного командного review.
