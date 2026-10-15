# Backend reliability — ночная задача 15 октября 2026

Ветка: `fix/backend-demo-reliability`. База: `dbeecb3`
(`feat/DEPLOY-01-hosting-cloud-run`). Начало: 16:49 UTC; предельное время
работы — 21:49 UTC. Изменения только в разрешённой backend/deploy/docs области.
Frontend независимо ведёт другой участник. Main и живая инфраструктура не меняются.

## Подтверждённое состояние перед работой

- Владелец развернул Hosting: https://saq-qurylys.web.app и Cloud Run:
  https://saq-qurylys-api-722228028571.europe-west1.run.app.
- По результатам владельца работают вход, DEMO seed, новое объявление,
  реальный анализ Gemini и отдельное подтверждение R2: 10 → 35/YELLOW.
- Metadata GET для `gemini-2.5-flash-lite` вернул 200, но generateContent — 404:
  модель недоступна новым пользователям. После выбора владельцем
  `gemini-3.5-flash-lite` анализ завершился успешно. Это проверка одного текста,
  не измерение качества/стоимости или проверка скриншотов.
- История сигнала показала общую ошибку. Причина не установлена; deployment
  Firestore indexes и облачные PDF/Storage/screenshot проверки не подтверждены.
- В Codex нет подтверждённых owner credentials Cloud Shell. Платных AI-запросов
  и изменений живого проекта в этой задаче не будет.

## Ход работы и продолжение

1. Проверены удалённые heads: feature-база `dbeecb3`, main `0f7c23a`.
2. Изучены AGENTS, PROJECT_SPEC, DEVELOPMENT_PLAN, WORK_LOG и существующий код.
3. Baseline: 140 passed / 4 failed. Все четыре сбоя в readiness-тестах:
   `_env_file=None` отключает dotenv, но не настройки процесса. Тестовый helper
   теперь явно задаёт пустые credentials/model/bucket и выключенный Firebase;
   настройки рабочего приложения не менялись.
4. Готова классификация Gemini: `AI_NOT_CONFIGURED`, `AI_CREDENTIALS`,
   `AI_ACCESS_DENIED`, `AI_MODEL_UNAVAILABLE`, `AI_PROVIDER_QUOTA`, `AI_TIMEOUT`,
   `AI_NETWORK`, `AI_TEMPORARY`, `AI_REQUEST_REJECTED`, `AI_INVALID_RESPONSE`.
   Логи содержат только фиксированный код/HTTP-статус; provider body, exception
   text, source text, ключи и URL не выводятся. Нет fallback-модели; один повтор
   только явных 502/503/504, без повтора timeout/неопределённого сетевого сбоя.
   Некорректные формы JSON-конверта больше не приводят к необработанному 500.
   Readiness прямо говорит: успешная metadata не подтверждает generateContent.
5. Проверка этапа: 61 passed (Gemini errors / analysis / readiness / evaluation),
   Ruff по изменённым файлам прошёл. Только MockTransport/тестовые адаптеры.
6. Следующее: Firestore SDK query/cursor/index проверки, сигналы/PDF и deployment.

Промежуточный отчёт. Ни новые исправления, ни release gates пока не завершены.
