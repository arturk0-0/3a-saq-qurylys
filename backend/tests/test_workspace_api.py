from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import current_user
from app.api.workspace import workspace_service
from app.core.config import Settings
from app.main import create_app
from app.models.auth import Principal
from app.services.seed_data import build_demo_seed
from app.services.workspace import WorkspaceService
from tests.fakes import MemoryStore


@pytest.fixture
def workspace():
    store = MemoryStore(build_demo_seed())
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[current_user] = lambda: Principal(uid="reviewer-real", role="analyst")
    app.dependency_overrides[workspace_service] = lambda: WorkspaceService(store)
    with TestClient(app) as client:
        yield client, store


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/complexes"),
        ("GET", "/complexes/demo-complex-01"),
        ("GET", "/complexes/demo-complex-01/risk"),
        ("POST", "/complexes"),
        ("GET", "/developers"),
        ("GET", "/advertisements"),
        ("POST", "/advertisements"),
        ("GET", "/advertisements/demo-ad-01"),
        ("POST", "/evidence"),
        ("GET", "/evidence/demo-evidence-ad-01"),
        ("POST", "/evidence/demo-evidence-ad-01/decision"),
        ("POST", "/complexes/demo-complex-01/factors/decision"),
        ("GET", "/complexes/demo-complex-01/history"),
        ("PATCH", "/complexes/demo-complex-01/legal-basis"),
    ],
)
def test_every_workspace_route_requires_authentication(method, path):
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.request(method, "/api/v1" + path)
    assert response.status_code == 401


def test_catalog_search_filter_sort_and_pagination(workspace):
    client, _ = workspace
    response = client.get("/api/v1/complexes", params={"limit": 2}).json()
    assert response["total"] == 8 and response["nextCursor"] == "2"
    assert [row["scenario"] for row in response["items"]] == ["B", "A"]
    assert response["catalogLimited"] is False
    second = client.get("/api/v1/complexes", params={"limit": 2, "cursor": "2"}).json()
    assert {row["id"] for row in response["items"]}.isdisjoint(row["id"] for row in second["items"])
    yellow = client.get("/api/v1/complexes", params={"zone": "YELLOW"}).json()
    assert yellow["total"] == 1 and yellow["items"][0]["scenario"] == "A"
    search = client.get("/api/v1/complexes", params={"q": "кедровый", "city": "Риддер"}).json()
    assert search["total"] == 1 and search["items"][0]["scenario"] == "B"
    assert client.get("/api/v1/complexes", params={"limit": 501}).status_code == 422


def test_complex_detail_combines_developer_and_backend_score(workspace):
    client, _ = workspace
    result = client.get("/api/v1/complexes/demo-complex-03").json()
    assert result["developer"]["id"] == result["developerId"]
    assert result["risk"]["score"] == 10
    assert result["legalBasis"]["type"] == "guarantee"


def test_create_ad_preserves_text_and_url_and_records_actor(workspace):
    client, store = workspace
    original = "  Новая реклама\nДепозит 350 000 ₸ — проверка человеком!  "
    response = client.post(
        "/api/v1/advertisements",
        json={
            "complexId": "demo-complex-01",
            "platform": "Manual",
            "account": "test-account",
            "sourceUrl": "https://example.test/post?id=123&source=demo",
            "text": original,
            "publishedAt": "2026-10-14T12:00:00+05:00",
        },
    )
    assert response.status_code == 201
    ad = response.json()
    assert ad["text"] == original
    assert ad["sourceUrl"] == "https://example.test/post?id=123&source=demo"
    assert ad["createdBy"] == "reviewer-real" and ad["demo"] is True
    assert store.get("advertisements", ad["id"])["text"] == original
    assert next(iter(store.documents["auditLogs"].values()))["actorUid"] == "reviewer-real"


def test_client_cannot_inject_reviewer_or_confirmed_state(workspace):
    client, _ = workspace
    response = client.post(
        "/api/v1/advertisements",
        json={
            "complexId": "demo-complex-01",
            "platform": "Manual",
            "account": "test",
            "sourceUrl": "https://example.test/post",
            "text": "demo",
            "publishedAt": "2026-10-14T00:00:00Z",
            "createdBy": "admin-forged",
        },
    )
    assert response.status_code == 422


