# Отчёт MON: сбор публикаций и очередь эксперта

17 октября 2026. Ветка `feat/MON-01-public-monitoring`, база main `ed38f00`.
[PR #14](https://github.com/arturk0-0/3a-saq-qurylys/pull/14),
[рабочая задача #13](https://github.com/arturk0-0/3a-saq-qurylys/issues/13).
Это feature-код и локальная проверка, **не обновлённое облачное приложение**.
**Дополнение:** Instagram trial успешно пройден: два поиска, остаток 98;
[актуальная интеграция/лимиты/результаты](instagram-searchapi.md).
Указанные ниже отсутствие provider и MON-IG-02 open относятся к первой фазе.

## Результат первой версии до SearchAPI trial

Выполнены MON-01–08: bounded RSS/Telegram adapters, отдельная реальная очередь,
provenance/дедуп/ревизии, fetch lease и quota до HTTP, опциональный Gemini с общей
квотой до вызова, аудит и версионные решения эксперта, real→real transfer,
frontend источников/находок/запусков и отдельный регулярный CLI worker.
Перенос существующего AI-результата не выполняет новую генерацию.
R1–R6 и значения A=35/YELLOW, B=70/RED, C=10/GREEN не изменены.

Instagram проверен первым: официальные Meta Ads Archive и Hashtag Search docs
прочитаны, Web Ad Library KZ вернула 403. Полный коммерческий Instagram-таргет
только по KZ через стандартный API не подтверждён. Нет Meta credentials/
поставщика; вход/капча не обходились, paid provider не приобретался.
[Источники и точная формулировка ограничения](instagram-feasibility.md).
MON-IG-01 закрыт, MON-IG-02 **открыт**. UI явно показывает это состояние.

План переработан: 50 реализованных baseline задач отделены от MON, оставшихся
10 AI/release gates и 4 отложенных drone-задач. Полный прежний план сохранён
в архиве. Для MON владелец разрешил B необходимый frontend без ожидания A.
Коммиты сохранялись/отправлялись по этапам: `1afbc0e` план/Instagram,
`c0fbc57` adapters, `8ab4a8a` backend, `a5fecc3` frontend; документация отдельно.

## Фактические проверки

| Проверка | Результат/граница |
| --- | --- |
| Backend Ruff check/format | Passed; финальный полный pytest — **403 passed** |
| Backend MON/parser набор | **58 passed** внутри общего прогона; ошибки доступа/формата/bytes/deadline/markup, auth, quota, lease CAS, ревизии, fairness, сохранение параллельного review |
| Native Firestore SDK | **13 passed**, из них 2 новых MON; изолированный demo emulator, client rules deny; не облачные indexes/IAM |
| Frontend Vitest | **68 passed**, из них 4 новых MON: opt-in, разграничение Instagram/snippet, реальный для API-контракта 409/refresh без потери notes, запрет DEMO/неизвестная дата |
| TypeScript/production build | Passed; основной JS **539.60 kB / gzip 163.18 kB**, существующее предупреждение >500 kB остаётся для A-02 |
| Chromium | **17 групп / 848 запросов**, без page errors/внешних запросов, размеры 1366/375/320; исходный пользовательский путь, настоящий WeasyPrint PDF, MON source→queue→review/409→AI→reload |
| Прямые HTTP-пробы публичных адаптеров | 8 RSS-результатов/20 Telegram-постов; только чтение, без записи в Firebase/без AI. Не измерение качества/охвата |
| Независимый read-only review | Отдельный агент Codex не нашёл blockers в проверенном diff; это не human GitHub approval |
| GitHub CI | Проверять итоговый head в PR #14; локальный успех не заменяет CI/merge |

Команды из корня (зависимости из lockfiles уже установлены):

```bash
(cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest -q)
python3 backend/qa/firestore/run.py
(cd frontend && npm test -- --run && npm run build)
SAQ_QA_ARTIFACTS=/tmp/saq-monitoring-browser-final python3 frontend/qa/release/run.py
```

Browser QA использует настоящий локальный FastAPI/domain services и
**явные MemoryStore/Auth/HTTP MockTransport**. Тестовая реклама вымышленная,
помечена LOCAL QA/DEMO и не является настоящим кейсом застройщика.
Скриншоты проверены визуально; исправлены отступы и перенос mobile topbar.
Первый прогон новых тестов обнаружил ошибки самих test fixtures/неоднозначный
locator, они исправлены; финальные прогоны перечислены выше.

Артефакты только в текущей временной среде:
`/tmp/saq-firestore-integration-rbes7isl/`,
`/tmp/saq-monitoring-browser-final/`,
`/tmp/saq-monitoring-final-build.log`.
Browser screenshot имена `monitoring-desktop-test-adapters.png` и
`monitoring-mobile-test-adapters.png`. Это не опубликованные данные/результаты
живого Gemini. Docker smoke этой новой версии проверяет CI; локально здесь
повторно не запускался.

## Открыто и с чего продолжать

1. **MON-IG-02**: выбрать разрешённый источник Instagram Ads KZ; до интеграции
   проверить реальный sample, страну/язык/creative/URL/date/provenance, условия и цену.
   Хэштеги и индексированные посты не равны таргету.
2. **MON-09**: review/merge конкретного SHA, сборка нового API image и frontend,
   готовые новые Firestore indexes, Job/Scheduler, два штатных сбора с закрытым
   браузером. [Точные команды включения](cloud-deployment.md#7-мониторинг-job-и-расписание).
   Здесь нет ADC для deployment, ничего в живой инфраструктуре не менялось.
3. Реальные публикации можно проверять в очереди при DEMO-only, но привязка к ЖК
   потребует документированного real registry в согласованной среде. Нельзя
   приписывать их seed-объектам. Обычный ручной DEMO flow остаётся отдельным.
4. Измерить precision/recall фильтра на разрешённом RU/KZ sample; возможны
   статьи/вторичное жильё и пропуски без города. Сейчас нет утверждения, что
   обнаружена именно несанкционированная реклама или обеспечен полный охват.
5. Ограничения первой версии: последнее текстовое окно/30 записей, без медиа/
   Stories/полного архива, max20 источников без удаления/изменения target,
   без UI сравнения ревизий; первый список real ЖК ограничен100.
6. Crash после AI reservation может оставить running. Автоматического сброса нет;
   [административная процедура](monitoring.md#восстановление-после-прерывания)
   сохраняет историю/квоты и не запускает платный retry вслепую.

Никаких paid Gemini-запросов, Meta login/provider регистрации, новых секретов,
изменения cloud IAM/rules, deployment или merge main в этой задаче не выполнялось.
Сохранённый источник/heartbeat worker не доказывает установленный Scheduler.
