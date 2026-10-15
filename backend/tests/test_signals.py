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
    app.dependency_overrides[current_user] = lambda: Principal(uid="human-reviewer", role="analyst")
    app.dependency_overrides[workspace_service] = lambda: WorkspaceService(store)
    with TestClient(app) as client:
        yield client, store


def create(client, complex_id="demo-complex-02"):
    response = client.post(
        "/api/v1/signals",
        json={
            "complexId": complex_id,
            "expectedComplexVersion": 1,
            "title": "DEMO — проверить источники",
            "reason": "Нужна дополнительная проверка",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def decide(client, signal, action, notes="Проверено человеком"):
    return client.post(
        f"/api/v1/signals/{signal['id']}/decision",
        json={
            "expectedVersion": signal["version"],
            "action": action,
            "notes": notes,
        },
    )


def test_full_signal_workflow_and_immutable_revision(workspace):
    client, store = workspace
    signal = create(client)
    assert signal["status"] == "draft"
    assert signal["snapshot"]["risk"]["score"] == 70
    assert decide(client, signal, "confirm").status_code == 409
    pending = decide(client, signal, "submit").json()
    assert pending["status"] == "pending_review"
    returned = decide(client, pending, "return", "Уточнить источник").json()
    assert returned["reviewer"] == "human-reviewer" and returned["reviewedAt"]
    assert returned["status"] == "returned"
    pending = decide(client, returned, "submit").json()
    confirmed = decide(client, pending, "confirm").json()
    assert confirmed["status"] == "confirmed"
    assert decide(client, confirmed, "return").status_code == 409
    assert len(store.documents["signalRevisions"]) == 5
    old = client.get(f"/api/v1/signals/{signal['id']}/revisions/1").json()
    assert old == signal
    events = client.get(f"/api/v1/signals/{signal['id']}/history").json()["items"]
    assert len(events) == 5 and events[0]["details"]["to"] == "confirmed"


def test_changed_complex_cannot_be_confirmed_from_stale_snapshot(workspace):
    client, store = workspace
    signal = decide(client, create(client), "submit").json()
    change = client.post(
        "/api/v1/complexes/demo-complex-02/factors/decision",
        json={
            "code": "R1",
            "decision": "rejected",
            "expectedVersion": 1,
            "evidenceIds": [],
            "notes": "Требуется перепроверка документа",
        },
    )
    assert change.status_code == 200
    before = deepcopy(store.documents)
    assert decide(client, signal, "confirm").status_code == 409
    assert store.documents == before
    returned = decide(client, signal, "return").json()
    refreshed = decide(client, returned, "submit").json()
    assert refreshed["snapshot"]["risk"]["score"] == 35
    assert signal["snapshot"]["risk"]["score"] == 70
    confirmed = decide(client, refreshed, "confirm").json()
    assert confirmed["status"] == "confirmed"


def test_versions_reason_and_actor_cannot_be_forged(workspace):
    client, _ = workspace
    signal = create(client)
    decide(client, signal, "submit")
    assert decide(client, signal, "submit").status_code == 409
    assert (
        client.post(
            f"/api/v1/signals/{signal['id']}/decision",
            json={
                "action": "confirm",
                "expectedVersion": 2,
                "notes": "",
                "reviewer": "forged",
            },
        ).status_code
        == 422
    )


def test_reports_are_real_pdf_and_escaped_html_with_snapshot(workspace):
    client, store = workspace
    signal = create(client)
    store.documents["signals"][signal["id"]]["title"] = '<img src="file:///etc/passwd">'
    html = client.get(f"/api/v1/signals/{signal['id']}/report?format=html")
    assert html.status_code == 200
    assert '<img src="file:' not in html.text and "&lt;img" in html.text
    assert "70 / 100" in html.text and "Черновик" in html.text
    assert "sandbox" in html.headers["content-security-policy"]
    pdf = client.get(f"/api/v1/signals/{signal['id']}/report")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert len(pdf.content) > 5000
    assert pdf.headers["cache-control"] == "no-store"
    assert "application/pdf" in pdf.headers["content-type"]
    assert client.get("/api/v1/signals").json()["items"][0]["risk"]["score"] == 70


def test_all_signal_routes_require_auth():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        for path in [
            "/signals",
            "/signals/any",
            "/signals/any/history",
            "/signals/any/report",
            "/signals/any/revisions/1",
        ]:
            assert client.get("/api/v1" + path).status_code == 401
        assert client.post("/api/v1/signals").status_code == 401
        assert client.post("/api/v1/signals/any/decision").status_code == 401


def test_non_demo_signal_is_hidden(workspace):
    client, store = workspace
    signal = create(client)
    store.documents["signals"][signal["id"]]["demo"] = False
    assert client.get(f"/api/v1/signals/{signal['id']}/report").status_code == 404
    assert client.get("/api/v1/signals").json()["items"] == []


def test_history_pages_keep_ties_scope_and_all_decisions(workspace):
    client, store = workspace
    first = create(client)
    second = create(client, "demo-complex-04")
    pending = decide(client, first, "submit").json()
    returned = decide(client, pending, "return").json()
    pending = decide(client, returned, "submit").json()
    decide(client, pending, "confirm")
    # Firestore tie-break is createdAt DESC, document name ASC, not UUID time order.
    for row in store.documents["auditLogs"].values():
        row["createdAt"] = "2026-10-15T12:00:00+00:00"
    hidden = deepcopy(next(iter(store.documents["auditLogs"].values())))
    hidden.update(id="hidden-audit", demo=False, entityId=first["id"])
    store.documents["auditLogs"][hidden["id"]] = hidden
    before = deepcopy(store.documents)
    cursor, events = None, []
    for _ in range(4):
        response = client.get(
            f"/api/v1/signals/{first['id']}/history",
            params={"limit": 2, **({"cursor": cursor} if cursor else {})},
        )
        assert response.status_code == 200
        page = response.json()
        events.extend(page["items"])
        cursor = page["nextCursor"]
        if cursor is None:
            break
    assert cursor is None and len(events) == 5
    ids = [row["id"] for row in events]
    assert ids == sorted(set(ids))
    assert all(row["entityId"] == first["id"] and row["demo"] for row in events)
    assert {row["details"].get("to") for row in events} == {
        None,
        "pending_review",
        "returned",
        "confirmed",
    }
    assert (
        client.get(f"/api/v1/signals/{second['id']}/history", params={"cursor": ids[0]}).status_code
        == 409
    )
    assert (
        client.get(
            f"/api/v1/signals/{first['id']}/history", params={"cursor": "deleted-row"}
        ).status_code
        == 409
    )
    assert store.documents == before


@pytest.mark.parametrize("suffix", ["history", "revisions/1", "report", "report?format=html"])
def test_missing_or_hidden_signal_cannot_expose_related_data(workspace, suffix):
    client, store = workspace
    signal = create(client)
    store.documents["signals"][signal["id"]]["demo"] = False
    before = deepcopy(store.documents)
    assert client.get(f"/api/v1/signals/{signal['id']}/{suffix}").status_code == 404
    assert client.get(f"/api/v1/signals/missing-signal/{suffix}").status_code == 404
    assert store.documents == before
