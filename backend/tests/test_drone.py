"""All photos, identities, observations and transports here are explicit test adapters."""

import hashlib
import json
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import current_user
from app.api.drone import drone_service
from app.api.workspace import workspace_service
from app.core.errors import AppError, Conflict
from app.main import create_app
from app.models.common import utc_now
from app.models.drone import (
    DEFAULT_CHECKLIST,
    AnalyzeInspection,
    CreateInspection,
    ReviewInspection,
)
from app.services.drone import DroneService
from app.services.drone_gemini import DroneGeminiClient
from app.services.seed_data import build_demo_seed
from app.services.workspace import WorkspaceService
from tests.fakes import MemoryStore
from tests.test_analysis import USER, FakeFiles, png, settings


def model_result(ids=None):
    return dict(
        observations=[
            dict(
                criterionId=id_,
                visibility="uncertain",
                explanation="Тестовый кадр: требуется осмотр.",
            )
            for id_ in (ids or [c.id for c in DEFAULT_CHECKLIST])
        ],
        summary="Тестовые наблюдения, не оценка соблюдения норм.",
        limitations="Один ракурс не показывает всю площадку.",
    )


def response(result=None, finish="STOP"):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "finishReason": finish,
                    "content": {"parts": [{"text": json.dumps(result or model_result())}]},
                }
            ]
        },
    )


@pytest.fixture
def service():
    config = settings()
    service = DroneService(
        WorkspaceService(MemoryStore(build_demo_seed())),
        FakeFiles(),
        DroneGeminiClient(config, httpx.MockTransport(lambda r: response())),
        config,
    )
    return service


def create(service, **kwargs):
    return service.create(
        CreateInspection(
            request_id=uuid4(), title="Учебный облёт", checklist=DEFAULT_CHECKLIST, **kwargs
        ),
        USER,
    )


def uploaded(service, **kwargs):
    item = create(service, **kwargs)
    return service.upload(item["id"], item["version"], png(), "image/png", USER)


def analyze(service, item):
    request = AnalyzeInspection(request_id=uuid4(), expected_version=item["version"])
    return service.analyze(item["id"], request, USER), request


def test_independent_lifecycle_preserves_original_risk_and_audit(service):
    before = deepcopy(
        {key: service.store.documents[key] for key in ["complexes", "evidence", "advertisements"]}
    )
    item = uploaded(service, complex_id="demo-complex-01")
    assert item["photo"]["sha256"] == hashlib.sha256(png()).hexdigest()
    assert "storagePath" not in item["photo"]
    assert service.download(item["id"]) == (png(), "image/png")
    complete, request = analyze(service, item)
    assert complete["latestRun"]["status"] == "succeeded"
    assert len(complete["latestRun"]["result"]["observations"]) == 3
    again = service.analyze(item["id"], request, USER)
    assert again["version"] == complete["version"]
    assert all(c["count"] == 1 for c in service.store.documents["usageLimits"].values())
    reviewed = service.review(
        item["id"],
        ReviewInspection(
            expected_version=complete["version"],
            run_id=str(request.request_id),
            decision="needs_followup",
            notes="Нужен второй ракурс.",
        ),
        USER,
    )
    assert reviewed["reviews"][0]["reviewer"] == USER.uid
    assert reviewed["status"] == "reviewed"
    assert before == {key: service.store.documents[key] for key in before}
    assert len(service.store.documents["auditLogs"]) == 5


def test_stale_review_and_old_run_cannot_confirm_new_analysis(service):
    item = uploaded(service)
    first, old_request = analyze(service, item)
    second, _ = analyze(service, first)
    with pytest.raises(Conflict):
        service.review(
            item["id"],
            ReviewInspection(
                expected_version=second["version"],
                run_id=str(old_request.request_id),
                decision="accepted",
                notes="Проверено",
            ),
            USER,
        )
    with pytest.raises(Conflict):
        service.review(
            item["id"],
            ReviewInspection(
                expected_version=first["version"],
                run_id=second["latestRunId"],
                decision="accepted",
                notes="Проверено",
            ),
            USER,
        )
    assert not service.get(item["id"])["reviews"]


