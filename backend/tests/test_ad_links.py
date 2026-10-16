from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import current_user
from app.api.workspace import workspace_service
from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.models.ad_trace import TraceDecision, TraceSave
from app.models.auth import Principal
from app.services.ad_links import AdLinksService
from app.services.seed_data import build_demo_seed
from app.services.workspace import WorkspaceService
from tests.fakes import MemoryStore

USER = Principal(uid="demo-trace-reviewer", role="analyst")
A, B = "demo-ad-01", "demo-ad-02"


@pytest.fixture
def service():
    store = MemoryStore(build_demo_seed())
    store.documents["advertisements"][A]["text"] = "DEMO +7 (000) 000-00-01"
    store.documents["advertisements"][B]["text"] = "DEMO WhatsApp https://wa.me/70000000001"
    return AdLinksService(WorkspaceService(store))


def payload(service):
    item = next(
        row for row in service.candidates(A)["items"] if row["otherAdvertisement"]["id"] == B
    )
    return TraceSave(
        other_advertisement_id=B,
        expected_snapshot_id=item["id"],
        expected_version=1,
        expected_other_version=1,
    )


def decision(status="confirmed", version=1):
    return TraceDecision(
        decision=status, notes="DEMO: оба оригинала сверены", expected_version=version
    )


def test_preview_is_read_only_with_exact_reasons_and_explicit_bounds(service):
    before = deepcopy(service.store.documents)
    response = service.candidates(A)
    assert service.store.documents == before
    assert response["scannedCount"] == 11
    assert not response["scanLimited"] and not response["resultsLimited"]
    assert len(response["items"]) == 1
    item = response["items"][0]
    assert item["saved"] is None
    assert item["snapshot"]["matches"][0]["normalized"] == "+70000000001"
    assert item["snapshot"]["matches"][0]["right"][0]["quote"] == "https://wa.me/70000000001"
    assert item["otherAdvertisement"]["account"]


@pytest.mark.parametrize("status", ["confirmed", "rejected"])
def test_link_review_persists_actor_reason_and_audit_without_changing_legal_records(
    service, status
):
    before = deepcopy(service.store.documents)
    request = payload(service)
    saved = service.save(A, request, USER)
    assert saved.status == "proposed" and saved.reviewer is None
    assert service.save(A, request, USER) == saved
    proposed_count = len(service.store.documents["auditLogs"])
    reviewed = service.decide(saved.id, decision(status), USER)
    assert reviewed.status == status and reviewed.version == 2
    assert reviewed.reviewer == USER.uid and reviewed.reviewed_at
    assert reviewed.notes == decision().notes
    assert service.save(A, request, USER) == reviewed  # uncertain-commit replay, no extra audit
    assert len(service.store.documents["auditLogs"]) == proposed_count + 2
    for collection in ("complexes", "advertisements", "evidence", "signals"):
        assert service.store.documents.get(collection) == before.get(collection)
    item = service.candidates(A)["items"][0]
    assert item["saved"]["status"] == status
    with pytest.raises(AppError) as error:
        service.decide(saved.id, decision(status), USER)
    assert error.value.status_code == 409


@pytest.mark.parametrize("change", ["version", "text"])
def test_stale_original_blocks_review_atomically_even_if_some_contacts_remain(service, change):
    saved = service.save(A, payload(service), USER)
    source = service.store.documents["advertisements"][A]
    if change == "version":
        source["version"] += 1
    else:
        source["text"] += " Изменённый текст без обновления версии"
    before = deepcopy(service.store.documents)
    with pytest.raises(AppError) as error:
        service.decide(saved.id, decision(), USER)
    assert error.value.code == "TRACE_STALE"
    assert service.store.documents == before


def test_alias_changes_between_preview_and_save_do_not_silently_replace_reasons(service):
    complex_id = service.store.documents["advertisements"][A]["complexId"]
    complex_ = service.store.documents["complexes"][complex_id]
    complex_["aliases"] = ["Другой учебный бренд"]
    for ad in (A, B):
        service.store.documents["advertisements"][ad]["text"] += " Другой учебный бренд"
    request = payload(service)
    complex_["aliases"] = []
    before = deepcopy(service.store.documents)
    with pytest.raises(AppError) as error:
        service.save(A, request, USER)
    assert error.value.status_code == 409
    assert service.store.documents == before


def test_cross_scope_missing_and_no_match_do_not_create_links(service):
    request = payload(service)
    for change, code in [
        ("scope", "NOT_FOUND"),
        ("no_match", "TRACE_NO_MATCH"),
        ("version", "CONFLICT"),
    ]:
        old = deepcopy(service.store.documents["advertisements"][B])
        if change == "scope":
            service.store.documents["advertisements"][B]["demo"] = False
        elif change == "version":
            service.store.documents["advertisements"][B]["version"] = 2
        else:
            service.store.documents["advertisements"][B]["text"] = "DEMO без контактов"
        before = deepcopy(service.store.documents)
        with pytest.raises(AppError) as error:
            service.save(A, request, USER)
        assert error.value.code == code
        assert service.store.documents == before
        service.store.documents["advertisements"][B] = old


def test_parallel_proposal_and_review_have_single_records_and_audit(service):
    request = payload(service)
    with ThreadPoolExecutor(max_workers=4) as pool:
        links = list(pool.map(lambda _: service.save(A, request, USER), range(4)))
    assert len({link.id for link in links}) == 1
    assert len(service.store.documents["adLinks"]) == 1

    def review(_):
        try:
            service.decide(links[0].id, decision(), USER)
            return "success"
        except AppError as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(review, range(4)))
    assert results.count("success") == 1
    assert results.count(409) == 3
    events = [
        e for e in service.store.documents["auditLogs"].values() if e["entityType"] == "adLink"
    ]
    assert len(events) == 4  # propose/review in each of two complexes


def test_api_requires_authentication_and_rejects_client_forged_decisions(service):
    app = create_app(Settings(_env_file=None, firebase_enabled=False))
    app.dependency_overrides[workspace_service] = lambda: service.workspace
    with TestClient(app) as client:
        assert client.get(f"/api/v1/advertisements/{A}/trace").status_code == 401
        assert client.post(f"/api/v1/advertisements/{A}/trace", json={}).status_code == 401
        assert client.post("/api/v1/ad-links/link/decision", json={}).status_code == 401
        app.dependency_overrides[current_user] = lambda: USER
        preview = client.get(f"/api/v1/advertisements/{A}/trace")
        assert preview.status_code == 200 and preview.headers["cache-control"] == "no-store"
        forged = payload(service).model_dump(by_alias=True)
        forged["status"] = "confirmed"
        assert client.post(f"/api/v1/advertisements/{A}/trace", json=forged).status_code == 422
        saved = client.post(
            f"/api/v1/advertisements/{A}/trace", json=payload(service).model_dump(by_alias=True)
        )
        assert saved.status_code == 200 and saved.json()["status"] == "proposed"
        path = f"/api/v1/ad-links/{saved.json()['id']}/decision"
        assert (
            client.post(
                path, json={"decision": "confirmed", "notes": "   ", "expectedVersion": 1}
            ).status_code
            == 422
        )
        reviewed = client.post(path, json=decision().model_dump(by_alias=True))
        assert reviewed.status_code == 200 and reviewed.json()["reviewer"] == USER.uid
