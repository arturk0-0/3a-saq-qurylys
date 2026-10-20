import base64
import io
import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageFile

from app.api.analysis import analysis_service, file_service
from app.api.dependencies import current_user
from app.api.workspace import workspace_service
from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.models.analysis import AnalysisRequest, HypothesisDecision
from app.models.auth import Principal
from app.services.analysis import AnalysisService
from app.services.files import FileService, validate_image
from app.services.gemini import GeminiClient
from app.services.seed_data import build_demo_seed
from app.services.workspace import WorkspaceService
from tests.fakes import MemoryStore

USER = Principal(uid="human-analyst", role="analyst")


class FakeFiles:
    def __init__(self):
        self.objects = {}

    def put(self, path, data, media_type):
        self.objects[path] = data

    def get(self, path):
        return self.objects[path]

    def delete(self, path):
        self.objects.pop(path, None)


def settings(**kwargs):
    return Settings(
        _env_file=None, gemini_api_key="test-only-key", gemini_model="test-model", **kwargs
    )


def extraction(quote):
    return {
        "hypotheses": [
            {"code": "R2", "quote": quote, "explanation": "Проверить оплату", "confidence": 0.8}
        ],
        "mentionedComplexes": [],
        "paymentTerms": [],
        "uncertainty": "Требуется проверка человеком",
    }


def mock_response(payload):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}
            ]
        },
    )


@pytest.mark.parametrize(
    "text", ["Внесите депозит 100 000 тенге.", "Брондау үшін 100 000 теңге төлеңіз."]
)
def test_new_input_is_sent_and_exact_quotes_are_validated(text):
    def handler(request):
        assert request.headers["x-goog-api-key"] == "test-only-key"
        body = json.loads(request.content)
        assert json.loads(body["contents"][0]["parts"][0]["text"])["sourceText"] == text
        assert "test-only-key" not in str(request.url)
        return mock_response(extraction(text))

    result = GeminiClient(settings(), httpx.MockTransport(handler)).extract(text)
    assert result.hypotheses[0].quote == text


@pytest.mark.parametrize(
    "bad",
    [
        extraction("invented quote"),
        {**extraction("quote"), "status": "confirmed"},
        {
            **extraction("quote"),
            "hypotheses": [{"code": "R1", "quote": "quote", "explanation": "no record"}],
        },
    ],
)
def test_model_cannot_invent_text_confirm_or_propose_r1(bad):
    client = GeminiClient(settings(), httpx.MockTransport(lambda _: mock_response(bad)))
    with pytest.raises(AppError) as error:
        client.extract("quote")
    assert error.value.code == "AI_INVALID_RESPONSE"


def test_harmless_response_can_be_empty():
    payload = {**extraction(""), "hypotheses": []}
    client = GeminiClient(settings(), httpx.MockTransport(lambda _: mock_response(payload)))
    assert client.extract("Бесплатная консультация, платежей нет.").hypotheses == []


def test_quota_errors_and_incomplete_responses_are_not_success():
    for response, expected in [
        (httpx.Response(429), "AI_PROVIDER_QUOTA"),
        (httpx.Response(200, json={"candidates": []}), "AI_INVALID_RESPONSE"),
    ]:
        with pytest.raises(AppError) as error:
            GeminiClient(settings(), httpx.MockTransport(lambda _, r=response: r)).extract("text")
        assert error.value.code == expected


@pytest.fixture
def services():
    store = MemoryStore(build_demo_seed())
    workspace = WorkspaceService(store)
    files = FileService(workspace, FakeFiles())
    quote = store.get("advertisements", "demo-ad-01")["text"]
    gemini = GeminiClient(
        settings(), httpx.MockTransport(lambda _: mock_response(extraction(quote)))
    )
    return AnalysisService(workspace, gemini, files, settings(ai_daily_user_limit=2)), files, store


