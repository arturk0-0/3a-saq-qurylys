# Firebase и доступ аналитика

Приложение использует Firebase Authentication, Firestore и Storage проекта `saq-qurylys`.
В этой среде реальные credentials и browser config пока не предоставлены. Ниже —
подготовленные инструкции; подключение к облаку не считается проверенным до реального входа.

## 1. Консоль Firebase

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

Путь — пример, файл не создаётся автоматически. Для Docker:

```bash
docker compose -f compose.yaml -f compose.firebase.yaml up --build --wait
```

Второй Compose-файл монтирует credentials только в backend, read-only. В образ и frontend
файл не попадает. Основной Compose без override работает для health/setup screen.

## 3. Назначить роль и загрузить DEMO

В локальном терминале из `backend/`, с настроенными серверными credentials:

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

Откройте приложение, войдите созданным пользователем. API `/api/v1/me` проверяет подпись,
проект, срок действия, отзыв token и роль через Firebase Admin. Без Bearer token — 401;
без роли — 403; при отключённой/недоступной интеграции — 503. Health остаётся публичным.

Не настраивайте Firebase emulator hosts в рабочей среде. Тестовые адаптеры находятся только
в `backend/tests/`; в приложении нет режима с поддельной авторизацией или локальной БД.
