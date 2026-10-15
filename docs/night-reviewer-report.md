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
- **NAV-01:** в реестре задать поиск/город/приоритет → открыть карточку → browser
  Back. На базе фильтры сбрасывались, так же при reload. Regression-тест упал
  на пустом поле поиска после возврата. Теперь применённые параметры и курсор
  хранятся в URL, browser Back/Forward/reload восстанавливают выборку.
- **SIGNAL-01:** открыть создание сигнала, заполнить заголовок/основание → другой
  аналитик меняет версию ЖК → создать. Ответ 409 сохранял поля, но повтор всегда
  посылал прежнюю версию; полный reload терял ввод. Regression-тест сначала упал
  из-за отсутствия безопасного обновления. Теперь есть «Обновить данные ЖК»:
  GET новой версии, сохранение обоих полей, явная повторная проверка и отправка.

## Этап 2 — браузер и исправления

Добавлен opt-in runner `frontend/qa/release/run.py` на уже доступном Playwright
1.62.0 + системном Chromium, без новой frontend/backend зависимости. Production
entry/config не импортируют adapters; QA Vite config включает явную плашку.
Реальные API routes/services, validation, risk и WeasyPrint работают с существующими
MemoryStore/FakeFiles/Gemini MockTransport. Browser Auth adapter заменяет только
внешний SDK; проверяется настоящий AuthProvider. Все процессы только loopback;
application credentials/env исключаются, внешние browser requests запрещены.

Завершённый прогон: **14 контрольных групп passed**, 432 browser requests, 0 page
errors, 0 внешних запросов. Артефакты этого прогона:
`/tmp/saq-release-browser-complete/results.json`, локальный настоящий PDF и снимок
мобильного экрана. Runner останавливает свои процессы и начинает с нового seed.

| Область | Проверено фактически |
| --- | --- |
| Авторизация | Прямая protected ссылка без входа; ошибка входа/очистка пароля; вход/выход/reload; ранее принятый токен → 401 → закрытие workspace → повторный вход |
| Каталог | Поиск/город/зона, пустая выборка, карточка/Back/Forward/reload, сохранение URL/cursor; реальная пагинация с уменьшенным limit |
| Объявление | Native required validation не отправляет POST; ошибка сохранения и явный повтор; исходные пробелы/переносы сохранены backend без изменений |
| AI | Pending/disabled состояние, реальный service с MockTransport, гипотеза, отсутствие гипотез на безобидном тексте, model/quota/network errors |
| Файл | Неверный MIME и повреждённый PNG отвергнуты реальным валидатором; >6 MiB не отправляется; допустимый PNG сохраняется и открывается через закрытый API |
| Разделение решений | Принятие AI = 10; source review = 10; отдельное решение R2 = 35, score получен с backend |
| Сигнал | UI draft → submit → return → resubmit → confirm; реальное конкурирующее решение даёт 409; комментарий сохраняется при GET refresh |
| Новый сигнал | Реальный конфликт версии ЖК; GET refresh, сохранённые title/reason, явное повторное создание |
| История | Loading, настоящие страницы audit с limit=2, typed index error/retry; пустая история — явно введённый fixture |
| PDF | HTML 200 не скачан; ошибка рендера показана; retry скачал настоящий локальный WeasyPrint `%PDF-` |
| Ссылки/адаптивность | Точный href/rel источника, deep link evidence; 1366×768, 375×812, 320×700 без page overflow; keyboard skip link |

AUTH-01 исправлен в AuthProvider: 401 и известные SDK-коды недействительной
сессии убирают profile/workspace, SDK-текст не показывается. Network/refresh outage
показывает безопасную ошибку с возможностью retry и не разлогинивает. Revision
защищает новый вход от позднего 401 старой сессии. Тестовые SDK/HTTP не подменяют
backend-проверку Firebase token или правила доступа в реальной среде.

После этих исправлений: **55 frontend tests passed**, 14 test files; отдельный
TypeScript check и production build успешны. QA adapters не найдены в собранном
`frontend/dist` по их уникальным маркерам. Lockfiles и зависимости не изменены.

Первые browser-прогоны остановились из-за двух ошибок самого нового runner:
он пытался декодировать бинарный upload как текст и выбирал все два источника
вместо нужного checkbox. Исправлены только runner/selector; после этого полный
прогон выше завершён с exit 0. Это не дефекты продукта и не cloud failures.

Read-only HTTPS-проверка Hosting/Cloud Run из этой машины остановилась до сервисов:
egress proxy вернул `Tunnel connection failed: 403 Forbidden`. Это не ответ
приложения и не подтверждение его недоступности. Живой вход/версию, PDF, историю
и screenshot по-прежнему проверяет владелец после публикации.

## Осталось проверить

Браузерная матрица, исправления с regression-тестами, runbook, финальные проверки,
push, PR и CI. Облачные история/PDF/скриншот и второй Windows-ПК остаются ручными
шагами владельца; этот промежуточный отчёт их не объявляет пройденными.
