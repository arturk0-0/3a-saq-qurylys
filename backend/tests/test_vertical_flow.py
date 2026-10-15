"""Full application workflow with explicitly mocked external Firebase/Gemini transports."""

import json
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.api.analysis import analysis_service
from app.api.dependencies import current_user
from app.api.workspace import workspace_service
from app.core.config import Settings
from app.main import create_app
from app.models.auth import Principal
from app.services.analysis import AnalysisService
from app.services.gemini import GeminiClient
from app.services.seed_data import build_demo_seed
from app.services.workspace import WorkspaceService
from tests.fakes import MemoryStore


def test_new_ad_to_reviewed_factor_signal_and_pdf():
    settings = Settings(_env_file=None, gemini_api_key="unit-test", gemini_model="test-model")
    store = MemoryStore(build_demo_seed())
    workspace = WorkspaceService(store)
    quote = "Бронь квартиры: внесите депозит 135 000 тенге."
    extraction = {
        "hypotheses": [
            {"code": "R2", "quote": quote, "explanation": "Прямой платёж", "confidence": None}
        ],
        "mentionedComplexes": [],
        "paymentTerms": ["135 000 тенге"],
        "uncertainty": "Нужна проверка",
    }
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": json.dumps(extraction)}]},
                    }
                ]
            },
        )
    )
    app = create_app(settings)
    app.dependency_overrides[current_user] = lambda: Principal(uid="reviewer", role="analyst")
    app.dependency_overrides[workspace_service] = lambda: workspace
    app.dependency_overrides[analysis_service] = lambda: AnalysisService(
        workspace, GeminiClient(settings, transport), None, settings
    )
    with TestClient(app) as client:
        ad = client.post(
            "/api/v1/advertisements",
            json={
                "complexId": "demo-complex-04",
                "platform": "DEMO",
                "account": "fictional-account",
                "sourceUrl": "https://demo.invalid/new-ad",
                "text": quote,
                "publishedAt": "2026-10-15T09:00:00+05:00",
            },
        ).json()
        run = client.post(
            f"/api/v1/advertisements/{ad['id']}/analyze",
            json={"requestId": str(uuid4()), "expectedVersion": 1},
        )
        assert run.status_code == 200
        hypothesis = client.get(f"/api/v1/advertisements/{ad['id']}/hypotheses").json()["items"][0]
        assert client.get("/api/v1/complexes/demo-complex-04/risk").json()["score"] == 10
        result = client.post(
            f"/api/v1/hypotheses/{hypothesis['id']}/decision",
            json={
                "decision": "accepted",
                "expectedVersion": 1,
                "notes": "Цитата соответствует оригиналу",
            },
        )
        assert result.status_code == 200
        assert client.get("/api/v1/complexes/demo-complex-04/risk").json()["score"] == 10
        reviewed = client.post(
            f"/api/v1/evidence/{hypothesis['evidenceId']}/decision",
            json={
                "decision": "confirmed",
                "expectedVersion": 1,
                "notes": "Платёж проверен в первоисточнике",
                "paymentOfferVerified": True,
            },
        )
        assert reviewed.status_code == 200
        risk = client.post(
            "/api/v1/complexes/demo-complex-04/factors/decision",
            json={
                "code": "R2",
                "decision": "confirmed",
                "expectedVersion": 1,
                "evidenceIds": [hypothesis["evidenceId"]],
                "notes": "Прямой платёж подтверждён",
            },
        )
        assert risk.status_code == 200 and risk.json()["risk"]["score"] == 35
        signal = client.post(
            "/api/v1/signals",
            json={
                "complexId": "demo-complex-04",
                "expectedComplexVersion": 2,
                "title": "DEMO — проверка новой рекламы",
                "reason": "Есть подтверждённый платёж",
            },
        ).json()
        for action, version in [("submit", 1), ("confirm", 2)]:
            response = client.post(
                f"/api/v1/signals/{signal['id']}/decision",
                json={"action": action, "expectedVersion": version, "notes": "Проверено человеком"},
            )
            assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
        assert response.json()["snapshot"]["risk"]["score"] == 35
        assert client.get(f"/api/v1/signals/{signal['id']}/report").content.startswith(b"%PDF")
