"""Safe response-validation diagnostics, exclusively synthetic MockTransport inputs."""

import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import AppError
from app.core.request_context import request_id_context
from app.main import create_app
from app.services.gemini import GeminiClient

SECRET = "test-key-must-never-appear"
SOURCE = "DEMO private source must never appear"


def extraction():
    return {
        "hypotheses": [],
        "mentionedComplexes": [],
        "paymentTerms": [],
        "uncertainty": "Проверка человеком",
    }


def envelope(text=None, *, finish="STOP", parts=None):
    return {
        "candidates": [
            {
                "finishReason": finish,
                "content": {
                    "parts": parts
                    if parts is not None
                    else [{"text": text if text is not None else json.dumps(extraction())}]
                },
            }
        ]
    }


def client(payload, *, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request)
        return httpx.Response(
            200, content=payload if isinstance(payload, bytes) else json.dumps(payload)
        )

    return GeminiClient(
        Settings(_env_file=None, gemini_api_key=SECRET, gemini_model="unit-model"),
        httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(
    "payload,reason,finish",
    [
        (b"not JSON", "envelope_json", "missing"),
        ([], "envelope_shape", "missing"),
        ({"candidates": {}}, "envelope_shape", "missing"),
        (
            {"promptFeedback": {"blockReason": SOURCE}, "candidates": []},
            "prompt_blocked",
            "missing",
        ),
        ({"candidates": []}, "no_candidates", "missing"),
        ({"candidates": [None]}, "candidate_shape", "missing"),
        (envelope(finish="MAX_TOKENS"), "incomplete_generation", "MAX_TOKENS"),
        (envelope(finish="SAFETY"), "incomplete_generation", "SAFETY"),
        (envelope(finish=SOURCE), "incomplete_generation", "unknown"),
        (envelope(finish={"untrusted": SOURCE}), "incomplete_generation", "unknown"),
        ({"candidates": [{"finishReason": "STOP"}]}, "parts_shape", "STOP"),
        (envelope(parts=[None]), "parts_shape", "STOP"),
        (envelope(parts=[{"text": 42}]), "parts_shape", "STOP"),
        (envelope(parts=[{"thought": SOURCE, "text": "x"}]), "parts_shape", "STOP"),
        (envelope(parts=[{"thought": True, "text": SOURCE}]), "no_text", "STOP"),
        (envelope(" "), "no_text", "STOP"),
        (envelope("x" * 40001), "output_too_large", "STOP"),
        (envelope("```json\n" + json.dumps(extraction()) + "\n```"), "extraction_json", "STOP"),
        (envelope('{"unexpected": '), "extraction_json", "STOP"),
        (envelope("[" * 1200 + "0" + "]" * 1200), "extraction_json", "STOP"),
        (envelope(json.dumps({**extraction(), SOURCE: SECRET})), "extraction_schema", "STOP"),
        (
            envelope(json.dumps({**extraction(), "uncertainty": SECRET * 300})),
            "extraction_schema",
            "STOP",
        ),
    ],
)
def test_validation_reason_is_bounded_safe_correlated_and_not_retried(
    payload, reason, finish, caplog
):
    calls = []
    token = request_id_context.set("6e2d8399-074c-4993-a216-aee8dbb39de4")
    try:
        with pytest.raises(AppError) as error:
            client(payload, calls=calls).extract(SOURCE)
    finally:
        request_id_context.reset(token)
    assert error.value.code == "AI_INVALID_RESPONSE" and error.value.status_code == 502
    assert len(calls) == 1
    records = [r for r in caplog.records if r.name == "app.services.gemini"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert f"reason={reason}" in message and f"finish_reason={finish}" in message
    assert "request_id=6e2d8399-074c-4993-a216-aee8dbb39de4" in message
    assert "stage=response_validation" in message and "input=text" in message
    assert not records[0].exc_info
    assert SOURCE not in caplog.text + error.value.message
    assert SECRET not in caplog.text + error.value.message
    assert "reason=" not in error.value.message  # API contract remains the same.
    assert request_id_context.get() == "outside-request"


def test_text_quote_must_still_be_exact_but_image_ocr_remains_a_human_hypothesis(caplog):
    value = {
        **extraction(),
        "hypotheses": [
            {
                "code": "R2",
                "quote": "not in the source",
                "explanation": "Проверить оригинал",
                "confidence": 0.5,
            }
        ],
    }
    payload = envelope(json.dumps(value))
    with pytest.raises(AppError):
        client(payload).extract(SOURCE)
    assert "reason=unanchored_quote" in caplog.text
    caplog.clear()
    assert (
        client(payload).extract(SOURCE, (b"synthetic-image", "image/png")).hypotheses[0].quote
        == "not in the source"
    )
    assert not caplog.text


def test_valid_split_json_ignores_private_thought_parts_and_keeps_request_configuration(caplog):
    text = json.dumps(extraction())
    calls = []
    payload = envelope(
        parts=[{"thought": True, "text": SECRET + SOURCE}, {"text": text[:15]}, {"text": text[15:]}]
    )
    payload["promptFeedback"] = {"blockReason": "BLOCK_REASON_UNSPECIFIED"}
    assert client(payload, calls=calls).extract(SOURCE).hypotheses == []
    config = json.loads(calls[0].content)["generationConfig"]
    assert config["maxOutputTokens"] == 4096 and config["temperature"] == 0
    assert config["responseMimeType"] == "application/json"
    assert calls[0].url.path.endswith("/unit-model:generateContent")
    assert SOURCE not in caplog.text and SECRET not in caplog.text


def test_parallel_sync_routes_log_only_their_server_generated_request_ids(caplog):
    app = create_app(Settings(_env_file=None, firebase_enabled=False))
    provider = client(envelope("invalid JSON " + SOURCE))

    @app.get("/test-gemini-diagnostic")
    def fail():
        return provider.extract(SOURCE)

    with TestClient(app) as http:
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(
                pool.map(
                    lambda _: http.get("/test-gemini-diagnostic", headers={"X-Request-ID": SECRET}),
                    range(4),
                )
            )
    ids = {response.json()["requestId"] for response in responses}
    assert len(ids) == 4
    for response in responses:
        assert response.status_code == 502
        assert response.json()["requestId"] == response.headers["x-request-id"]
    records = [r.getMessage() for r in caplog.records if r.name == "app.services.gemini"]
    assert len(records) == 4
    assert {message.split("request_id=", 1)[1].split()[0] for message in records} == ids
    assert SOURCE not in caplog.text and SECRET not in caplog.text
    assert request_id_context.get() == "outside-request"


def test_image_failures_log_only_the_mode_not_the_private_bytes(caplog):
    image = (SOURCE + SECRET).encode()
    with pytest.raises(AppError):
        client(envelope(finish="MAX_TOKENS")).extract(SOURCE, (image, "image/png"))
    assert "input=image" in caplog.text and "finish_reason=MAX_TOKENS" in caplog.text
    assert SOURCE not in caplog.text and SECRET not in caplog.text
