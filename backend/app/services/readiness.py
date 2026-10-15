"""Read-only setup checks; never expose credential values or provider error bodies."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import httpx
from firebase_admin import auth

from app.core.config import Settings
from app.core.firebase import FirebaseRuntime


@dataclass(frozen=True)
class Check:
    name: str
    status: Literal["ok", "failed", "skipped"]
    message: str


def check_connections(
    settings: Settings,
    *,
    online: bool = False,
    require_ai: bool = False,
    runtime_factory: Callable = FirebaseRuntime,
    transport: httpx.BaseTransport | None = None,
) -> list[Check]:
    checks = []
    firebase_configured = settings.firebase_enabled
    if not firebase_configured:
        checks.append(Check("Firebase config", "failed", "Установите FIREBASE_ENABLED=true."))
    elif settings.firebase_credentials_path and not settings.firebase_credentials_path.is_file():
        firebase_configured = False
        checks.append(
            Check(
                "Firebase config",
                "failed",
                "Файл FIREBASE_CREDENTIALS_PATH не найден. "
                "Для Docker проверьте credentials override.",
            )
        )
    else:
        checks.append(
            Check("Firebase config", "ok", "Настройки заданы; доступ проверяется с --online.")
        )

    bucket_configured = bool(settings.firebase_storage_bucket)
    if not bucket_configured or "://" in settings.firebase_storage_bucket:
        bucket_configured = False
        checks.append(
            Check(
                "Storage config", "failed", "Укажите FIREBASE_STORAGE_BUCKET без gs:// и https://."
            )
        )
    else:
        checks.append(Check("Storage config", "ok", "Имя bucket задано."))

    ai_configured = bool(settings.gemini_model and settings.gemini_api_key.get_secret_value())
    checks.append(
        Check(
            "Gemini config",
            "ok" if ai_configured else "failed" if require_ai else "skipped",
            "Ключ и модель заданы."
            if ai_configured
            else "Задайте GEMINI_API_KEY и GEMINI_MODEL для анализа; "
            "остальные модули работают без AI.",
        )
    )
    if not online:
        return checks

    def probe(name: str, operation: Callable[[], object], failure: str) -> None:
        try:
            operation()
        except Exception:
            # Provider exceptions can contain tokens, private paths, URLs or user data.
            checks.append(Check(name, "failed", failure))
        else:
            checks.append(Check(name, "ok", "Ответ сервиса получен; данные не изменялись."))

    if firebase_configured:
        runtime = runtime_factory(settings)
        try:
            probe(
                "Firebase Authentication",
                lambda: auth.list_users(max_results=1, app=runtime.app()),
                "Проверьте Admin credentials, проект, права Authentication и доступ к Google API.",
            )
            probe(
                "Firestore",
                lambda: list(runtime.db().collection("complexes").limit(1).stream(timeout=10)),
                "Проверьте создание базы Firestore, Admin credentials, IAM и доступ к Google API.",
            )
            if bucket_configured:

                def storage_metadata():
                    runtime.bucket().reload(timeout=10, retry=None)

                probe(
                    "Firebase Storage",
                    storage_metadata,
                    "Проверьте bucket, billing, Admin credentials и право storage.buckets.get.",
                )
        finally:
            runtime.close()
    else:
        checks.append(Check("Firebase online", "skipped", "Сначала исправьте Firebase config."))

    if ai_configured:

        def model_metadata():
            url = "https://generativelanguage.googleapis.com/v1beta/models/" + settings.gemini_model
            with httpx.Client(timeout=10, transport=transport) as client:
                response = client.get(
                    url, headers={"x-goog-api-key": settings.gemini_api_key.get_secret_value()}
                )
            response.raise_for_status()
            if "generateContent" not in response.json().get("supportedGenerationMethods", []):
                raise ValueError("Selected model does not support generateContent")

        probe(
            "Gemini model",
            model_metadata,
            "Проверьте ключ, GEMINI_MODEL, включение API, ограничения ключа и доступ к Google API.",
        )
    return checks