def test_analysis_and_review_never_modify_factors_or_verified_facts(services):
    service, _, store = services
    before = deepcopy(store.documents["complexes"])
    payload = AnalysisRequest(request_id=uuid4(), expected_version=1)
    result = service.analyze("demo-ad-01", payload, USER)
    assert result["status"] == "succeeded"
    hypothesis = store.get("aiHypotheses", result["hypothesisIds"][0])
    evidence = store.get("evidence", hypothesis["evidenceId"])
    assert evidence["status"] == "proposed" and evidence["paymentOfferVerified"] is False
    assert evidence["reviewer"] is None
    service.review(
        hypothesis["id"],
        HypothesisDecision(decision="accepted", notes="Цитата верна", expected_version=1),
        USER,
    )
    assert store.get("evidence", evidence["id"])["status"] == "proposed"
    assert store.documents["complexes"] == before
    assert service.analyze("demo-ad-01", payload, USER) == result
    assert len(store.documents["aiHypotheses"]) == 1


def test_limits_and_request_ownership(services):
    service, _, store = services
    payload = AnalysisRequest(request_id=uuid4(), expected_version=1)
    service.analyze("demo-ad-01", payload, USER)
    with pytest.raises(AppError) as error:
        service.analyze("demo-ad-01", payload, Principal(uid="other", role="analyst"))
    assert error.value.status_code == 409
    # An identical input is reused and does not consume another quota unit.
    service.analyze("demo-ad-01", AnalysisRequest(request_id=uuid4(), expected_version=1), USER)
    assert all(c["count"] == 1 for c in store.documents["usageLimits"].values())
    quote = store.get("advertisements", "demo-ad-02")["text"]
    service.client = GeminiClient(
        settings(), httpx.MockTransport(lambda _: mock_response(extraction(quote)))
    )
    service.analyze("demo-ad-02", AnalysisRequest(request_id=uuid4(), expected_version=1), USER)
    with pytest.raises(AppError) as error:
        service.analyze("demo-ad-03", AnalysisRequest(request_id=uuid4(), expected_version=1), USER)
    assert error.value.status_code == 429
    assert all(c["count"] == 2 for c in store.documents["usageLimits"].values())


def png():
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_private_upload_integrity_and_wrong_image_selection(services):
    service, files, store = services
    image = files.upload("demo-ad-01", 1, png(), "image/png", USER)
    assert image.status == "unknown"
    assert files.download(image.id) == (png(), "image/png")
    with pytest.raises(AppError) as error:
        service.analyze(
            "demo-ad-02",
            AnalysisRequest(request_id=uuid4(), expected_version=1, screenshot_id=image.id),
            USER,
        )
    assert error.value.code == "IMAGE_MISMATCH"
    result = service.analyze(
        "demo-ad-01",
        AnalysisRequest(request_id=uuid4(), expected_version=2, screenshot_id=image.id),
        USER,
    )
    item = store.get("aiHypotheses", result["hypothesisIds"][0])
    assert store.get("evidence", item["evidenceId"])["sha256"] == image.sha256
    files.storage.objects[image.storage_path] = b"changed"
    with pytest.raises(AppError) as error:
        files.download(image.id)
    assert error.value.code == "FILE_INTEGRITY"


@pytest.mark.parametrize(
    "data,media",
    [
        (b"<svg></svg>", "image/png"),
        (png(), "image/jpeg"),
        (b"a" * (6 * 1024 * 1024 + 1), "image/png"),
    ],
)
def test_reject_unsafe_or_mislabeled_images(data, media):
    with pytest.raises(AppError):
        validate_image(data, media)


@pytest.mark.parametrize("missing_bytes", [2, 5, 10])
@pytest.mark.parametrize("allow_truncated", [False, True])
def test_truncated_jpeg_is_rejected_before_storage(
    services, monkeypatch, missing_bytes, allow_truncated
):
    # WeasyPrint's first import enables this flag in a running API process.
    monkeypatch.setattr(ImageFile, "LOAD_TRUNCATED_IMAGES", allow_truncated)
    _, files, store = services
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buffer, format="JPEG")
    original = buffer.getvalue()
    before = deepcopy(store.documents)
    with pytest.raises(AppError) as error:
        files.upload("demo-ad-01", 1, original[:-missing_bytes], "image/jpeg", USER)
    assert error.value.code == "INVALID_IMAGE"
    assert not files.storage.objects
    assert store.documents == before
    assert ImageFile.LOAD_TRUNCATED_IMAGES is allow_truncated
    # Successful validation preserves the exact uploaded file, including provenance hash.
    item = files.upload("demo-ad-01", 1, original, "image/jpeg", USER)
    assert files.download(item.id) == (original, "image/jpeg")
    assert ImageFile.LOAD_TRUNCATED_IMAGES is allow_truncated


