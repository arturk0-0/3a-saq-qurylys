import logging
import re
from collections.abc import Callable
from typing import Any

from google.api_core.exceptions import (
    Aborted,
    AlreadyExists,
    FailedPrecondition,
    GoogleAPICallError,
    RetryError,
)
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.errors import AppError, Conflict, IntegrationUnavailable
from app.repositories.store import Document, T, UnitOfWork, matches_filter

logger = logging.getLogger(__name__)
COLLECTIONS = frozenset(
    {
        "developers",
        "companies",
        "companyProjects",
        "complexes",
        "advertisements",
        "adLinks",
        "evidence",
        "signals",
        "signalRevisions",
        "aiHypotheses",
        "auditLogs",
        "seedRuns",
        "users",
        "analysisRuns",
        "usageLimits",
        "monitorSources",
        "monitorItems",
        "monitorRuns",
        "monitorEvents",
        "monitorLimits",
        "monitorAiRuns",
    }
)


def firestore_error(exc: GoogleAPICallError | RetryError, operation: str) -> AppError:
    # Missing/building indexes are FailedPrecondition, but not every precondition
    # failure is about an index. Never echo the provider message or console URL.
    if isinstance(exc, FailedPrecondition) and "requires an index" in str(exc).lower():
        logger.error("Firestore %s failed: code=FIRESTORE_INDEX_REQUIRED", operation)
        return AppError(
            503,
            "FIRESTORE_INDEX_REQUIRED",
            "Firestore query index is missing or building; check deployment indexes",
        )
    logger.error("Firestore %s failed: %s", operation, type(exc).__name__)
    return IntegrationUnavailable("Firestore")


def validate_path(collection: str, record_id: str | None = None) -> None:
    if collection not in COLLECTIONS:
        raise ValueError("Unsupported collection")
    if record_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", record_id):
        raise ValueError("Invalid document ID")


class FirestoreUnitOfWork:
    def __init__(self, db, transaction):
        self.db = db
        self.transaction = transaction

    def reference(self, collection: str, record_id: str):
        validate_path(collection, record_id)
        return self.db.collection(collection).document(record_id)

    def get(self, collection: str, record_id: str) -> Document | None:
        snapshot = self.reference(collection, record_id).get(
            transaction=self.transaction, timeout=10
        )
        return snapshot.to_dict() if snapshot.exists else None

    def create(self, collection: str, record_id: str, data: Document) -> None:
        self.transaction.create(self.reference(collection, record_id), data)

    def set(self, collection: str, record_id: str, data: Document) -> None:
        self.transaction.set(self.reference(collection, record_id), data)


class FirestoreStore:
    def __init__(self, db):
        self.db = db

    def get(self, collection: str, record_id: str) -> Document | None:
        validate_path(collection, record_id)
        try:
            snapshot = self.db.collection(collection).document(record_id).get(timeout=10)
            return snapshot.to_dict() if snapshot.exists else None
        except (GoogleAPICallError, RetryError) as exc:
            raise firestore_error(exc, "read") from None

    def list(
        self,
        collection: str,
        *,
        filters: list[tuple[str, str, Any]] | None = None,
        after_id: str | None = None,
        limit: int = 100,
        newest_first: bool = False,
    ) -> list[Document]:
        validate_path(collection, after_id)
        if not 1 <= limit <= 500:
            raise ValueError("Query limit must be between 1 and 500")
        query = self.db.collection(collection)
        for field, operator, value in filters or []:
            query = query.where(filter=FieldFilter(field, operator, value))
        if newest_first:
            query = query.order_by("createdAt", direction=firestore.Query.DESCENDING)
        query = query.order_by("__name__")
        if after_id:
            cursor = {"__name__": self.db.collection(collection).document(after_id)}
            if newest_first:
                row = self.get(collection, after_id)
                if (
                    not row
                    or not row.get("createdAt")
                    or any(not matches_filter(row, f, op, v) for f, op, v in filters or [])
                ):
                    raise Conflict("Cursor no longer exists in this query")
                cursor["createdAt"] = row["createdAt"]
            query = query.start_after(cursor)
        try:
            return [snapshot.to_dict() for snapshot in query.limit(limit).stream(timeout=10)]
        except (GoogleAPICallError, RetryError) as exc:
            raise firestore_error(exc, "query") from None

    def atomic(self, operation: Callable[[UnitOfWork], T]) -> T:
        @firestore.transactional
        def execute(transaction):
            return operation(FirestoreUnitOfWork(self.db, transaction))

        try:
            return execute(self.db.transaction(max_attempts=3))
        except AlreadyExists:
            raise Conflict("Record already exists") from None
        except ValueError as exc:
            # The SDK wraps max-attempt contention in ValueError, with Aborted as
            # its explicit cause. Do not hide unrelated callback/programming errors.
            if isinstance(exc.__cause__, Aborted):
                raise Conflict() from None
            raise
        except (GoogleAPICallError, RetryError) as exc:
            raise firestore_error(exc, "transaction") from None
