# Единая реклама · совместная интеграция A и B

20 октября 2026. Backend B объединён через [PR #32](https://github.com/arturk0-0/3a-saq-qurylys/pull/32),
коммит main `c3ac492`. Frontend A (`af81ff9`) сохранён целиком; совместная ветка
и исправления B объединены через [PR #33](https://github.com/arturk0-0/3a-saq-qurylys/pull/33).
Это отчёт реализации и локальных проверок, не публикации на облачный сайт.

## Итоговый путь

В меню одна «Реклама»: все материалы и источники/расписание. Новый текст или
поддерживаемое загруженное изображение ставится сервером в очередь анализа.
Повторные публикации объединены с сохранением оригиналов. Аналитик видит
отдельно предварительный приоритет и подтверждённые риски и сохраняет выбранные
решения одной операцией. Старые файлы, документы, компании, карта, дрон,
рекламный след, сигналы и PDF сохранены. Готовность строительства не возвращена.

## Исправлено при независимом review и интеграции

- Повторное нажатие показа той же цитаты после ручного выбора другой публикации
  теперь вновь выбирает её оригинал. Запрос выбора имеет sequence; новая
  регрессия проверяет именно повторное действие.
- Старые advertisement/finding ссылки разрешаются серверным GET material по
  legacy ID и открывают точный канонический материал, сохраняя query. Архив
  остаётся явной ссылкой для прежней истории/файлов и fallback при ошибке.
- Решение «Недостаточно данных» автоматически оставляет материал для проверки.
  Противоречивое `insufficient + reviewed` блокируется до отправки; серверный
  guard сохранён, тестовые адаптеры также не принимают такой payload.
- Исправления не меняют подтверждённую формулу R1–R6, квоты, auth/rules,
  данные или тексты оригиналов. Код B и A объединён без конфликтов.

## Фактические проверки

- **133 frontend tests, 32 файла — passed**, typecheck и production build passed.
  Начальный JS 442.69 kB / gzip 139.32 kB, review chunk 22.23 kB.
- **11 browser contract групп — passed**: private file, состояния/ошибки,
  409/draft/явное подтверждение обновления, lost response/идемпотентный повтор,
  фильтры/cursor, источники, старые ID, карта/компании/дрон/сигнал/PDF,
  keyboard/reduced-motion, 1440/375/320 и отсутствие горизонтального overflow.
  Materials в этом наборе — явно заданные golden DTO, не реализация скоринга.
- **5 browser native integration групп — passed**: настоящий API/очередь B,
  дубль двух платформ с одним вызовом MockTransport, одно review → evidence/
  persisted risk 35 → история → сигнал snapshot35 → настоящий PDF WeasyPrint.
  Старый ID тоже проходит реальный resolver. Нет подмены materials/скоринга;
  Auth, MemoryStore, файлы и внешние providers — изолированные тестовые адаптеры.
- Backend #32 до объединения: **558 unit tests**, **19 native Firestore SDK
  integration tests**, Ruff/format и все пять CI jobs passed. Совместное дерево объединено в main (`71ec160`);
  [все пять CI jobs прошли](https://github.com/arturk0-0/3a-saq-qurylys/actions/runs/39475456531).
- **Настоящий persistent local-demo + новый UI — passed**: login, intake,
  автоматический локальный анализ, одно review → 35, reload с сохранённым
  комментарием/историей, 1440/375/320; нет external requests/page errors.
  Использованы LocalStore/LocalFiles и явные учебные providers, не Gemini.
- Git diff --check, Ruff/format Python QA — passed. Два независимых read-only
  review; найденные проблемы исправлены и покрыты регрессиями.

Локальные артефакты сессии:
`/tmp/saq-unified-tests-verified.log`, `/tmp/saq-unified-build-verified.log`,
`/tmp/saq-unified-release-contract/` (11), `/tmp/saq-unified-release-native/` (5).
Дополнительные снимки/результат local-demo:
`/tmp/saq-unified-persistent-browser/`.
Команды воспроизведения: `frontend/qa/unified-advertising/README.md`.

## Границы выпуска

Платных Gemini/SearchAPI вызовов и деплоя нет. Нет проверки качества настоящей
модели, реальных ролей/Firestore IAM или опубликованного сайта. Внешнее видео и
превью не выдаются за проанализированное видео. Дрон не меняет рекламный риск.
Облачная публикация и приёмка worker/прав/private files/review остаются отдельной
задачей MAT-DEPLOY. Проверен Chromium Linux; Safari/iOS/Windows не проверялись.
