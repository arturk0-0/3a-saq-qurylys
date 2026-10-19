# SAQ QURYLYS — текущие задачи двух участников

Актуально на 19 октября 2026 по прямому поручению владельца.
**A — друг, B — владелец.** Бывшая третья роль объединена с B.

- **A:** [Issue #20 — дополнительная карта города с объёмными зданиями](https://github.com/arturk0-0/3a-saq-qurylys/issues/20).
  Работает через Codex без Firebase/Google Cloud, ключей, оплаты и ручной настройки.
- **B:** [Issue #21 — застройщик и уполномоченная компания, источники и страницы](https://github.com/arturk0-0/3a-saq-qurylys/issues/21).
  Ведёт сбор, модели/API, необходимый frontend компаний, интеграцию и последующий выпуск.

**Полное распределение, границы файлов и готовые промпты:**
[map-company-split.md](tasks/map-company-split.md).
Самодостаточные ТЗ: [A — карта](tasks/A-city-map.md), [B — компании](tasks/B-company-profiles.md).
По B подготовлен [PR #23](https://github.com/arturk0-0/3a-saq-qurylys/pull/23)
поверх #19; [отчёт](company-profiles-report.md). Merge/CI/совместная приёмка
с картой A отслеживаются отдельно. Старые A-01–04 завершены;
[Issue #9](https://github.com/arturk0-0/3a-saq-qurylys/issues/9) закрыт и не открывается снова.
[Issue #8](https://github.com/arturk0-0/3a-saq-qurylys/issues/8) сохраняет прежнюю общую очередь выпуска B.

## Правила совместной работы

1. Проверить AGENTS, спецификацию, актуальные remote PR, план, WORK_LOG и свой Issue.
   Не повторять готовый код по старым checkbox. Старые PR #1–4 уже включены ранее.
2. Отдельные ветки/PR. Карта A не требует PR #19. B учитывает открытый #19,
   переиспользует его реестры; не теряет его работу при интеграции.
3. A владеет city-map/** и минимальным подключением в ComplexList.tsx;
   B — backend, company frontend, ComplexDetail.tsx, App/routes и shared types.
   Общие стили/QA runner не редактируются одновременно.
4. A ведёт docs/map-handoff.md, B — docs/company-profiles-report.md и общий план/журнал.
5. Тестовые адаптеры только в QA, реальные и учебные объекты не смешиваются.
   Неизвестные факты/координаты не придумываются, R1–R6/auth/rules не меняются.
6. Проверки → небольшие коммиты → push → PR → независимое review/зелёный CI.
   A не выполняет main merge/deploy. B выпускает отдельно из проверенного SHA;
   наличие кода в GitHub не подтверждает публикацию сайта.

История предыдущих очередей, результатов и старых промптов сохранена в
[архиве](archive/two-person-team-2026-10-19-before-map-company.md).
Она не является текущим заданием. Фактическое состояние выпусков —
[DEVELOPMENT_PLAN](DEVELOPMENT_PLAN.md) и [WORK_LOG](WORK_LOG.md).