def test_factor_decision_is_atomic_audited_and_versioned(workspace):
    client, store = workspace
    payload = {
        "code": "R1",
        "decision": "rejected",
        "evidenceIds": [],
        "notes": "Документ требует уточнения",
        "expectedVersion": 1,
    }
    response = client.post("/api/v1/complexes/demo-complex-02/factors/decision", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert (result["risk"]["score"], result["risk"]["zone"], result["version"]) == (35, "YELLOW", 2)
    factor = next(row for row in result["factors"] if row["code"] == "R1")
    assert factor["reviewer"] == "reviewer-real"
    assert factor["reviewedAt"]
    before = deepcopy(store.documents)
    stale = client.post("/api/v1/complexes/demo-complex-02/factors/decision", json=payload)
    assert stale.status_code == 409
    assert store.documents == before
    payload.update(
        {"decision": "confirmed", "evidenceIds": ["demo-evidence-legal-02"], "expectedVersion": 2}
    )
    result = client.post("/api/v1/complexes/demo-complex-02/factors/decision", json=payload).json()
    assert (result["risk"]["score"], result["risk"]["zone"]) == (70, "RED")


def test_evidence_cannot_be_changed_under_a_confirmed_factor(workspace):
    client, _ = workspace
    response = client.post(
        "/api/v1/evidence/demo-evidence-ad-01/decision",
        json={
            "decision": "rejected",
            "notes": "Проверить повторно",
            "expectedVersion": 1,
        },
    )
    assert response.status_code == 409


def test_unverified_or_wrong_complex_evidence_cannot_affect_score(workspace):
    client, store = workspace
    before = deepcopy(store.documents)
    payload = {
        "code": "R1",
        "decision": "confirmed",
        "evidenceIds": ["demo-evidence-legal-02"],
        "notes": "Попытка другой ссылки",
        "expectedVersion": 1,
    }
    response = client.post("/api/v1/complexes/demo-complex-01/factors/decision", json=payload)
    assert response.status_code == 422
    assert store.documents == before


def test_create_and_review_evidence_does_not_automatically_change_score(workspace):
    client, _ = workspace
    response = client.post(
        "/api/v1/evidence",
        json={
            "complexId": "demo-complex-04",
            "type": "work_status",
            "sourceReference": "Акт учебного осмотра №4",
            "excerpt": "DEMO: работы остановлены",
            "capturedAt": "2026-10-14T00:00:00Z",
        },
    )
    assert response.status_code == 201
    item = response.json()
    assert item["status"] == "unknown"
    reviewed = client.post(
        f"/api/v1/evidence/{item['id']}/decision",
        json={
            "decision": "confirmed",
            "notes": "Источник проверен",
            "workStoppageVerified": True,
            "expectedVersion": 1,
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["reviewer"] == "reviewer-real"
    assert client.get("/api/v1/complexes/demo-complex-04/risk").json()["score"] == 10
    result = client.post(
        "/api/v1/complexes/demo-complex-04/factors/decision",
        json={
            "code": "R6",
            "decision": "confirmed",
            "evidenceIds": [item["id"]],
            "notes": "Остановка подтверждена актом",
            "expectedVersion": 1,
        },
    )
    assert result.status_code == 200
    assert result.json()["risk"]["score"] == 15


def test_excerpt_must_match_original_ad(workspace):
    client, _ = workspace
    response = client.post(
        "/api/v1/evidence",
        json={
            "complexId": "demo-complex-01",
            "advertisementId": "demo-ad-01",
            "type": "advertisement",
            "sourceUrl": "https://demo.invalid/advertisements/1",
            "excerpt": "Это не цитата из рекламы",
            "capturedAt": "2026-10-14T00:00:00Z",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "EXCERPT_MISMATCH"


def test_demo_only_scope_hides_non_demo_records(workspace):
    client, store = workspace
    store.documents["complexes"]["demo-complex-01"]["demo"] = False
    assert client.get("/api/v1/complexes/demo-complex-01").status_code == 404
    assert client.get("/api/v1/complexes").json()["total"] == 7


def test_legal_basis_uses_server_reviewer_and_does_not_silently_remove_r1(workspace):
    client, _ = workspace
    payload = {
        "basis": {
            "type": "guarantee",
            "status": "confirmed",
            "reference": "DEMO-NEW",
            "source": "Синтетическая гарантия",
        },
        "expectedVersion": 1,
    }
    response = client.patch("/api/v1/complexes/demo-complex-02/legal-basis", json=payload)
    assert response.status_code == 409
    response = client.patch("/api/v1/complexes/demo-complex-01/legal-basis", json=payload)
    assert response.status_code == 200
    assert response.json()["legalBasis"]["reviewer"] == "reviewer-real"
    assert response.json()["risk"]["score"] == 35


def test_advertisement_pagination_has_no_duplicates(workspace):
    client, _ = workspace
    seen = []
    cursor = None
    while True:
        params = {"limit": 5}
        if cursor:
            params["cursor"] = cursor
        page = client.get("/api/v1/advertisements", params=params).json()
        seen.extend(row["id"] for row in page["items"])
        cursor = page["nextCursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 12
