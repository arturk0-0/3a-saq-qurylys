from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app(Settings(_env_file=None)))


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "saq-qurylys-api"}
    UUID(response.headers["x-request-id"])
    assert response.headers["cache-control"] == "no-store"


def test_missing_route_has_typed_error(client):
    response = client.get("/api/v1/nonexistent-route")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "HTTP_404"
    assert body["message"] == "Not Found"
    assert body["requestId"] == response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "origin,allowed", [("http://localhost:5173", True), ("https://untrusted.example", False)]
)
def test_cors(client, origin, allowed):
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == (200 if allowed else 400)
    assert response.headers.get("access-control-allow-origin") == (origin if allowed else None)


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://example.com/path",
        "ftp://example.com",
        "https://user:pass@example.com",
        "https://example.com:invalid",
    ],
)
def test_invalid_cors_configuration(origin):
    with pytest.raises(ValidationError):
        Settings(cors_origins=[origin], _env_file=None)


def test_unhandled_error_does_not_leak_details_or_escape_to_server_logs(caplog):
    app = create_app(Settings(_env_file=None))

    @app.get("/test-error")
    def fail():
        raise RuntimeError("private credential")

    # Keep the default raise_server_exceptions=True: an exception reaching the ASGI
    # server would otherwise produce an unsanitized Uvicorn traceback in production.
    with TestClient(app) as client:
        response = client.get("/test-error", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "private credential" not in response.text
    assert "private credential" not in caplog.text
    assert "exception_type=RuntimeError" in caplog.text
    assert response.json()["requestId"] in caplog.text
    assert response.json()["requestId"] == response.headers["x-request-id"]
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["cache-control"] == "no-store"


def test_hosting_origin_preflight_allows_auth_headers_and_rejects_other_origins():
    origin = "https://saq-qurylys.web.app"
    app = create_app(Settings(_env_file=None, cors_origins=[origin]))
    with TestClient(app) as client:
        for candidate, status in [(origin, 200), ("https://other.example", 400)]:
            response = client.options(
                "/api/v1/complexes",
                headers={
                    "Origin": candidate,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
            )
            assert response.status_code == status
        response = client.get("/api/v1/complexes", headers={"Origin": origin})
        assert response.status_code == 401
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["cache-control"] == "no-store"


def test_request_validation_does_not_echo_input():
    app = create_app(Settings(_env_file=None))

    @app.get("/test-validation")
    def validate(count: int):
        return {"count": count}

    with TestClient(app) as client:
        response = client.get("/test-validation", params={"count": "private value"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["requestId"] == response.headers["x-request-id"]
    assert "private value" not in response.text


def test_cors_configuration_from_environment(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:5173"]')
    assert Settings(_env_file=None).cors_origins == ["http://localhost:5173"]


def test_integration_error_log_correlates_request_without_headers_or_body(caplog):
    app = create_app(Settings(_env_file=None))

    @app.post("/test-safe-error")
    def fail():
        raise AppError(503, "AI_MODEL_UNAVAILABLE", "Selected model is unavailable")

    with TestClient(app) as client:
        response = client.post(
            "/test-safe-error",
            headers={"Authorization": "Bearer PRIVATE_TEST_TOKEN"},
            json={"text": "PRIVATE_TEST_ADVERTISEMENT"},
        )
    assert response.status_code == 503
    assert response.json()["requestId"] in caplog.text
    assert "code=AI_MODEL_UNAVAILABLE" in caplog.text
    assert "PRIVATE_TEST_TOKEN" not in caplog.text
    assert "PRIVATE_TEST_ADVERTISEMENT" not in caplog.text
