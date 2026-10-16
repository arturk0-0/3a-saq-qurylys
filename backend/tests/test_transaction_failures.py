"""Real Firestore retry machinery with transaction RPCs replaced; no cloud access."""

from unittest.mock import Mock

import pytest
from google.api_core.exceptions import Aborted, RetryError, ServiceUnavailable
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.transaction import Transaction

from app.core.errors import AppError, Conflict
from app.repositories.firestore import FirestoreStore


@pytest.fixture
def transaction_store(monkeypatch):
    db = firestore.Client(project="offline-retry-test", credentials=AnonymousCredentials())
    monkeypatch.setattr(
        Transaction, "_begin", lambda tx, retry_id=None: setattr(tx, "_id", b"test")
    )
    rollback = Mock()
    monkeypatch.setattr(Transaction, "_rollback", rollback)
    try:
        yield FirestoreStore(db), rollback
    finally:
        db.close()


def test_exhausted_sdk_contention_is_a_conflict_not_internal_error(transaction_store, monkeypatch):
    store, rollback = transaction_store
    commit = Mock(side_effect=Aborted("PRIVATE_CONTENTION_DETAIL"))
    monkeypatch.setattr(Transaction, "_commit", commit)
    operation = Mock(return_value="not committed")
    with pytest.raises(Conflict) as error:
        store.atomic(operation)
    assert commit.call_count == operation.call_count == 3
    rollback.assert_called_once()
    assert "PRIVATE_CONTENTION_DETAIL" not in error.value.message


def test_unknown_commit_failure_is_not_retried_by_application(transaction_store, monkeypatch):
    store, rollback = transaction_store
    commit = Mock(side_effect=ServiceUnavailable("PRIVATE_COMMIT_DETAIL"))
    monkeypatch.setattr(Transaction, "_commit", commit)
    operation = Mock()
    with pytest.raises(AppError) as error:
        store.atomic(operation)
    assert error.value.status_code == 503
    assert commit.call_count == operation.call_count == 1
    rollback.assert_called_once()
    assert "PRIVATE_COMMIT_DETAIL" not in error.value.message


def test_unrelated_callback_value_error_is_not_mislabeled_as_contention(
    transaction_store, monkeypatch
):
    store, _ = transaction_store
    commit = Mock()
    monkeypatch.setattr(Transaction, "_commit", commit)
    with pytest.raises(ValueError, match="test bug"):
        store.atomic(Mock(side_effect=ValueError("test bug")))
    commit.assert_not_called()


def test_sdk_retry_deadline_becomes_safe_unavailable(transaction_store, monkeypatch, caplog):
    store, _ = transaction_store
    cause = ServiceUnavailable("PRIVATE_RETRY_DETAIL")
    monkeypatch.setattr(
        Transaction, "_commit", Mock(side_effect=RetryError("PRIVATE_RETRY", cause))
    )
    with pytest.raises(AppError) as error:
        store.atomic(lambda tx: None)
    assert (error.value.status_code, error.value.code) == (503, "INTEGRATION_UNAVAILABLE")
    assert "PRIVATE_RETRY" not in caplog.text + error.value.message
