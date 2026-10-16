# Запуск в Windows через Docker Desktop

Для **просмотра опубликованного сайта** откройте https://saq-qurylys.web.app
и войдите приватно выданной учётной записью. Установка Docker и скачивание
серверных ключей для просмотра сайта не нужны. Ниже — **локальный запуск**
процессов на своём компьютере. Они используют выбранный облачный Firebase-проект,
когда он настроен; это не отдельная локальная копия базы.

1. Для обычного ПК с процессором Intel/AMD скачайте Docker Desktop **AMD64**.
   ARM64 предназначен для компьютеров с ARM-процессором. Проверьте актуальные
   требования Docker Desktop к Windows и WSL 2 на официальном сайте:
   https://docs.docker.com/desktop/setup/install/windows-install/
2. Установите и запустите Docker Desktop, завершите предложенную настройку
   WSL 2/перезагрузку. Затем полностью перезапустите VS Code.
3. В VS Code откройте **именно папку с compose.yaml**, backend и frontend.
   После распаковки ZIP она может находиться внутри другой папки saq-qurylys.
4. В Explorer слева нажмите правой кнопкой на эту папку → Open in Integrated
   Terminal. Или Terminal → New Terminal; проверьте текущую папку командой dir.

Если исходников ещё нет, в PowerShell из новой рабочей папки:

```powershell
git clone --branch test/night-release-readiness --single-branch https://github.com/arturk0-0/3a-saq-qurylys.git
Set-Location 3a-saq-qurylys
git rev-parse HEAD
```

Сравните полный SHA с PR/переданной версией; ветка проверки ещё требует review.
Для итоговой сдачи используйте согласованный владельцем commit/tag.
В PowerShell из папки с `compose.yaml`:

```powershell
docker --version
docker compose version
docker info
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build --wait
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:5173/api/v1/health
```

Ожидается: оба сервиса `healthy`, оба health-ответа содержат `status: ok` и
`service: saq-qurylys-api`. Python/Node отдельно на хосте для Docker-пути не нужны.
После успешного запуска откройте браузер на **http://localhost:5173**.
Это локальный сервер вашего ПК. Облачная панель Codex для этого не используется.
Без настройки Firebase откроется экран «Подключите рабочую среду».
Это успешный health/setup-запуск, а не работающий каталог/вход/Gemini.

Чтобы получить рабочие данные, заполните .env по docs/firebase-setup.md и запускайте
с приватным credentials override:

```powershell
docker compose -f compose.yaml -f compose.firebase.yaml up --build --wait
docker compose -f compose.yaml -f compose.firebase.yaml exec backend .venv/bin/python -m app.cli.check --online --require-ai
docker compose -f compose.yaml -f compose.firebase.yaml exec backend .venv/bin/python -m app.cli.seed validate
```

Ожидается экран входа; после входа — защищённое рабочее пространство. Диагностика
проверяет доступ без генерации, но её успех не заменяет настоящий AI/Storage/PDF
прогон. Для browser config нужны четыре обязательных `VITE_FIREBASE_*` из
docs/firebase-setup.md, для backend — его отдельные credentials и bucket.
`FIREBASE_CREDENTIALS_FILE` в корневом `.env` — абсолютный Windows-путь с `/`,
например `C:/private/saq-firebase-admin.json`. При смене конфигурации повторите
`up --build --wait` с теми же двумя `-f`.

## Административная подготовка — только владелец

Следующие команды меняют выбранный облачный проект. Они не нужны для просмотра
сайта или обычного перезапуска. Выполняйте их только после выбора собственного
учебного проекта по docs/firebase-setup.md:

```powershell
docker compose -f compose.yaml -f compose.firebase.yaml exec backend .venv/bin/python -m app.cli.seed import --project-confirm saq-qurylys --apply
```

Назначение роли (замените YOUR_FIREBASE_UID на UID созданного пользователя):

```powershell
docker compose -f compose.yaml -f compose.firebase.yaml exec backend .venv/bin/python -m app.cli.role YOUR_FIREBASE_UID analyst --project-confirm saq-qurylys
```

После назначения роли войдите в приложение заново.

| Сообщение | Что сделать |
| --- | --- |
| docker не распознано | Установить Docker Desktop, перезапустить VS Code |
| Cannot connect to Docker daemon | Открыть Docker Desktop и дождаться запуска |
| no configuration file provided | Перейти в папку, где лежит compose.yaml |
| port is already allocated | Остановить предыдущий запуск приложения; проверить docker compose ps |
| localhost не подключается | Проверить docker compose ps и docker compose logs --tail 50 |
| экран настройки Firebase | Заполнить browser-конфигурацию и серверные credentials, пересоздать контейнеры |

Не отправляйте .env, private key или полный вывод конфигурации в чат.
Остановка базового запуска: `docker compose down`; для Firebase override:

```powershell
docker compose -f compose.yaml -f compose.firebase.yaml down
```

Данные Firestore остаются в выбранном облачном проекте.
Команды Compose проверены в Linux-среде; запуск на вашем Windows ещё требует проверки.
