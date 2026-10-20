# Разработка и проверки

Для просмотра проекта начните с [локальной демонстрации](local-demo.md).
Здесь — установка для изменения кода и подключение собственных внешних сервисов.

## Зависимости

Python **3.12**, uv **0.12.23**, Node.js **24 LTS**. Установка по lockfiles:

```bash
cd backend
uv sync --frozen
cd ../frontend
npm ci
```

Для серверного PDF на Debian/Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core
```

## Локальная демонстрация без Docker

Два терминала, из соответствующих директорий:

```bash
# backend/
uv run --frozen python -m local_demo
```

```bash
# frontend/
npm run demo
```

Откройте http://localhost:5173. Данные — в `backend/.local-demo-data/`.
Это отдельный локальный режим с учебными данными и ответами; он не обращается
к настоящим Firebase/Gemini. Подробности: [local-demo.md](local-demo.md).

## Собственные Firebase и Gemini

Настройте `.env`, Firebase, роль аналитика и приватные credentials по
[инструкции](firebase-setup.md). Файлы ключей и `.env` не входят в Git.

```bash
# Из корня, после настройки собственных внешних сервисов:
docker compose -f compose.yaml -f compose.firebase.yaml up --build --wait
```

Либо в двух терминалах:

```bash
# backend/
uv run --frozen uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
# frontend/
npm run dev
```

Без Firebase основной `compose.yaml` даёт health и экран настройки.
Для рабочего каталога используйте отдельный `compose.demo.yaml` либо собственный
настроенный облачный проект. Не запускайте оба Compose-режима одновременно.

## Тесты

```bash
# backend/
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest
```

```bash
# frontend/
npm test
npm run build
```

Из корня, при запущенной локальной демонстрации; Python 3.12+:

```bash
python scripts/check-local-demo.py
```

Он создаёт отдельный учебный объект, проверяет решения, сигнал, PDF и приватную
загрузку. Существующие решения не сбрасываются.

Расширенные проверки: [Firestore SDK](../backend/qa/firestore/README.md),
[браузер и единая реклама](../frontend/qa/unified-advertising/README.md).
Это отдельные QA-адаптеры; успешный локальный прогон не заменяет проверку
реальных учётных записей, провайдеров и развёрнутого сайта.