def test_photo_errors_immutable_and_integrity_failure_cannot_reach_ai(service):
    item = create(service)
    with pytest.raises(AppError):
        service.upload(item["id"], 1, b"<svg/>", "image/png", USER)
    assert not service.storage.objects
    item = service.upload(item["id"], 1, png(), "image/png", USER)
    with pytest.raises(Conflict):
        service.upload(item["id"], item["version"], png(), "image/png", USER)
    path = next(iter(service.storage.objects))
    service.storage.objects[path] = b"changed"
    with pytest.raises(AppError) as error:
        analyze(service, item)
    assert error.value.code == "FILE_INTEGRITY"
    failed = service.get(item["id"])
    assert failed["latestRun"]["errorCode"] == "FILE_INTEGRITY"
    assert failed["photo"]["sha256"] == item["photo"]["sha256"]


def test_create_idempotence_scope_and_stable_pagination(service):
    request = CreateInspection(request_id=uuid4(), title="Один снимок", checklist=DEFAULT_CHECKLIST)
    first = service.create(request, USER)
    assert service.create(request, USER)["id"] == first["id"]
    with pytest.raises(Conflict):
        service.create(request.model_copy(update={"title": "Другой снимок"}), USER)
    other = create(service)
    page = service.list(limit=1)
    assert page["nextCursor"] and len(page["items"]) == 1
    assert service.list(page["nextCursor"], 1)["items"][0]["id"] != page["items"][0]["id"]
    live = DroneService(
        WorkspaceService(service.store, demo_only=False),
        service.storage,
        service.client,
        service.settings,
    )
    assert live.list()["items"] == []
    with pytest.raises(AppError) as error:
        live.get(other["id"])
    assert error.value.status_code == 404


def test_daily_shared_quota_and_invalid_model_never_save_observations(service):
    service.settings.ai_daily_user_limit = 1
    first = uploaded(service)
    service.client.transport = httpx.MockTransport(lambda r: response(model_result(["wrong"])))
    with pytest.raises(AppError) as error:
        analyze(service, first)
    assert error.value.code == "DRONE_INVALID_RESPONSE"
    assert service.get(first["id"])["latestRun"]["result"] is None
    second = uploaded(service)
    with pytest.raises(AppError) as error:
        analyze(service, second)
    assert error.value.code == "AI_DAILY_LIMIT"
    assert service.get(second["id"])["status"] == "ready"


@pytest.mark.parametrize(
    "result,finish",
    [
        (model_result(["fence", "fence", "waste"]), "STOP"),
        ({**model_result(), "compliant": True}, "STOP"),
        (model_result(), "MAX_TOKENS"),
    ],
)
def test_schema_and_incomplete_generation_rejected_without_provider_data_in_logs(
    result, finish, caplog
):
    client = DroneGeminiClient(settings(), httpx.MockTransport(lambda r: response(result, finish)))
    with pytest.raises(AppError) as error:
        client.inspect((png(), "image/png"), DEFAULT_CHECKLIST)
    assert error.value.code == "DRONE_INVALID_RESPONSE"
    assert "Тестовые наблюдения" not in caplog.text


def test_unrelated_photo_request_keeps_original_bytes_and_guarded_prompt(service):
    def inspect(request):
        payload = json.loads(request.content)
        assert (
            "not_visible means it is not seen" in payload["systemInstruction"]["parts"][0]["text"]
        )
        image = payload["contents"][0]["parts"][1]["inlineData"]
        import base64

        assert base64.b64decode(image["data"]) == png()
        assert request.url.host == "generativelanguage.googleapis.com"
        return response()

    service.client.transport = httpx.MockTransport(inspect)
    result, _ = analyze(service, uploaded(service))
    assert all(
        o["visibility"] == "uncertain" for o in result["latestRun"]["result"]["observations"]
    )


def test_stale_run_manual_recovery_does_not_replay_old_request(service):
    item = uploaded(service)
    original = service.client.inspect

    def crash(*args):
        raise KeyboardInterrupt()

    service.client.inspect = crash
    request = AnalyzeInspection(request_id=uuid4(), expected_version=item["version"])
    with pytest.raises(KeyboardInterrupt):
        service.analyze(item["id"], request, USER)
    running = service.get(item["id"])
    assert not running["canAnalyze"]
    with pytest.raises(AppError) as error:
        analyze(service, running)
    assert error.value.code == "DRONE_BUSY"
    service.store.documents["droneRuns"][str(request.request_id)]["createdAt"] = (
        utc_now() - timedelta(minutes=6)
    ).isoformat()
    assert service.get(item["id"])["canAnalyze"]
    service.client.inspect = original
    completed, _ = analyze(service, service.get(item["id"]))
    assert completed["latestRun"]["status"] == "succeeded"
    assert (
        service.store.get("droneRuns", str(request.request_id))["errorCode"] == "DRONE_INTERRUPTED"
    )


