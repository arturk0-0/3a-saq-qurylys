# SAQ QURYLYS

Внутреннее приложение для аналитиков ВКО: проверка потенциальных рисков в рекламе
строящихся ЖК. Система поддерживает решение человека и не устанавливает незаконность.
Контекст: [AGENTS.md](AGENTS.md), [спецификация](docs/PROJECT_SPEC.md),
[план разработки](docs/DEVELOPMENT_PLAN.md).

## Текущий этап

Готовы чистый скоринг R1–R6, валидируемые модели доказательств, DEMO-набор из 8 ЖК и
12 объявлений, Firebase Admin и вход через Firebase Authentication. Защищённые запросы
требуют проверенный token с ролью analyst/admin. Без настройки Firebase отображается
экран подключения среды. Локальный запуск рабочего пространства требует собственной
разрешённой Firebase-конфигурации; секреты не входят в исходники.

Настройка: [Firebase и доступ аналитика](docs/firebase-setup.md).
Windows: [пошаговый запуск](docs/windows-start.md).
Демонстрация: [новое объявление → проверка → PDF](docs/demo-scenarios.md).
Организаторам: [показ на 5–7 минут и запасной сценарий](docs/judge-runbook.md).
Проверки этой версии: [ночной отчёт](docs/night-reviewer-report.md).
Устройство приложения: [архитектура](docs/architecture.md), [API и данные](docs/data-model.md).
Правила: [R1–R6](docs/risk-rules.md). Данные: [DEMO seed](data/seed/README.md).
Публичные реестры: [источники и порядок ручной сверки](docs/public-sources.md),
ссылки доступны в карточке ЖК → Документы; автоматической загрузки реестров нет.
Ход реализации и ограничения: [WORK_LOG](docs/WORK_LOG.md).

## Возможности и стек

React + TypeScript (strict) + Vite, Tailwind CSS, базовый Button shadcn/ui и React Router.
Реализованы обзор с фильтрами, реестр, карточка ЖК, объявления, доказательства,
документы и история. Локальный UI обращается к защищённому FastAPI через Vite proxy;
Hosting использует настроенный HTTPS origin Cloud Run.
API предоставляет `GET /api/v1/health`, настройки CORS, ошибки
`{code, message, requestId}` и заголовок `X-Request-ID`.

Добавлен серверный Gemini adapter для текста/скриншотов, приватная загрузка и
проверка гипотез. По извлечённым названиям можно запросить кандидатов ЖК по имени/
алиасам и явно выбрать карточку для сравнения; автоперепривязки нет.
Методология и ограничения: [AI](docs/ai-methodology.md).
Сигналы: черновик, передача на проверку, подтверждение/возврат и PDF со снимком
доказательств. Инструкция: [сигналы и PDF](docs/signals.md).
Карта Leaflet/OpenStreetMap открывается кнопкой «Показать карту» на обзоре и в реестре.
Она показывает объекты текущей страницы с координатами, учитывает фильтры и открывает
карточку по метке. DEMO-координаты условные; список доступен при сбое подложки OSM.
В объявлениях доступен [«Рекламный след»](docs/advertising-trace.md): точные
совпадения телефонов/WhatsApp, доменов и названий с ручным решением и аудитом.
Совпадения не устанавливают владельца и не меняют R1–R6. Drone-модуль не реализован.
Health проверяет процесс API, а не Firebase или Gemini. A/B/C проверены на синтетических данных.

## Сайт для организаторов

Опубликованный сайт: https://saq-qurylys.web.app. Для просмотра нужен браузер и
выданная владельцем приватно учётная запись аналитика; Docker, Python, Admin JSON
и ключ Gemini посетителю сайта не нужны. API:
https://saq-qurylys-api-722228028571.europe-west1.run.app.
Владелец подтвердил вход, DEMO, создание объявления, реальный текстовый Gemini-анализ
и ручное подтверждение R2 (10 → 35). 16 октября владелец также подтвердил
историю, скачанный PDF, анализ скриншота и успешное завершение ручных проверок.
Это относится к опубликованной версии; новые PR требуют отдельной приёмки. Новые коммиты и PR не публикуются автоматически.

Локальный запуск ниже создаёт отдельные процессы на вашем компьютере, но при
подключении к Firebase использует выбранный облачный проект и его данные.
Порядок публикации владельцем: [Hosting + Cloud Run](docs/cloud-deployment.md).
При подготовке проверенной версии фиксируйте полный SHA: текущий `main` может
не включать исправления из открытых PR. Ночная проверка ведётся в
`test/night-release-readiness` от `fix/security-demo-hardening` (`d579566`).

## Запуск через Docker

Требуются Git, Docker Engine и Docker Compose v2. Для воспроизведения этой проверки
из новой папки (ветка содержит открытые PR, merge/publication ещё нужны):

```bash
git clone --branch test/night-release-readiness --single-branch https://github.com/arturk0-0/3a-saq-qurylys.git
cd 3a-saq-qurylys
git rev-parse HEAD
```

Сравните SHA с проверяемым PR. Для окончательной сдачи владелец передаёт согласованный
commit/tag после review; не заменяйте его случайным состоянием `main`.
Из корня, где находятся `compose.yaml`, `backend/` и `frontend/`:

```bash
test -e .env || cp .env.example .env
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
и `package-lock.json`. Из корня создайте `.env`, сохранив существующий:

```bash
test -e .env || cp .env.example .env
```

Для PDF WeasyPrint нужны системные библиотеки и шрифты. На Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core
```

В Docker они устанавливаются Dockerfile. Для Windows используйте Docker Desktop
по отдельной инструкции; Linux-проверка не подтверждает нативный Windows-запуск.

Оба терминала изначально откройте в корне `3a-saq-qurylys/`. В первом:

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
Gemini использует серверный `GEMINI_API_KEY` и выбранный `GEMINI_MODEL`.
Диагностика: `uv run --frozen python -m app.cli.check --online --require-ai` из `backend/`;
она проверяет доступ без генерации и изменения данных. Набор входов и команда
для платного RU/KZ/image-прогона описаны в [методологии AI](docs/ai-methodology.md).
При `AI_INVALID_RESPONSE` сохраните код обращения: безопасный поиск причины
в серверных логах описан в [инструкции deployment](docs/cloud-deployment.md).
Изменения диагностики/PDF и границы локальных проверок —
[отчёт B-03/B-04](docs/backend-followup-report.md).
Настройки `VITE_FIREBASE_*` предназначены
только для browser SDK. Никогда не помещайте Admin credentials или Gemini key в `VITE_*`.
Credentials храните вне Git; для монтирования используйте `compose.firebase.yaml`.
`.env` и `credentials/` исключены из Git.

Следующий этап: live-проверка Firebase/Gemini, командное review и прогон на втором ПК.
Для локальной проверки без облачных данных есть отдельный
[Chromium QA runner с явно тестовыми адаптерами](frontend/qa/release/README.md).
Он не подменяет демонстрацию настоящего Gemini и не входит в production entry.
Плановые чекбоксы обновляются
после review/merge, а не по наличию каркаса.

Каркас создан с помощью Codex; реализация требует обычного командного review.
