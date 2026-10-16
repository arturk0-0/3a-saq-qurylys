"""Test the integration runner guard without starting an emulator or making RPCs."""

import pytest

from qa.firestore.safety import validate_target


@pytest.mark.parametrize(
    "host",
    [
        "",
        "localhost:8080",
        "0.0.0.0:8080",
        "example.test:8080",
        "https://127.0.0.1:8080",
        "127.0.0.1:0",
        "127.0.0.1:65536",
    ],
)
def test_emulator_guard_refuses_non_loopback_or_invalid_target(host):
    with pytest.raises(ValueError):
        validate_target(host, "demo-saq-it-test", opt_in="1")


@pytest.mark.parametrize("project", ["saq-qurylys", "demo-another-project", "", "../saq-qurylys"])
def test_emulator_guard_refuses_actual_or_unrelated_projects(project):
    with pytest.raises(ValueError):
        validate_target("127.0.0.1:8787", project, opt_in="1")


def test_emulator_guard_requires_opt_in():
    with pytest.raises(ValueError):
        validate_target("127.0.0.1:8787", "demo-saq-it-test", opt_in="")
    validate_target("127.0.0.1:8787", "demo-saq-it-test", opt_in="1")


def test_runner_child_environment_excludes_credentials_and_preserves_tls(monkeypatch, tmp_path):
    from qa.firestore.run import child_environment

    private = {
        "GOOGLE_APPLICATION_CREDENTIALS": "/private/test-only.json",
        "GOOGLE_CLOUD_PROJECT": "saq-qurylys",
        "FIREBASE_TOKEN": "private-test-token",
        "GEMINI_API_KEY": "private-test-key",
        "FIREBASE_ENABLED": "true",
        "VITE_API_BASE_URL": "https://production.invalid",
        "CLOUDSDK_AUTH_ACCESS_TOKEN": "private-test-token",
        "FIRESTORE_EMULATOR_HOST": "remote.invalid:8080",
    }
    for key, value in private.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SSL_CERT_FILE", "/test-only/ca.pem")
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", "/test-only/ca.pem")
    env = child_environment(tmp_path)
    assert private.keys().isdisjoint(env)
    assert env["SSL_CERT_FILE"] == env["NODE_EXTRA_CA_CERTS"] == "/test-only/ca.pem"
    assert env["SAQ_FIRESTORE_INTEGRATION"] == "1"
    assert env["XDG_CONFIG_HOME"] == str(tmp_path / "cli-config")
    assert env["NO_PROXY"].startswith("127.0.0.1,localhost,")
