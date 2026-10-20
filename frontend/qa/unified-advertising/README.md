# Unified advertising: локальная QA (#30)

Все файлы здесь — **отдельные тестовые адаптеры**, не production. Золотые DTO
`fixtures.json` задают ответы для ошибок и конфликтов. `transport.py` не вычисляет
риск. `integration_api.py` подключает настоящие backend routes/services/worker из
ветки B, но использует MemoryStore, FakeFiles, тестовую личность и GeminiClient с
MockTransport. Реальные Firebase/Gemini не вызываются. Данные синтетические.

Проверено на Linux, Node 24.19, Python 3.12.14, Chromium. Нужны Python
Playwright/Pillow и Chromium: установка описана в `../release/README.md`.
Общие QA-инструменты не являются зависимостями production приложения.

Из корня репозитория (отдельный чистый checkout backend B; исходники не менять):

```bash
git fetch origin feat/B-materials-auto-priority
git worktree add --detach /tmp/saq-materials-backend-review f95c644065e3ea56025ec6480f5560a187fb52a0
UV_PROJECT_ENVIRONMENT=/tmp/saq-a-backend-venv uv sync --project /tmp/saq-materials-backend-review/backend --frozen
cd frontend
npm ci
npm test
npm run typecheck
npm run build -- --manifest
cd ..
```

Если worktree уже существует, используйте его только после проверки чистоты и
нужного SHA, либо выберите новый путь. Никаких `.env`, секретов или venv из
рабочего checkout переносить не нужно.

Настоящий backend B: intake → очередь → дедупликация → одно сохранение проверки →
реальный R2/риск 35 → история → сигнал → настоящий PDF WeasyPrint:

```bash
SAQ_BACKEND_PYTHON=/tmp/saq-a-backend-venv/bin/python \
SAQ_QA_BACKEND_ROOT=/tmp/saq-materials-backend-review/backend \
SAQ_QA_API_MODULE=integration_api:app \
SAQ_QA_BROWSER_SCRIPT=frontend/qa/unified-advertising/integration_check.py \
SAQ_QA_ARTIFACTS=/tmp/saq-native-repeat \
python3 frontend/qa/release/run.py
```

Сбои API и границы состояний: те же переменные, но
`SAQ_QA_BROWSER_SCRIPT=frontend/qa/unified-advertising/browser_check.py` и новая
папка `SAQ_QA_ARTIFACTS`. Здесь `/materials` подменён явно в browser transport;
это проверка UI-контракта, не доказательство backend транзакций.

Ожидается 5 PASS для настоящей интеграции и 11 PASS для контракта, exit 0.
Запуски последовательные: runner занимает только localhost:8011/5181,
отказывается занимать уже используемые порты, очищает credentials в дочернем
окружении, блокирует внешнюю сеть браузера и завершает собственные процессы.
Исторический `qa/release/browser_check.py` проверяет старую навигацию/ручной AI;
для новой «Рекламы» используйте явно указанные scripts выше.

В `results.json` — результаты, рядом логи, PDF и снимки 1440/375/320 px с явной
маркировкой QA. Снимки в `screenshots/` получены из локальных прогонов; они не
доказывают работу опубликованного сайта. Production entrypoints не импортируют
эти адаптеры. Команда обычной сборки не включает их в JS bundles.
