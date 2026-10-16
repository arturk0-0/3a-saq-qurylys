"""Real SDK + isolated local Firestore, not a live Firebase verification."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.analysis import analysis_service, file_service
from app.api.dependencies import current_user
from app.api.workspace import workspace_service
from app.core.config import Settings
from app.core.errors import AppError, Conflict
from app.main import create_app
from app.models.analysis import AnalysisRequest
from app.models.auth import Principal
from app.repositories.firestore import FirestoreStore
from app.schemas.workspace import FactorDecision
from app.services.analysis import AnalysisService
from app.services.files import FileService
from app.services.gemini import GeminiClient
from tests.test_analysis import FakeFiles, extraction, mock_response, png

USER = Principal(uid="local-emulator-reviewer", role="analyst")


@pytest.mark.parametrize(
    "quote,image",
    [
        ("DEMO: внесите депозит 130 000 тенге.", False),
        ("DEMO: брондау үшін 130 000 теңге төлеңіз.", True),
    ],
)
def test_new_ad_to_human_review_signal_revisions_and_native_pdf(workspace, quote, image):
    config = Settings(
        _env_file=None,
        firebase_enabled=False,
        gemini_api_key="local-placeholder",
        gemini_model="local-test",
    )
    files = FileService(workspace, FakeFiles())
    provider_calls = []

    def handler(request):
        provider_calls.append(request)
        return mock_response(extraction(quote))

    service = AnalysisService(
        workspace, GeminiClient(config, httpx.MockTransport(handler)), files, config
    )
    app = create_app(config)
    app.dependency_overrides[workspace_service] = lambda: workspace
    app.dependency_overrides[file_service] = lambda: files
    app.dependency_overrides[analysis_service] = lambda: service
    with TestClient(app) as client:
        assert client.get("/api/v1/complexes").status_code == 401
        app.dependency_overrides[current_user] = lambda: USER
        ad_response = client.post(
            "/api/v1/advertisements",
            json={
                "complexId": "demo-complex-04",
                "platform": "DEMO",
                "account": "fictional-local",
                "sourceUrl": "https://demo.invalid/emulator-ad",
                "text": quote,
                "publishedAt": "2026-10-16T00:00:00+05:00",
            },
        )
        assert ad_response.status_code == 201, ad_response.text
        ad = ad_response.json()
        payload = {"requestId": str(uuid4()), "expectedVersion": 1}
        if image:
            upload = client.post(
                f"/api/v1/advertisements/{ad['id']}/screenshots?expected_version=1",
                content=png(),
                headers={"Content-Type": "image/png"},
            )
            assert upload.status_code == 201, upload.text
            payload.update(expectedVersion=2, screenshotId=upload.json()["id"])
            downloaded = client.get(f"/api/v1/evidence/{upload.json()['id']}/file")
            assert downloaded.content == png()
        analyzed = client.post(f"/api/v1/advertisements/{ad['id']}/analyze", json=payload)
        assert analyzed.status_code == 200, analyzed.text
        repeated = client.post(f"/api/v1/advertisements/{ad['id']}/analyze", json=payload)
        assert repeated.json() == analyzed.json() and len(provider_calls) == 1
        hypothesis = client.get(f"/api/v1/advertisements/{ad['id']}/hypotheses").json()["items"][0]
        assert client.get("/api/v1/complexes/demo-complex-04/risk").json()["score"] == 10
        accepted = client.post(
            f"/api/v1/hypotheses/{hypothesis['id']}/decision",
            json={
                "decision": "accepted",
                "expectedVersion": 1,
                "notes": "Локальная проверка цитаты",
            },
        )
        assert accepted.status_code == 200, accepted.text
        reviewed = client.post(
            f"/api/v1/evidence/{hypothesis['evidenceId']}/decision",
            json={
                "decision": "confirmed",
                "expectedVersion": 1,
                "notes": "Локальная проверка источника",
                "paymentOfferVerified": True,
            },
        )
        assert reviewed.status_code == 200, reviewed.text
        assert client.get("/api/v1/complexes/demo-complex-04/risk").json()["score"] == 10
        factored = client.post(
            "/api/v1/complexes/demo-complex-04/factors/decision",
            json={
                "code": "R2",
                "decision": "confirmed",
                "expectedVersion": 1,
                "evidenceIds": [hypothesis["evidenceId"]],
                "notes": "DEMO: фактор проверен человеком",
            },
        )
        assert factored.status_code == 200, factored.text
        assert factored.json()["risk"]["score"] == 35
        created = client.post(
            "/api/v1/signals",
            json={
                "complexId": "demo-complex-04",
                "expectedComplexVersion": 2,
                "title": "DEMO — local SDK signal",
                "reason": "Тест настоящего persistence",
            },
        )
        assert created.status_code == 201, created.text
        signal = created.json()
        original = signal.copy()
        for action in ["submit", "return", "submit", "confirm"]:
            decided = client.post(
                f"/api/v1/signals/{signal['id']}/decision",
                json={
                    "expectedVersion": signal["version"],
                    "action": action,
                    "notes": "DEMO: локальная проверка решения",
                },
            )
            assert decided.status_code == 200, decided.text
            signal = decided.json()
        assert signal["status"] == "confirmed" and signal["snapshot"]["risk"]["score"] == 35
        assert client.get(f"/api/v1/signals/{signal['id']}/revisions/1").json() == original
        events, cursor = [], None
        for _ in range(4):
            response = client.get(
                f"/api/v1/signals/{signal['id']}/history",
                params={
                    "limit": 2,
                    **({"cursor": cursor} if cursor else {}),
                },
            )
            assert response.status_code == 200, response.text
            page = response.json()
            events.extend(page["items"])
            cursor = page["nextCursor"]
            if cursor is None:
                break
        assert cursor is None and len({row["id"] for row in events}) == len(events) == 5
        assert all(row["actorUid"] == USER.uid for row in events)
        pdf = client.get(f"/api/v1/signals/{signal['id']}/report")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
        assert pdf.headers["cache-control"] == "no-store"


def test_actual_query_pages_ties_scope_and_demo_filter(workspace):
    store = workspace.store
    for event_id, demo, entity in [
        ("tie-a", True, "signal-a"),
        ("tie-b", True, "signal-a"),
        ("tie-c", True, "signal-a"),
        ("tie-hidden", False, "signal-a"),
        ("tie-other", True, "signal-b"),
    ]:
        store.db.collection("auditLogs").document(event_id).create(
            {
                "id": event_id,
                "demo": demo,
                "entityId": entity,
                "createdAt": "2026-10-16T00:00:00+00:00",
            }
        )
    first = workspace.page("auditLogs", extra_filters=[("entityId", "==", "signal-a")], limit=2)
    assert [row["id"] for row in first["items"]] == ["tie-a", "tie-b"]
    second = workspace.page(
        "auditLogs",
        extra_filters=[("entityId", "==", "signal-a")],
        after_id=first["nextCursor"],
        limit=2,
    )
    assert [row["id"] for row in second["items"]] == ["tie-c"]
    assert second["nextCursor"] is None
    with pytest.raises(Conflict):
        workspace.page(
            "auditLogs", extra_filters=[("entityId", "==", "signal-b")], after_id="tie-a", limit=2
        )


def test_sdk_atomic_failure_does_not_persist_partial_business_or_audit(db):
    store = FirestoreStore(db)

    def interrupted(tx):
        tx.create("complexes", "interrupted", {"id": "interrupted", "demo": True})
        tx.create("auditLogs", "interrupted-audit", {"id": "interrupted-audit", "demo": True})
        raise RuntimeError("Explicit test interruption before commit")

    with pytest.raises(RuntimeError, match="Explicit test interruption"):
        store.atomic(interrupted)
    assert store.get("complexes", "interrupted") is None
    assert store.get("auditLogs", "interrupted-audit") is None


def test_real_transactions_prevent_lost_parallel_factor_review(workspace):
    start = Barrier(2)

    def decide(index):
        start.wait(timeout=10)
        try:
            return workspace.factor_decision(
                "demo-complex-01",
                FactorDecision(
                    code="R2",
                    decision="rejected",
                    expected_version=1,
                    notes=f"DEMO: reviewer {index}",
                ),
                Principal(uid=f"local-reviewer-{index}", role="analyst"),
            )
        except Conflict as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, range(2)))
    assert sum(isinstance(result, Conflict) for result in results) == 1
    complex_ = workspace.complex_detail("demo-complex-01")
    assert complex_["version"] == 2 and complex_["risk"]["score"] == 10
    audit = workspace.page("auditLogs", complex_id="demo-complex-01")["items"]
    assert len(audit) == 1
    factor = next(row for row in complex_["factors"] if row["code"] == "R2")
    assert factor["reviewer"] == audit[0]["actorUid"]


def test_client_rules_deny_direct_read_and_write_but_server_sdk_can_read(workspace):
    db = workspace.store.db
    host = os.environ["FIRESTORE_EMULATOR_HOST"]
    document = f"http://{host}/v1/projects/{db.project}/databases/(default)/documents/complexes/demo-complex-01"
    with httpx.Client(trust_env=False, timeout=10) as client:
        assert client.get(document).status_code == 403
        assert client.patch(document, json={"fields": {}}).status_code == 403
    assert workspace.complex("demo-complex-01").id == "demo-complex-01"


def test_real_transactions_enforce_global_ai_quota(workspace):
    config = Settings(
        _env_file=None,
        gemini_api_key="local-placeholder",
        gemini_model="local-test",
        ai_daily_global_limit=1,
        ai_daily_user_limit=1,
    )
    quote = workspace.require_record("advertisements", "demo-ad-01")["text"]
    calls = []

    def handler(request):
        calls.append(request)
        return mock_response(extraction(quote))

    service = AnalysisService(
        workspace,
        GeminiClient(config, httpx.MockTransport(handler)),
        FileService(workspace, FakeFiles()),
        config,
    )
    start = Barrier(2)

    def analyze(index):
        start.wait(timeout=10)
        try:
            return service.analyze(
                "demo-ad-01",
                AnalysisRequest(request_id=uuid4(), expected_version=1),
                Principal(uid=f"local-quota-user-{index}", role="analyst"),
            )
        except AppError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(analyze, range(2)))
    failures = [result for result in results if isinstance(result, AppError)]
    assert len(failures) == 1
    assert (failures[0].status_code, failures[0].code) == (429, "AI_DAILY_LIMIT")
    assert len(calls) == 1
    assert len(workspace.page("analysisRuns")["items"]) == 1
    assert workspace.complex_detail("demo-complex-01")["risk"]["score"] == 35


@pytest.mark.parametrize(
    "complex_id,score,zone",
    [
        ("demo-complex-01", 35, "YELLOW"),
        ("demo-complex-02", 70, "RED"),
        ("demo-complex-03", 10, "GREEN"),
    ],
)
def test_persisted_mandatory_scenarios_and_signal_snapshots(workspace, complex_id, score, zone):
    from app.models.signals import SignalCreate
    from app.services.signals import SignalService

    detail = workspace.complex_detail(complex_id)
    assert (detail["risk"]["score"], detail["risk"]["zone"]) == (score, zone)
    if complex_id == "demo-complex-03":
        assert detail["legalBasis"]["status"] == "confirmed"
        assert detail["legalBasis"]["type"] == "guarantee"
    signals = SignalService(workspace)
    created = signals.create(
        SignalCreate(
            complex_id=complex_id,
            expected_complex_version=1,
            title="DEMO local mandatory scenario",
            reason="Synthetic persistence check",
        ),
        USER,
    )
    saved = signals.get(created.id)
    assert saved == created
    assert (saved.snapshot.risk.score, saved.snapshot.risk.zone) == (score, zone)