def test_create_duplicate_criteria_and_future_capture_rejected():
    for extra in [
        dict(checklist=[DEFAULT_CHECKLIST[0]] * 2),
        dict(captured_at=utc_now() + timedelta(days=1)),
    ]:
        payload = dict(request_id=uuid4(), title="Снимок", checklist=DEFAULT_CHECKLIST)
        payload.update(extra)
        with pytest.raises(ValidationError):
            CreateInspection(**payload)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", ""),
        ("POST", ""),
        ("GET", "/checklist"),
        ("GET", "/id"),
        ("POST", "/id/photo?expected_version=1"),
        ("GET", "/id/photo"),
        ("POST", "/id/analyze"),
        ("POST", "/id/review"),
        ("GET", "/id/runs"),
    ],
)
def test_routes_require_auth_before_storage_or_model(method, path):
    with TestClient(create_app(settings())) as client:
        assert client.request(method, "/api/v1/drone-inspections" + path).status_code == 401


def test_api_photo_protection_and_lifecycle(service):
    app = create_app(settings())
    app.dependency_overrides[current_user] = lambda: USER
    app.dependency_overrides[workspace_service] = lambda: service.workspace
    app.dependency_overrides[drone_service] = lambda: service
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/drone-inspections",
            json=dict(
                requestId=str(uuid4()),
                title="Снимок",
                checklist=[c.model_dump(mode="json", by_alias=True) for c in DEFAULT_CHECKLIST],
            ),
        ).json()
        path = "/api/v1/drone-inspections/" + created["id"]
        uploaded = client.post(
            path + "/photo?expected_version=1", content=png(), headers={"Content-Type": "image/png"}
        )
        assert uploaded.status_code == 201
        download = client.get(path + "/photo")
        assert download.content == png() and download.headers["cache-control"] == "no-store"
        assert download.headers["x-content-type-options"] == "nosniff"
        analyzed = client.post(
            path + "/analyze", json=dict(requestId=str(uuid4()), expectedVersion=2)
        )
        assert analyzed.status_code == 200 and analyzed.json()["latestRun"]["status"] == "succeeded"


def test_rejected_upload_cleans_only_own_object_but_uncertain_commit_keeps_original(service):
    item = create(service)
    original_put = service.storage.put

    def racing_put(path, data, media_type):
        original_put(path, data, media_type)
        service.store.documents["droneInspections"][item["id"]]["version"] += 1

    service.storage.put = racing_put
    with pytest.raises(Conflict):
        service.upload(item["id"], 1, png(), "image/png", USER)
    assert not service.storage.objects
    service.storage.put = original_put
    atomic = service.store.atomic

    def commit_then_timeout(operation):
        atomic(operation)
        raise AppError(503, "INTEGRATION_UNAVAILABLE", "Synthetic uncertain commit")

    service.store.atomic = commit_then_timeout
    with pytest.raises(AppError):
        service.upload(item["id"], 2, png(), "image/png", USER)
    assert len(service.storage.objects) == 1
    assert service.download(item["id"])[0] == png()


def test_late_old_model_response_cannot_replace_recovered_result(service):
    item = uploaded(service)
    original_inspect = service.client.inspect
    old_id = None

    def finish_late(image, checklist):
        nonlocal old_id
        old_id = service.get(item["id"])["latestRunId"]
        service.store.documents["droneRuns"][old_id]["createdAt"] = (
            utc_now() - timedelta(minutes=6)
        ).isoformat()
        service.client.inspect = original_inspect
        analyze(service, service.get(item["id"]))
        return original_inspect(image, checklist)

    service.client.inspect = finish_late
    with pytest.raises(Conflict):
        analyze(service, item)
    current = service.get(item["id"])
    assert current["latestRunId"] != old_id and current["latestRun"]["status"] == "succeeded"
    assert service.store.get("droneRuns", old_id)["errorCode"] == "DRONE_INTERRUPTED"
