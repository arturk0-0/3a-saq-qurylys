from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from firebase_admin import auth

from app.api.dependencies import admin_user, get_runtime
from app.core.config import Settings
from app.core.errors import AppError
from app.core.firebase import FirebaseRuntime
from app.main import create_app
from app.models.auth import Principal


def test_anonymous_cannot_access_identity():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get("/api/v1/me")
        assert response.status_code == 401
        assert response.json()["code"] == "AUTH_REQUIRED"
        assert response.headers["www-authenticate"] == "Bearer"
        assert client.get("/api/v1/health").status_code == 200


def test_missing_firebase_configuration_does_not_enable_fake_login():
    with TestClient(create_app(Settings(_env_file=None, firebase_enabled=False))) as client:
        response = client.get("/api/v1/me", headers={"Authorization": "Bearer token"})
        assert response.status_code == 503
        assert response.json()["code"] == "INTEGRATION_UNAVAILABLE"


def test_token_is_verified_with_revocation_check(monkeypatch):
    runtime = FirebaseRuntime(Settings(_env_file=None, firebase_enabled=True))
    sdk_app = object()
    monkeypatch.setattr(runtime, "app", lambda: sdk_app)
    verify = Mock(return_value={"uid": "analyst-1", "role": "analyst", "email": "a@example.test"})
    monkeypatch.setattr(auth, "verify_id_token", verify)
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_runtime] = lambda: runtime
    with TestClient(app) as client:
        response = client.get("/api/v1/me", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200
    assert response.json()["uid"] == "analyst-1"
    verify.assert_called_once_with(
        "test-token", app=sdk_app, check_revoked=True, clock_skew_seconds=10
    )


@pytest.mark.parametrize("role", [None, "viewer", "owner", "ANALYST"])
def test_unsigned_or_unrecognised_role_cannot_access(monkeypatch, role):
    runtime = FirebaseRuntime(Settings(_env_file=None, firebase_enabled=True))
    monkeypatch.setattr(runtime, "app", lambda: object())
    monkeypatch.setattr(auth, "verify_id_token", lambda *a, **k: {"uid": "u", "role": role})
    with pytest.raises(AppError) as exc:
        runtime.verify_token("token")
    assert exc.value.status_code == 403


def test_invalid_token_is_rejected_without_echo(monkeypatch):
    runtime = FirebaseRuntime(Settings(_env_file=None, firebase_enabled=True))
    monkeypatch.setattr(runtime, "app", lambda: object())
    monkeypatch.setattr(
        auth, "verify_id_token", Mock(side_effect=auth.InvalidIdTokenError("secret"))
    )
    with pytest.raises(AppError) as exc:
        runtime.verify_token("token")
    assert exc.value.status_code == 401
    assert "secret" not in exc.value.message


def test_identity_endpoint_does_not_accept_client_role_header():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get("/api/v1/me", headers={"X-Role": "admin", "X-User-ID": "admin"})
    assert response.status_code == 401


def test_analyst_cannot_perform_admin_operation():
    with pytest.raises(AppError) as exc:
        admin_user(Principal(uid="analyst", role="analyst"))
    assert exc.value.status_code == 403


def test_cors_permits_authorization_header_only_for_allowed_origin():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.options(
            "/api/v1/me",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
