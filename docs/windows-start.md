# Запуск в Windows через Docker Desktop

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

В PowerShell из папки с compose.yaml:

```powershell
docker --version
docker compose version
docker info
Copy-Item .env.example .env
docker compose up --build --wait
```

Copy-Item нужен только при первом запуске: не перезаписывайте свой заполненный .env.
После успешного запуска откройте браузер на **http://localhost:5173**.
Это локальный сервер вашего ПК. Облачная панель Codex для этого не используется.
Без настройки Firebase откроется экран «Подключите рабочую среду».

Чтобы получить рабочие данные, заполните .env по docs/firebase-setup.md и запускайте
с приватным credentials override:

```powershell
docker compose -f compose.yaml -f compose.firebase.yaml up --build --wait
docker compose -f compose.yaml -f compose.firebase.yaml exec backend .venv/bin/python -m app.cli.check --online --require-ai
docker compose -f compose.yaml -f compose.firebase.yaml exec backend .venv/bin/python -m app.cli.seed validate
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
Остановка приложения: docker compose down (данные Firestore остаются в облаке).
Команды Compose проверены в Linux-среде; запуск на вашем Windows ещё требует проверки.
