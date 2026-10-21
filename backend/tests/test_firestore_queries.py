"""Real SDK query/cursor serialization with the stream RPC replaced; no cloud calls."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.api_core.exceptions import (
    Aborted,
    FailedPrecondition,
    PermissionDenied,
    RetryError,
    ServiceUnavailable,
)
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.types import StructuredQuery

from app.api.dependencies import current_user
from app.api.workspace import workspace_service
from app.core.config import Settings
from app.core.errors import AppError, Conflict
from app.main import create_app
from app.models.auth import Principal
from app.repositories.firestore import FirestoreStore
from app.services.workspace import WorkspaceService


@pytest.fixture
def offline_store(monkeypatch):
    db = firestore.Client(project="offline-test", credentials=AnonymousCredentials())
    queries = []

    def stream(query, *, timeout):
        assert timeout == 10
        queries.append(query._to_protobuf())
        return iter([])

    monkeypatch.setattr(firestore.Query, "stream", stream)
    try:
        yield FirestoreStore(db), queries
    finally:
        db.close()


@pytest.mark.parametrize("demo_only", [True, False])
@pytest.mark.parametrize("field", ["entityId", "complexId"])
def test_history_queries_have_declared_index_definitions_and_stable_order(
    offline_store, monkeypatch, demo_only, field
):
    store, queries = offline_store
    workspace = WorkspaceService(store, demo_only=demo_only)
    if field == "complexId":
        monkeypatch.setattr(workspace, "complex", lambda _: None)
        workspace.page("auditLogs", complex_id="object-1", limit=2)
    else:
        workspace.page("auditLogs", extra_filters=[(field, "==", "object-1")], limit=2)
    query = queries[0]
    assert query.from_[0].collection_id == "auditLogs"
    assert query.limit == 3  # one extra row to determine nextCursor
    assert [(order.field.field_path, order.direction) for order in query.order_by] == [
        ("createdAt", StructuredQuery.Direction.DESCENDING),
        ("__name__", StructuredQuery.Direction.ASCENDING),
    ]
    filters = query.where.composite_filter.filters if demo_only else [query.where]
    expected_fields = ["demo", field] if demo_only else [field]
    assert [entry.field_filter.field.field_path for entry in filters] == expected_fields
    expected_index = [{"fieldPath": name, "order": "ASCENDING"} for name in expected_fields] + [
        {"fieldPath": "createdAt", "order": "DESCENDING"},
        {"fieldPath": "__name__", "order": "ASCENDING"},
    ]
    indexes = json.loads((Path(__file__).parents[2] / "firestore.indexes.json").read_text())[
        "indexes"
    ]
    assert any(
        index["collectionGroup"] == "auditLogs"
        and index["queryScope"] == "COLLECTION"
        and index["fields"] == expected_index
        for index in indexes
    )


def test_history_cursor_serializes_date_and_document_reference(offline_store, monkeypatch):
    store, queries = offline_store
    captured_at = "2026-10-15T10:00:00+00:00"
    monkeypatch.setattr(
        store, "get", lambda *_: {"createdAt": captured_at, "entityId": "signal-1", "demo": True}
    )
    store.list(
        "auditLogs",
        newest_first=True,
        after_id="event-1",
        filters=[("demo", "==", True), ("entityId", "==", "signal-1")],
        limit=2,
    )
    cursor = queries[0].start_at
    assert cursor.before is False  # start_after, not start_at
    assert len(cursor.values) == 2
    assert cursor.values[0].string_value == captured_at
    assert cursor.values[1].reference_value.endswith("/documents/auditLogs/event-1")


@pytest.mark.parametrize(
    "row",
    [
        None,
        {"createdAt": "date", "entityId": "another-signal", "demo": True},
        {"createdAt": "date", "entityId": "signal-1", "demo": False},
        {"entityId": "signal-1", "demo": True},
    ],
)
def test_history_cursor_cannot_escape_scope_or_use_deleted_invalid_row(
    offline_store, monkeypatch, row
):
    store, queries = offline_store
    monkeypatch.setattr(store, "get", lambda *_: row)
    with pytest.raises(Conflict):
        store.list(
            "auditLogs",
            newest_first=True,
            after_id="event-1",
            filters=[("demo", "==", True), ("entityId", "==", "signal-1")],
        )
    assert queries == []


@pytest.mark.parametrize(
    "failure,code",
    [
        (
            FailedPrecondition("The query requires an index. PRIVATE_PROVIDER_URL"),
            "FIRESTORE_INDEX_REQUIRED",
        ),
        (
            FailedPrecondition("Unrelated precondition PRIVATE_PROVIDER_URL"),
            "INTEGRATION_UNAVAILABLE",
        ),
        (PermissionDenied("PRIVATE_PROVIDER_URL"), "INTEGRATION_UNAVAILABLE"),
        (ServiceUnavailable("PRIVATE_PROVIDER_URL"), "INTEGRATION_UNAVAILABLE"),
        (
            RetryError("PRIVATE_PROVIDER_URL", ServiceUnavailable("PRIVATE_CAUSE")),
            "INTEGRATION_UNAVAILABLE",
        ),
    ],
)
def test_query_failure_never_leaks_provider_text_or_mislabels_preconditions(
    offline_store, monkeypatch, caplog, failure, code
):
    store, _ = offline_store

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(firestore.Query, "stream", fail)
    with pytest.raises(AppError) as error:
        WorkspaceService(store).page("auditLogs", extra_filters=[("entityId", "==", "signal-1")])
    assert (error.value.status_code, error.value.code) == (503, code)
    assert "PRIVATE_PROVIDER_URL" not in caplog.text + error.value.message


def test_missing_index_is_an_authenticated_typed_history_error(offline_store, monkeypatch):
    store, _ = offline_store
    monkeypatch.setattr(store, "get", lambda *_: {"id": "signal-1", "demo": True})

    def fail(*args, **kwargs):
        raise FailedPrecondition("The query requires an index. PRIVATE_CONSOLE_URL")

    monkeypatch.setattr(firestore.Query, "stream", fail)
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[workspace_service] = lambda: WorkspaceService(store)
    with TestClient(app) as http:
        path = "/api/v1/signals/signal-1/history"
        assert http.get(path).status_code == 401
        app.dependency_overrides[current_user] = lambda: Principal(uid="reviewer", role="analyst")
        response = http.get(path)
    assert response.status_code == 503
    assert response.json()["code"] == "FIRESTORE_INDEX_REQUIRED"
    assert response.json()["requestId"] == response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"
    assert "PRIVATE_CONSOLE_URL" not in response.text


def test_bulk_reads_are_chunked_deduplicated_and_keep_missing_documents(offline_store, monkeypatch):
    from types import SimpleNamespace

    store, _ = offline_store
    batches = []

    def get_all(refs, *, timeout):
        assert timeout == 10
        batches.append([ref.id for ref in refs])
        # Native get_all order is not guaranteed; missing snapshots are explicit.
        return iter(
            [
                SimpleNamespace(
                    id=ref.id, exists=ref.id != "missing", to_dict=lambda ref=ref: {"id": ref.id}
                )
                for ref in reversed(refs)
            ]
        )

    monkeypatch.setattr(store.db, "get_all", get_all)
    keys = [f"row-{i}" for i in range(201)] + ["missing", "row-0"]
    result = store.get_many("materialJobs", keys)
    assert [len(batch) for batch in batches] == [200, 2]
    assert len(result) == 202
    assert result["missing"] is None
    assert result["row-200"] == {"id": "row-200"}
    assert store.get_many("materialJobs", []) == {}
    with pytest.raises(ValueError):
        store.get_many("materialJobs", ["bad/id"])


@pytest.mark.parametrize("always_abort", [False, True])
def test_transaction_read_abort_restarts_whole_callback_or_returns_conflict(
    offline_store, monkeypatch, always_abort
):
    store, _ = offline_store
    calls = []
    # Isolate the SDK boundary: Aborted from callback reads is not retried by its
    # commit retry loop. Each outer retry must receive a fresh transaction.
    monkeypatch.setattr(firestore, "transactional", lambda callback: callback)
    monkeypatch.setattr("app.repositories.firestore.time.sleep", lambda _: None)

    def operation(tx):
        calls.append(tx.transaction)
        if always_abort or len(calls) == 1:
            raise Aborted("PRIVATE_PROVIDER_MESSAGE")
        return "committed"

    if always_abort:
        with pytest.raises(Conflict) as error:
            store.atomic(operation)
        assert "PRIVATE_PROVIDER_MESSAGE" not in error.value.message
        assert len(calls) == 3
    else:
        assert store.atomic(operation) == "committed"
        assert len(calls) == 2
    assert len({id(tx) for tx in calls}) == len(calls)
