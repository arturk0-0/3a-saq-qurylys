"""Provider failures use MockTransport only; no credentials or paid calls required."""

import json

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.services.gemini import GeminiClient

SECRET = "unit-test-secret-not-for-logging"
SOURCE = "Private fictional advertisement, never log the source"


def client(handler):
    return GeminiClient(
        Settings(_env_file=None, gemini_api_key=SECRET, gemini_model="selected-model"),
        httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(
    "status,reason,code,api_status",
    [
        (400, "API_KEY_INVALID", "AI_CREDENTIALS", 503),
        (403, "API_KEY_INVALID", "AI_CREDENTIALS", 503),
        (401, None, "AI_CREDENTIALS", 503),
        (403, None, "AI_ACCESS_DENIED", 503),
        (404, None, "AI_MODEL_UNAVAILABLE", 503),
        (429, None, "AI_PROVIDER_QUOTA", 429),
        (400, None, "AI_REQUEST_REJECTED", 502),
        (500, None, "AI_TEMPORARY", 503),
        (502, None, "AI_TEMPORARY", 503),
        (503, None, "AI_TEMPORARY", 503),
        (504, None, "AI_TEMPORARY", 503),
    ],
)
def test_provider_error_is_classified_and_body_never_echoed(
    status, reason, code, api_status, caplog, monkeypatch
):
    monkeypatch.setattr("app.services.gemini.time.sleep", lambda _: None)
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.path.endswith("/selected-model:generateContent")
        assert SECRET not in str(request.url)
        return httpx.Response(
            status,
            json={"error": {"message": f"{SECRET} {SOURCE}", "details": [{"reason": reason}]}},
        )

    with pytest.raises(AppError) as error:
        client(handler).extract(SOURCE)
    assert (error.value.code, error.value.status_code) == (code, api_status)
    assert len(calls) == (2 if status in {502, 503, 504} else 1)
    assert code in caplog.text
    assert SECRET not in caplog.text + str(error.value) + error.value.message
    assert SOURCE not in caplog.text + str(error.value) + error.value.message


@pytest.mark.parametrize(
    "error_type,code",
    [
        (httpx.ReadTimeout, "AI_TIMEOUT"),
        (httpx.ConnectTimeout, "AI_TIMEOUT"),
        (httpx.ConnectError, "AI_NETWORK"),
        (httpx.RemoteProtocolError, "AI_NETWORK"),
    ],
)
def test_network_failures_are_safe_and_never_retried(error_type, code, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        raise error_type(f"{SECRET} {SOURCE}", request=request)

    with pytest.raises(AppError) as error:
        client(handler).extract(SOURCE)
    assert error.value.code == code and error.value.status_code == 503
    assert len(calls) == 1
    assert SECRET not in caplog.text + error.value.message
    assert SOURCE not in caplog.text + error.value.message


def test_one_explicit_transient_retry_can_succeed_without_changing_model(monkeypatch):
    pauses = []
    monkeypatch.setattr("app.services.gemini.time.sleep", pauses.append)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "hypotheses": [],
                                            "mentionedComplexes": [],
                                            "paymentTerms": [],
                                            "uncertainty": "Нужна проверка",
                                        }
                                    )
                                }
                            ]
                        },
                    }
                ]
            },
        )

    assert client(handler).extract(SOURCE).hypotheses == []
    assert len(calls) == 2 and pauses == [0.5]
    assert calls[0].url == calls[1].url
    assert calls[0].content == calls[1].content


@pytest.mark.parametrize(
    "body", [b"not JSON", b"[]", b'{"error":null}', b'{"error":{"details":42}}']
)
def test_malformed_error_body_does_not_crash_or_escape(body):
    with pytest.raises(AppError) as error:
        client(lambda _: httpx.Response(400, content=body)).extract(SOURCE)
    assert error.value.code == "AI_REQUEST_REJECTED"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        42,
        {"candidates": [None]},
        {"candidates": [{"finishReason": "STOP", "content": {"parts": [None]}}]},
    ],
)
def test_malformed_success_envelope_is_not_an_internal_error(payload):
    with pytest.raises(AppError) as error:
        client(lambda _: httpx.Response(200, content=json.dumps(payload))).extract(SOURCE)
    assert error.value.code == "AI_INVALID_RESPONSE" and error.value.status_code == 502


def test_unconfigured_client_does_not_start_a_request():
    missing = GeminiClient(
        Settings(_env_file=None, gemini_api_key="", gemini_model="selected-model"),
        httpx.MockTransport(lambda _: pytest.fail("Unconfigured client sent a request")),
    )
    with pytest.raises(AppError) as error:
        missing.extract(SOURCE)
    assert error.value.code == "AI_NOT_CONFIGURED"
