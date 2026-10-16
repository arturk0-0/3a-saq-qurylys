# Единый кандидат SAQ QURYLYS

Ветка: `release/demo-candidate`. Задача от 16 октября 2026 (Asia/Qyzylorda).
Это подготовка к review, а не публикация сайта или подтверждение облачной приёмки.

## Состав

В отдельной feature-ветке объединены:

- `fix/backend-concurrency-recovery`, `82e61d5`: весь предшествующий backend,
  безопасность, frontend и исправления конкурентных действий;
- `test/night-release-readiness`, `8dce105`: работа друга — восстановление сессий,
  сохранение фильтров/черновиков при конфликтах, PDF guard, браузерный QA runner
  и пакет инструкций для организаторов.

Объединение прошло без конфликтов. `main` и исходные ветки не изменены.
Предыдущие PR остаются отдельными материалами для review; независимое одобрение
не заменено авторской проверкой. Release-ветка нужна для единой проверки и
возможного последующего согласованного переноса в main.

## Новая проверка настоящего Firestore SDK

Добавлен opt-in runner `backend/qa/firestore/run.py`, локальные integration tests
и отдельная CI job. Эмулятор не становится частью приложения: production по-прежнему
онлайн Firebase, backend без Java, прежние зависимости/контракты/R1–R6.
Без credentials, платного Gemini, изменения инфраструктуры и живых данных.

Первый реальный локальный прогон: **7 passed**, Firestore emulator **1.22.0**,
firebase-tools **15.34.0**, Java **21**. Проверены:

- новое объявление → AI MockTransport → принятие гипотезы → source review →
  явное подтверждение R2, 10→10→35;
- текст RU и скриншотный путь с KZ-цитатой (это не проверка качества OCR);
- настоящие persisted signal/revisions/history → submit/return/resubmit/confirm
  → настоящий локальный WeasyPrint PDF;
- повторы analysis requestId без нового вызова провайдера;
- реальные query/cursors, одинаковые даты, DEMO/объектная область;
- rollback без частичных бизнес/audit-записей;
- реальная конкуренция решений и глобальная AI-квота;
- настоящие rules: прямые клиентские read/write запрещены, серверный SDK работает.

Изолированные guards дополнительно прошли **13 unit-тестов**: non-loopback,
реальные/неподходящие project IDs, отсутствие opt-in, исключение credentials и
сохранение TLS/CA. К обычным 238 backend-тестам добавлены отдельно.

Расширенный повтор: **10 passed**, включая A=35/YELLOW, B=70/RED,
C=10/GREEN с применимой гарантией, сохранённые через настоящий SDK и
включённые в снимки сигналов. Артефакты:
`/tmp/saq-firestore-integration-muw5lnv8/results.xml`, локальные emulator logs.

## Итоговая проверка единого кандидата

| Проверка | Фактический результат |
| --- | --- |
| Backend pytest | 251 passed, без запуска эмулятора |
| Настоящий SDK integration | 10 passed, отдельный изолированный emulator process |
| Ruff check/format | Успешно, 75 Python-файлов |
| compileall app/qa/integration_tests | Успешно |
| Frontend Vitest | 61 passed, 15 файлов |
| TypeScript + Vite production build | Успешно |
| Chromium opt-in runner | 15 групп passed, 498 локальных запросов, 0 page errors/external requests |
| Docker backend/frontend | Оба образа собраны из этой ветки, оба контейнера healthy |
| Контейнерные HTTP проверки | Health напрямую/через proxy, protected API 401, отсутствие конфигурации 503, CORS allow/deny |
| Chromium против контейнера без config | Прямая ссылка карточки показывает setup screen, 0 внешних запросов |
| PDF внутри non-root backend image | Настоящий PDF 20 779 bytes; pdftotext подтвердил `Құрылыс`, DEMO, 70/100, R1–R6 |
| Эвристический скан Git-истории | 42 достижимых коммита / 380 уникальных blob на момент скана; совпадений с проверенными шаблонами нет |

Git-скан проверял PEM/JSON private key, Google API key candidates, OAuth refresh
tokens, GitHub/AWS token candidates и JWT candidates без печати значений. Это
не доказательство отсутствия любых секретов; внешние artifacts/форки/удалённые
объекты и облачные журналы не проверены.

Контейнеры запускались отдельным Compose-проектом `saq-release-candidate`,
только loopback 18800/15173, без env приложения/credentials и с явно отключённым
Firebase. Исходный пользовательский Compose не перезаписывался. Стандартный
Compose отдельно проверен CI. Сетевые ограничения сборочной среды обходились
штатными proxy build args/host mapping и поддерживаемым `custom_ca` secret;
TLS/подписи не отключались. Контейнеры работают как `appuser`/`node`; Java и QA
эмулятор в production backend image не добавлены. После проверок собственный
Compose-проект остановлен и удалён, browser/emulator runner также завершили
свои процессы. Артефакты синтетические:

- `/tmp/saq-release-candidate-browser/results.json` и снимки/локальный PDF;
- `/tmp/saq-release-candidate-demo.pdf` — PDF из контейнера;
- `/tmp/saq-firestore-integration-muw5lnv8/results.xml` и emulator logs.

Backend image: `sha256:224cff3a4504d6989c17a7aa28320fac91846149a28abd151e9239ac4230e302`.
Frontend image: `sha256:e079d5bab161941e5213e10a627e07ff44dd3ba7d3b54729521323306c2fa783`.
Это локальные образы, не отправленные в Artifact Registry. Образы основаны на
обычных repository Dockerfiles; базовые теги плавающие, bit-for-bit reproducible
build не обещается. Dependency lockfiles не менялись.

Первый CI нового кандидата `9a072d4`: **backend/frontend/compose/firestore-integration
все success**, https://github.com/arturk0-0/3a-saq-qurylys/actions/runs/38845179169.
Финальные изменения после этого — документация; CI всё равно проверяется для
последнего SHA PR, без переноса статуса со старого коммита.

Сборка сообщает известное предупреждение JS chunk чуть больше 500 kB
(около 153.6 kB gzip); это не ошибка. Осталось прежнее предупреждение
Starlette/httpx в тестовом клиенте и предупреждения GitHub об обновлении
runner/actions. Не выполнялся незапрошенный редизайн, замена библиотек или
обновление lockfiles ради удаления предупреждений.

Сверены архитектура, перечень коллекций/API и hand-off плана. Исправлены
устаревшие утверждения об отсутствии карты/коллекций и о непроверенном вообще
Gemini; owner-reported успех отделён от самостоятельно выполненных локальных
проверок. Чекбоксы приёмки и независимого review автоматически не закрывались.

## Публикация после согласования владельцем

Эта ветка содержит весь кандидат. Владелец проверяет финальный SHA и diff PR;
main не обновлялся автоматически, submission tag и repo visibility не менялись.
После review и согласованного выбора версии получить её в Cloud Shell:

```bash
git fetch origin release/demo-candidate
git switch --detach FETCH_HEAD
git rev-parse HEAD
```

Продолжать только в чистом рабочем дереве и после проверки, что показанный SHA
совпадает с согласованным. Существующие env/credentials не добавлять в Git.
Из корня этого checkout сначала собрать backend:

```bash
SAQ_IMAGE="europe-west1-docker.pkg.dev/saq-qurylys/saq-qurylys/api:candidate-$(date -u +%Y%m%d-%H%M%S)"
gcloud builds submit . --project=saq-qurylys \
  --config=deploy/cloudbuild.yaml --substitutions="_IMAGE=$SAQ_IMAGE"
```

Только после SUCCESS, в той же сессии:

```bash
gcloud run services update saq-qurylys-api --project=saq-qurylys \
  --region=europe-west1 --image="$SAQ_IMAGE"
```

Команда сохраняет действующие env, secrets, runtime identity и выбранную модель.
Нужные индексы и их готовность проверяются отдельно по cloud-deployment.md;
эмулятор их наличие не подтверждает. Затем frontend с уже настроенными
browser config и VITE_API_BASE_URL:

```bash
cd frontend
npm ci
npm run build:hosting
```

Только после успешной проверки env/typecheck/build:

```bash
cd ..
npx firebase-tools@15.34.0 deploy --only hosting --project saq-qurylys
```

Эти команды записаны для владельца, здесь не выполнялись. Если публичные VITE
настройки отсутствуют в выбранном checkout, сначала восстановить их локально
по README/cloud-deployment; не пытаться публиковать неуспешную сборку.

## Оставшиеся release gates

Облачные IAM/rules/index readiness/Storage/PDF/OCR, измерение качества нового
RU/KZ/image Gemini-ввода, второе устройство и независимое review требуют
отдельной приёмки владельцем по judge-runbook. Ни MemoryStore, ни настоящий
локальный SDK не проверяют production auth/инфраструктуру и provider quality.
История сигнала на живом сайте могла ошибаться; успешная локальная история
не устанавливает причину и не подтверждает исправление опубликованной версии.
Реальный успешный Gemini и R2 10→35 ранее сообщил владелец, повторных платных
проверок здесь нет. После приёмки остаются согласованные merge/tag/publication.
