# Firebase и доступ аналитика

Приложение использует Firebase Authentication, Firestore и Storage проекта `saq-qurylys`.
Для просмотра https://saq-qurylys.web.app нужна только приватно выданная учётная
запись. Организаторам сайта не нужны Admin JSON или ключ Gemini. Владелец подтвердил
облачный вход, DEMO, создание объявления и текстовый Gemini-анализ; облачные история,
PDF и скриншоты требуют отдельной приёмки после публикации исправлений.
Ниже — настройка владельцем **локального backend** или отдельного учебного проекта.
В этой ночной проверке облачные credentials не использовались и данные не менялись.

## 1. Консоль Firebase

Это административная подготовка проекта, не обязательные действия каждого
организатора при входе на сайт. Для существующего проекта сначала проверьте его
состояние; применение rules/индексов и создание ресурсов выполняет только владелец.

1. Откройте проект `saq-qurylys` в Firebase Console.
2. В Authentication включите Email/Password и создайте отдельную учётную запись аналитика.
3. В настройках Authentication добавьте `localhost` в Authorized domains для локального запуска.
4. Создайте Firestore database и Storage bucket, если они ещё не созданы. Проверьте тариф/квоты.
5. Зарегистрируйте Web app и скопируйте browser config в соответствующие `VITE_FIREBASE_*`
   поля корневого `.env`. Это публичная конфигурация клиента, не Admin private key.
6. Настройте Firestore/Storage rules по файлам в корне. Они запрещают прямые клиентские
   обращения: данные читает/меняет FastAPI с Admin credentials. Перед применением к уже
   используемому проекту убедитесь, что других клиентов, зависящих от прежних правил, нет.
7. Разверните индексы из firestore.indexes.json и дождитесь готовности.
   При установленном Firebase CLI: firebase deploy --only firestore:indexes --project saq-qurylys.
   Для rules: firebase deploy --only firestore:rules,storage --project saq-qurylys.
   Эти команды здесь не выполнялись: требуется доступ к вашему проекту.

## 2. Серверные credentials

Предпочтительны Application Default Credentials или отдельный service account с минимальными
правами к нужным Firebase сервисам. JSON private key нельзя класть в Git или отправлять в чат.
Для локального запуска сохраните файл в приватной папке и укажите полный путь в
`FIREBASE_CREDENTIALS_PATH`. Если путь пуст, Firebase Admin использует стандартный ADC,
включая `GOOGLE_APPLICATION_CREDENTIALS` там, где он уже правильно настроен.

В `.env`:

```dotenv
FIREBASE_ENABLED=true
FIREBASE_DEMO_ONLY=true
FIREBASE_PROJECT_ID=saq-qurylys
FIREBASE_CREDENTIALS_PATH=C:/private/saq-firebase-admin.json
FIREBASE_CREDENTIALS_FILE=C:/private/saq-firebase-admin.json
FIREBASE_STORAGE_BUCKET=your-actual-bucket-name
```

Для Linux используйте абсолютный путь к собственному приватному файлу, например
`/home/your-user/private/saq-firebase-admin.json`. `FIREBASE_CREDENTIALS_PATH` нужен
при нативном запуске backend; `FIREBASE_CREDENTIALS_FILE` — путь **на хосте** для
Compose override. Внутри контейнера путь будет `/run/secrets/firebase-admin.json`,
override задаёт его сам. Не переносите чужие credentials вместе с исходниками.

Для frontend в корневом `.env` обязательны `VITE_FIREBASE_API_KEY`,
`VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_APP_ID`
из Web app config того же проекта. Для локального Vite оставьте `VITE_API_BASE_URL=`
пустым: `/api/v1` идёт на локальный backend. `GEMINI_API_KEY` и `GEMINI_MODEL`
нужны только backend; без них анализ недоступен, ручная проверка данных сохраняется.
Выбранная владельцем Cloud Run модель — `gemini-3.5-flash-lite`; её наличие в
документе не подтверждает доступность для другого проекта или успешную генерацию.

Путь — пример, файл не создаётся автоматически. Для Docker:

```bash
docker compose -f compose.yaml -f compose.firebase.yaml up --build --wait
```

Второй Compose-файл монтирует credentials только в backend, read-only. В образ и frontend
файл не попадает. Основной Compose без override работает для health/setup screen.

## 3. Назначить роль и загрузить DEMO

Это **изменение облачных данных/claims**, только для владельца и явно выбранного
учебного проекта. Обычный вход/перезапуск приложения не требует повторного seed
или назначения роли. В локальном терминале из `backend/`, после `uv sync --frozen`,
с собственными настроенными серверными credentials:

```bash
uv run --frozen python -m app.cli.role FIREBASE_USER_UID analyst --project-confirm saq-qurylys
uv run --frozen python -m app.cli.seed validate
uv run --frozen python -m app.cli.seed import --project-confirm saq-qurylys --apply
```

UID берётся из Authentication → Users. Команда роли меняет только custom claim `role`,
сохраняет остальные claims и отзывает старые сессии; пользователь должен войти заново.
Доступ дают только роли `analyst`/`admin` из проверенного Firebase ID token.
Переданный клиентом заголовок роли и email сами по себе не дают прав.

Seed загружается одной транзакцией, создаёт только отсутствующие DEMO-документы и маркер
версии. Повторный запуск после успешного импорта ничего не меняет. Совпадение ID с
не-DEMO документом отменяет всю операцию. Правки аналитиков не перезаписываются.

## 4. Проверка

Перед входом можно проверить конфигурацию и доступ **без изменения облачных данных**:

```bash
uv run --frozen python -m app.cli.check
uv run --frozen python -m app.cli.check --online --require-ai
```

Для Docker из корня репозитория:

```bash
docker compose -f compose.yaml -f compose.firebase.yaml exec backend .venv/bin/python -m app.cli.check --online --require-ai
```

Команда выводит только статусы и подсказки, без ключей, содержимого credentials или
ответов с пользовательскими данными. `--online` читает Authentication, один документ
Firestore, метаданные bucket и метаданные выбранной Gemini-модели; генерацию не запускает.
Для bucket-проверки нужно право `storage.buckets.get`; отрицательный результат требует
проверки IAM и не доказывает, что отдельное право загрузки файлов отсутствует.
Без `--require-ai` ненастроенный Gemini отмечается SKIPPED. Код возврата 1 означает
найденную проблему; 0 не заменяет вход аналитика, seed, проверку клиентских rules,
загрузку изображения или генерацию. Для автоматизации доступен `--json`.

Откройте приложение, войдите созданным пользователем. API `/api/v1/me` проверяет подпись,
проект, срок действия, отзыв token и роль через Firebase Admin. Без Bearer token — 401;
без роли — 403; при отключённой/недоступной интеграции — 503. Health остаётся публичным.

Не настраивайте Firebase emulator hosts в рабочей среде. Production entry не имеет
режима с поддельной авторизацией или локальной БД. Существующие backend test adapters
и отдельный opt-in browser runner `frontend/qa/release/` используются только для
локального QA, с явной плашкой и изолированной памятью; ими нельзя подтверждать
готовность живой Firebase-интеграции.
