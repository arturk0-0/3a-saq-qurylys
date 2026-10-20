# Запуск в Windows

Для проверки исходников используйте отдельную локальную демонстрацию.
Firebase, ключи API и `.env` для неё не нужны.

## Подготовка

1. Установите [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)
   для своего процессора: AMD64 для обычного Intel/AMD, ARM64 для ARM.
2. Запустите Docker Desktop, завершите настройку WSL 2 при необходимости и
   включите Linux containers. Дождитесь готовности Docker Engine.
3. Установите Git либо скачайте репозиторий через **Code → Download ZIP**.
   После распаковки откройте папку, в которой лежит `compose.demo.yaml`.

## PowerShell

```powershell
git clone https://github.com/arturk0-0/3a-saq-qurylys.git
Set-Location 3a-saq-qurylys
docker compose version
docker compose -f compose.demo.yaml up --build --wait --wait-timeout 180
```

Если исходники скачаны ZIP, первые две команды заменяются переходом в
распакованную папку. Первая сборка требует Интернета и может занять несколько минут.

Откройте **http://localhost:5173**. Почта `analyst@example.test`, пароль `demo-demo`.
[Сценарий проверки](judge-runbook.md) · [особенности локального режима](local-demo.md).

## Если не открылось

| Сообщение | Что сделать |
| --- | --- |
| `docker` не распознано | Установить Docker Desktop, перезапустить терминал. |
| Cannot connect to Docker daemon | Запустить Docker Desktop и дождаться готовности. |
| no configuration file provided / файл не найден | Перейти в папку с `compose.demo.yaml`; после ZIP она может быть вложенной. |
| port is already allocated | Освободить 5173 или остановить предыдущую копию приложения. |
| localhost не отвечает | Проверить команды ниже и дождаться `healthy` у обоих сервисов. |
| Экран настройки Firebase | Запущен обычный Compose; для проверки без ключей нужен именно `-f compose.demo.yaml`. |

```powershell
docker compose -f compose.demo.yaml ps
docker compose -f compose.demo.yaml logs --tail 50
Invoke-RestMethod http://127.0.0.1:5173/api/local-demo/info
```

Последняя команда должна вернуть `mode: local-demo`.
Остановка с сохранением учебных данных:

```powershell
docker compose -f compose.demo.yaml down
```

`down -v` удаляет учебные данные и файлы. Для обычной остановки её не используйте.

Для собственного Firebase/Gemini есть отдельные инструкции:
[разработка](development.md), [настройка Firebase](firebase-setup.md).
Команды Compose проверены в Linux; самостоятельная проверка именно Windows/WSL
не подменяется этим результатом.