def test_analysis_routes_and_private_download(services):
    service, files, _ = services
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        assert client.post("/api/v1/advertisements/demo-ad-01/analyze").status_code == 401
        assert client.get("/api/v1/evidence/anything/file").status_code == 401
        app.dependency_overrides[current_user] = lambda: USER
        app.dependency_overrides[workspace_service] = lambda: service.workspace
        app.dependency_overrides[analysis_service] = lambda: service
        app.dependency_overrides[file_service] = lambda: files
        response = client.post(
            "/api/v1/advertisements/demo-ad-01/screenshots?expected_version=1",
            content=png(),
            headers={"content-type": "image/png"},
        )
        assert response.status_code == 201
        download = client.get(f"/api/v1/evidence/{response.json()['id']}/file")
        assert download.content == png() and download.headers["cache-control"] == "no-store"
        result = client.post(
            "/api/v1/advertisements/demo-ad-01/analyze",
            json={"requestId": str(uuid4()), "expectedVersion": 2},
        )
        assert result.status_code == 200
        assert (
            client.get("/api/v1/advertisements/demo-ad-01/hypotheses").json()["items"][0]["status"]
            == "proposed"
        )


@pytest.mark.parametrize(
    "status,code",
    [
        (429, "AI_PROVIDER_QUOTA"),
        (404, "AI_MODEL_UNAVAILABLE"),
        (401, "AI_CREDENTIALS"),
        (403, "AI_ACCESS_DENIED"),
    ],
)
def test_failed_provider_call_is_persisted_without_fake_output(services, status, code):
    service, _, store = services
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "PRIVATE PROVIDER DETAIL"}})

    service.client = GeminiClient(settings(), httpx.MockTransport(handler))
    request = AnalysisRequest(request_id=uuid4(), expected_version=1)
    original = deepcopy(store.documents["complexes"])
    with pytest.raises(AppError) as error:
        service.analyze("demo-ad-01", request, USER)
    assert error.value.code == code
    failed = store.get("analysisRuns", str(request.request_id))
    assert (failed["status"], failed["errorCode"]) == ("failed", code)
    assert "PRIVATE PROVIDER DETAIL" not in json.dumps(failed)
    assert not store.documents.get("aiHypotheses")
    with pytest.raises(AppError) as repeated:
        service.analyze("demo-ad-01", request, USER)
    assert repeated.value.status_code == 409 and len(calls) == 1
    assert all(counter["count"] == 1 for counter in store.documents["usageLimits"].values())
    assert store.documents["complexes"] == original


def test_screenshot_bytes_and_provenance_survive_mocked_analysis(services):
    service, files, store = services
    image = files.upload("demo-ad-01", 1, png(), "image/png", USER)
    quote = "Цитата из тестового ответа OCR; качество OCR здесь не проверяется."

    def handler(request):
        body = json.loads(request.content)
        part = body["contents"][0]["parts"][1]["inlineData"]
        assert part["mimeType"] == "image/png"
        assert base64.b64decode(part["data"]) == png()
        return mock_response(extraction(quote))

    service.client = GeminiClient(settings(), httpx.MockTransport(handler))
    result = service.analyze(
        "demo-ad-01",
        AnalysisRequest(request_id=uuid4(), expected_version=2, screenshot_id=image.id),
        USER,
    )
    hypothesis = store.get("aiHypotheses", result["hypothesisIds"][0])
    evidence = store.get("evidence", hypothesis["evidenceId"])
    assert evidence["excerpt"] == quote and evidence["status"] == "proposed"
    assert evidence["storagePath"] == image.storage_path
    assert evidence["sha256"] == image.sha256
    assert evidence["paymentOfferVerified"] is False and evidence["reviewer"] is None


def test_hidden_image_is_not_read_from_storage(services, monkeypatch):
    _, files, store = services
    image = files.upload("demo-ad-01", 1, png(), "image/png", USER)
    store.documents["evidence"][image.id]["demo"] = False
    monkeypatch.setattr(files.storage, "get", lambda _: pytest.fail("Must not read hidden file"))
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[current_user] = lambda: USER
    app.dependency_overrides[file_service] = lambda: files
    with TestClient(app) as http:
        response = http.get(f"/api/v1/evidence/{image.id}/file")
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
