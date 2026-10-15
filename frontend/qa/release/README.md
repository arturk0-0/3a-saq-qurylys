# Локальная браузерная проверка release

Это **тестовые адаптеры**, не режим демонстрации организаторам и не Firebase emulator.
Обычные `vite.config.ts`, `main.tsx`, backend и deploy-файлы их не импортируют.
Запускаются настоящие UI, AuthProvider, API routes, валидация, сервисы, скоринг и
WeasyPrint. Внешние зависимости заменены существующими `MemoryStore`, `FakeFiles`,
`GeminiClient` с `httpx.MockTransport` и явным browser Auth adapter.
Каждый запуск создаёт новую память с DEMO seed. Живых ключей, данных и AI-запросов нет.

Сначала выполните установки по lockfiles из README. Для проверки нужен уже
доступный Python Playwright и Chromium; это отдельный QA-инструмент, не зависимость
приложения. Он уже установлен в использованной cloud-среде. На другой Linux-машине
можно установить его отдельно от backend:

```bash
python3 -m venv /tmp/saq-browser-tools
/tmp/saq-browser-tools/bin/pip install playwright==1.62.0 pillow==12.3.0
/tmp/saq-browser-tools/bin/python -m playwright install chromium
```

При необходимости укажите путь к Chromium через `SAQ_CHROMIUM`. Runner сначала
использует системный `chromium`, иначе установленный Playwright browser. В проверенной
cloud-среде Playwright 1.62.0, Pillow 12.3.0 и системный Chromium уже присутствовали;
дополнительные установки browser tools не требовались.

Из корня репозитория с установленными `backend/.venv` и `frontend/node_modules`:

```bash
python3 frontend/qa/release/run.py
```

Здесь `python3` должен иметь Playwright/Pillow. Если он установлен в отдельном
venv, используйте `/tmp/saq-browser-tools/bin/python` вместо `python3`.
При другом расположении backend Python задайте `SAQ_BACKEND_PYTHON`.
Runner предназначен для Linux (включая подготовленную Linux-среду WSL),
Windows-прогон не выполнялся.
Runner проверяет, что 8011 и 5181 свободны, запускает только loopback QA API и Vite,
ждёт readiness, запускает Chromium и завершает свои процессы. Прокси, CA и TLS
настройки не ослабляются. Переменные приложения/credentials исключаются из
окружения дочерних процессов, `.env` не загружается. Внешние browser requests
заблокированы; непредвиденная попытка делает прогон неуспешным.

Ожидается последовательность `PASS` и exit 0. Полный underlying exit status
сохраняется. Артефакты текущего запуска: `/tmp/saq-release-browser/results.json`,
логи API/Vite, настоящий локальный PDF, мобильный снимок. При сбое остаются
`failure.png`/`failure.txt`. Это синтетические данные. Путь можно переопределить
`SAQ_QA_ARTIFACTS`; перед повтором выбирайте новую папку, чтобы не спутать старые
артефакты с текущими. Пагинация проверяется настоящим API с уменьшением limit
в browser transport; ошибки Gemini/HTTP и пустая история вводятся явно.

Этот runner проверяет локальную Linux-реализацию. Он не проверяет IAM, реальные
Firebase tokens/rules/index deployment, качество Gemini, Windows или опубликованную
версию. Ручная облачная приёмка: `docs/judge-runbook.md`.
