import re
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


@pytest.mark.parametrize(
    "authorization,status,code",
    [
        (None, 401, "AUTH_REQUIRED"),
        ("Basic forged", 401, "AUTH_REQUIRED"),
        ("Bearer invalid-test-token", 401, "INVALID_TOKEN"),
        ("Bearer " + "x" * 8193, 401, "INVALID_TOKEN"),
        ("Bearer valid-token-without-role", 403, "ROLE_REQUIRED"),
    ],
)
def test_all_business_routes_reject_before_opening_cloud_resources(
    monkeypatch, authorization, status, code
):
    """Exercise real dependencies; only the SDK identity provider is a test adapter."""
    app = create_app(Settings(_env_file=None, firebase_enabled=True))
    runtime = app.state.firebase
    monkeypatch.setattr(runtime, "app", lambda: object())
    monkeypatch.setattr(runtime, "db", Mock(side_effect=AssertionError("Must not open DB")))
    monkeypatch.setattr(runtime, "bucket", Mock(side_effect=AssertionError("Must not open bucket")))

    def verify(token, **kwargs):
        if token == "valid-token-without-role":
            return {"uid": "test-viewer", "role": "viewer"}
        raise auth.InvalidIdTokenError("PRIVATE_TEST_TOKEN_DETAIL")

    monkeypatch.setattr(auth, "verify_id_token", verify)
    headers = {"X-Role": "admin", "X-User-ID": "forged-admin"}
    if authorization:
        headers["Authorization"] = authorization
    protected = 0
    with TestClient(app) as client:
        for path, methods in app.openapi()["paths"].items():
            if path == "/api/v1/health":
                continue
            # Valid syntax prevents path validation from obscuring authentication checks.
            url = re.sub(r"\{([^}]+)\}", lambda m: "1" if m[1] == "version" else "test-id", path)
            for method in methods:
                if method not in {"get", "post", "patch"}:
                    continue
                response = client.request(method, url, headers=headers, json={})
                assert response.status_code == status, (method, path, response.text)
                assert response.json()["code"] == code
                assert response.headers["cache-control"] == "no-store"
                assert "PRIVATE_TEST_TOKEN_DETAIL" not in response.text
                protected += 1
    assert protected > 0
    runtime.db.assert_not_called()
    runtime.bucket.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        auth.ExpiredIdTokenError("PRIVATE_TEST_DETAIL", None),
        auth.RevokedIdTokenError("PRIVATE_TEST_DETAIL"),
        auth.UserDisabledError("PRIVATE_TEST_DETAIL"),
        auth.UserNotFoundError("PRIVATE_TEST_DETAIL"),
    ],
)
def test_expired_revoked_or_disabled_identity_is_rejected_without_detail(
    monkeypatch, caplog, error
):
    app = create_app(Settings(_env_file=None, firebase_enabled=True))
    monkeypatch.setattr(app.state.firebase, "app", lambda: object())
    monkeypatch.setattr(auth, "verify_id_token", Mock(side_effect=error))
    with TestClient(app) as client:
        response = client.get("/api/v1/me", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"
    assert response.headers["www-authenticate"] == "Bearer"
    assert "PRIVATE_TEST_DETAIL" not in response.text + caplog.text
