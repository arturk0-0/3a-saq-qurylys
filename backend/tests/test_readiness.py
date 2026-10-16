import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from app.core.config import Settings
from app.services.readiness import check_connections


def settings(**values):
    # _env_file=None disables dotenv, but does not disable process environment bindings.
    defaults = {
        "firebase_enabled": False,
        "firebase_credentials_path": None,
        "firebase_storage_bucket": "",
        "gemini_api_key": "",
        "gemini_model": "",
    }
    return Settings(_env_file=None, **(defaults | values))


def test_missing_config_fails_without_starting_external_calls():
    runtime = Mock()
    checks = check_connections(settings(), online=True, require_ai=True, runtime_factory=runtime)
    assert {item.name for item in checks if item.status == "failed"} == {
        "Firebase config",
        "Storage config",
        "Gemini config",
    }
    runtime.assert_not_called()


def test_missing_credential_file_and_bucket_scheme_are_actionable(tmp_path):
    checks = check_connections(
        settings(
            firebase_enabled=True,
            firebase_credentials_path=tmp_path / "missing-private-key.json",
            firebase_storage_bucket="gs://demo-bucket",
        )
    )
    assert checks[0].status == "failed" and "FIREBASE_CREDENTIALS_PATH" in checks[0].message
    assert checks[1].status == "failed" and "без gs://" in checks[1].message
    assert checks[2].status == "skipped"


@pytest.mark.parametrize("status", [200, 403, 404, 429, 500])
def test_gemini_metadata_is_read_only_and_never_leaks_keys_or_error_bodies(status):
    secret = "private-test-value-must-never-be-printed"

    def handler(request):
        assert request.method == "GET"
        assert request.headers["x-goog-api-key"] == secret
        assert secret not in str(request.url)
        return httpx.Response(
            status, json={"supportedGenerationMethods": ["generateContent"], "privateError": secret}
        )

    checks = check_connections(
        settings(gemini_api_key=secret, gemini_model="test-model"),
        online=True,
        transport=httpx.MockTransport(handler),
    )
    result = next(item for item in checks if item.name == "Gemini model")
    assert result.status == ("ok" if status == 200 else "failed")
    if status == 200:
        assert "generateContent не выполнялся" in result.message
    assert secret not in json.dumps([item.__dict__ for item in checks])


def test_firebase_checks_continue_independently_and_close_runtime(monkeypatch):
    runtime = Mock()
    runtime.db.return_value.collection.return_value.limit.return_value.stream.return_value = []
    runtime.bucket.return_value.reload.side_effect = RuntimeError("PRIVATE TOKEN")
    list_users = Mock(return_value=SimpleNamespace(users=[]))
    monkeypatch.setattr("app.services.readiness.auth.list_users", list_users)
    checks = check_connections(
        settings(firebase_enabled=True, firebase_storage_bucket="bucket"),
        online=True,
        runtime_factory=lambda _: runtime,
    )
    assert next(item for item in checks if item.name == "Firestore").status == "ok"
    assert next(item for item in checks if item.name == "Firebase Authentication").status == "ok"
    assert next(item for item in checks if item.name == "Firebase Storage").status == "failed"
    runtime.close.assert_called_once()
    assert "PRIVATE TOKEN" not in repr(checks)


def test_config_only_does_not_initialize_sdk_or_send_requests():
    runtime = Mock(side_effect=AssertionError("Must not initialize"))
    transport = httpx.MockTransport(lambda _: pytest.fail("Must not send network requests"))
    checks = check_connections(
        settings(
            firebase_enabled=True,
            firebase_storage_bucket="bucket",
            gemini_api_key="test-key",
            gemini_model="test-model",
        ),
        runtime_factory=runtime,
        transport=transport,
    )
    assert all(item.status == "ok" for item in checks)
    runtime.assert_not_called()


def test_cli_invalid_settings_does_not_echo_values(monkeypatch, capsys):
    from app.cli.check import main

    monkeypatch.setattr("sys.argv", ["check"])
    monkeypatch.setenv("GEMINI_MODEL", "PRIVATE VALUE THAT FAILS MODEL VALIDATION")
    assert main() == 1
    assert "PRIVATE VALUE" not in capsys.readouterr().out


def test_cli_json_exit_status_for_unconfigured_services(monkeypatch, capsys):
    from app.cli.check import main

    monkeypatch.setattr("sys.argv", ["check", "--json", "--require-ai"])
    monkeypatch.setattr("app.cli.check.Settings", lambda: settings())
    assert main() == 1
    results = json.loads(capsys.readouterr().out)
    assert {item["name"] for item in results if item["status"] == "failed"} == {
        "Firebase config",
        "Storage config",
        "Gemini config",
    }
