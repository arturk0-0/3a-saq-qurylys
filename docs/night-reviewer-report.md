# Проверка готовности к демонстрации и сдаче

База: `fix/security-demo-hardening`, полный SHA
`d5795669fd567d8da4a2fc473f30ec0f3296b4d3`.
Рабочая ветка: `test/night-release-readiness`. Начало: 15 октября 2026,
23:16 Asia/Almaty (18:16 UTC); предел активной работы — пять часов.
Это проверка локальной Linux-среды; результаты не означают публикацию в Hosting
или Cloud Run. Живые данные/инфраструктура и платный Gemini не используются.

## База и координация

Прочитаны AGENTS, PROJECT_SPEC, DEVELOPMENT_PLAN, WORK_LOG и три night-отчёта.
Получены все удалённые heads. Указанная база включает backend/frontend/security
исправления; уже выполненные функции заново не реализуются. Исходное рабочее
дерево чистое, прежней несохранённой работы нет. Исторические PR: #1 backend,
#2 frontend, #3 security. GitHub GraphQL и REST PR/check-runs вернули `Forbidden`
в текущей сессии; состояние PR/CI по этим ответам установить нельзя. Git read
работает, ветка будет отправляться по этапам; доступ к API проверяется повторно
перед завершением. `main` не меняется.

## Этап 1 — чистая установка

Создан Git-export точного HEAD в `/tmp/saq-release-clean`, только tracked-файлы:
без `.env`, production env, `node_modules`, `.venv` и credentials. Это чистая копия
на этой же Linux-машине, не второй Windows-компьютер.

| Проверка | Фактический результат |
| --- | --- |
| Node / npm / uv / Python | 24.19.0 / 11.9.0 / 0.12.23 / 3.12.14 |
| `frontend`: `npm ci` | Установлены 265 пакетов из package-lock.json |
| `npm test` | 48 passed, 12 test files |
| `npm run typecheck`, `npm run build` | Успешно |
| `backend`: `uv sync --frozen` | 63 пакета из uv.lock, отдельная новая .venv |
| `uv run --frozen pytest -q` | 218 passed; один прежний StarletteDeprecationWarning |
| Ruff check / format | Успешно, 66 файлов |
| `python -m app.cli.seed validate` | 8 застройщиков, 8 ЖК, 12 объявлений, 9 источников |
| `python -m app.cli.check` без конфигурации | Exit 1: Firebase/Storage FAILED, Gemini SKIPPED; ожидаемая диагностика, не успешное подключение |

Оба Docker-образа собраны из чистого export с frozen lockfiles. Для сетевого
ограничения этой машины потребовались штатные proxy build args, host build network,
`--add-host` для имени прокси по текущему `/etc/hosts` и поддерживаемый secret
`custom_ca`. Проверка TLS/подписей не отключалась, Dockerfiles не менялись.
Первый build остановлен после `Temporary failure resolving 'proxy'`; это свойство
build sandbox, а не ошибка приложения. `docker compose -p saq-release-clean up
--no-build --wait --wait-timeout 120` успешно запустил оба образа: оба healthy.
Health напрямую на 8000 и через frontend proxy на 5173 вернул точный JSON;
защищённый каталог без токена — 401. Chromium по прямому URL карточки без
конфигурации показал «Подключите рабочую среду», без рабочей навигации.

README уточнён: просмотр опубликованного сайта отдельно от локального запуска,
фактические проверки владельца отдельно от PR; добавлены системные PDF-зависимости
для Linux и создание `.env` без перезаписи существующего файла.

## Воспроизведения перед исправлением frontend

- **AUTH-01:** войти с принятым токеном → API следующего раздела отвечает 401.
  На базе навигация и рабочая оболочка остаются; меняется только ошибка запроса.
  Если `getIdToken()` отклонён с `auth/user-token-expired`, интерфейс также остаётся
  открытым и показывает исходный текст SDK exception. Два новых regression-теста
  воспроизвели дефект (2 failed), контрольный offline-тест прошёл.

## Осталось проверить

Браузерная матрица, исправления с regression-тестами, runbook, финальные проверки,
push, PR и CI. Облачные история/PDF/скриншот и второй Windows-ПК остаются ручными
шагами владельца; этот промежуточный отчёт их не объявляет пройденными.
