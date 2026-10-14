import logging
import threading
from uuid import uuid4

import firebase_admin
from firebase_admin import auth, credentials, firestore, storage
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError, IntegrationUnavailable
from app.models.auth import Principal

logger = logging.getLogger(__name__)


class FirebaseRuntime:
    """Lazy SDK initialization; missing cloud configuration never opens an auth bypass."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._app: firebase_admin.App | None = None
        self._lock = threading.Lock()

    def app(self) -> firebase_admin.App:
        if not self.settings.firebase_enabled:
            raise IntegrationUnavailable("Firebase")
        with self._lock:
            if self._app is None:
                try:
                    credential = (
                        credentials.Certificate(str(self.settings.firebase_credentials_path))
                        if self.settings.firebase_credentials_path
                        else credentials.ApplicationDefault()
                    )
                    self._app = firebase_admin.initialize_app(
                        credential,
                        {
                            "projectId": self.settings.firebase_project_id,
                            "storageBucket": self.settings.firebase_storage_bucket or None,
                            "httpTimeout": 10,
                        },
                        name=f"saq-{uuid4().hex}",
                    )
                except Exception as exc:
                    logger.error("Firebase initialization failed: %s", type(exc).__name__)
                    raise IntegrationUnavailable("Firebase") from None
            return self._app

    def verify_token(self, token: str) -> Principal:
        app = self.app()
        try:
            claims = auth.verify_id_token(token, app=app, check_revoked=True, clock_skew_seconds=10)
        except (
            auth.InvalidIdTokenError,
            auth.ExpiredIdTokenError,
            auth.RevokedIdTokenError,
            auth.UserDisabledError,
            auth.UserNotFoundError,
            ValueError,
        ):
            raise AppError(401, "INVALID_TOKEN", "Sign in again") from None
        except Exception as exc:
            logger.error("Firebase token verification unavailable: %s", type(exc).__name__)
            raise IntegrationUnavailable("Firebase Authentication") from None
        if claims.get("role") not in {"analyst", "admin"}:
            raise AppError(403, "ROLE_REQUIRED", "Analyst or admin role is required")
        try:
            return Principal(
                uid=claims["uid"],
                role=claims["role"],
                email=claims.get("email"),
                display_name=claims.get("name"),
            )
        except (KeyError, ValidationError):
            raise AppError(401, "INVALID_TOKEN", "Sign in again") from None

    def db(self):
        try:
            return firestore.client(app=self.app())
        except AppError:
            raise
        except Exception as exc:
            logger.error("Firestore initialization failed: %s", type(exc).__name__)
            raise IntegrationUnavailable("Firestore") from None

    def bucket(self):
        if not self.settings.firebase_storage_bucket:
            raise IntegrationUnavailable("Firebase Storage")
        try:
            return storage.bucket(app=self.app())
        except AppError:
            raise
        except Exception as exc:
            logger.error("Storage initialization failed: %s", type(exc).__name__)
            raise IntegrationUnavailable("Firebase Storage") from None

    def close(self) -> None:
        with self._lock:
            if self._app is not None:
                firebase_admin.delete_app(self._app)
                self._app = None
