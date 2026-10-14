# SAQ QURYLYS

Внутреннее приложение для аналитиков ВКО: проверка потенциальных рисков в рекламе
строящихся ЖК. Система поддерживает решение человека и не устанавливает незаконность.
Контекст: [AGENTS.md](AGENTS.md), [спецификация](docs/PROJECT_SPEC.md),
[план разработки](docs/DEVELOPMENT_PLAN.md).

## G0 — каркас

React + TypeScript (strict) + Vite, Tailwind CSS, базовый Button shadcn/ui и React Router.
Навигация: обзор, реестр ЖК, объявления, сигналы. Рабочие разделы ещё не реализованы.
Обзор проверяет настоящий FastAPI через Vite proxy, сообщает об ошибках и позволяет
повторить запрос. API предоставляет `GET /api/v1/health`, настройки CORS, ошибки
`{code, message, requestId}` и заголовок `X-Request-ID`.

Firebase Auth/Firestore/Storage, Gemini, DEMO seed, R1–R6, карта и PDF пока не подключены.
Авторизации и рабочих данных нет: открыта только техническая оболочка и health endpoint.
Health проверяет процесс API, а не Firebase или Gemini. Сценарии A/B/C ещё не реализованы.

## Запуск через Docker

Требуются Docker Engine и Docker Compose v2. Из корня репозитория:

```bash
cp .env.example .env
docker compose up --build --wait
```

UI: `http://localhost:5173`, API: `http://localhost:8000/api/v1/health`,
OpenAPI: `http://localhost:8000/docs`. Порты опубликованы только на loopback.
Ожидаемый health: `{"status":"ok","service":"saq-qurylys-api"}`.
В обзоре появится «API доступен». Остановка: `docker compose down`.
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

Для G0 внешние сервисы и секреты не нужны. `.env.example` содержит пустые поля для
будущего Firebase/Gemini; они пока не используются. Firebase project ID — `saq-qurylys`.
В будущей интеграции backend получит приватные Admin credentials и `GEMINI_API_KEY`,
модель будет задаваться через `GEMINI_MODEL`. Настройки `VITE_FIREBASE_*` предназначены
только для browser SDK. Никогда не помещайте Admin credentials или Gemini key в `VITE_*`.
Credentials храните вне Git; монтирование в контейнер добавляется при реализации интеграции.
`.env` и `credentials/` исключены из Git.

Следующий этап: Firebase и авторизация, безопасный DEMO seed и чистый backend-скоринг
с тестами A/B/C. AI и рабочий процесс — после этого. Плановые чекбоксы обновляются
после review/merge, а не по наличию каркаса.

Каркас создан с помощью Codex; реализация требует обычного командного review.
