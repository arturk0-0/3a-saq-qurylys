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
3. Запущен baseline backend suite; результат будет записан после завершения.
4. Следующее: тесты реального Firestore query builder и курсоров, безопасная
   классификация ошибок, проверка сигналов/PDF, deployment-инструкции.

Промежуточный отчёт. Ни новые исправления, ни release gates пока не завершены.
