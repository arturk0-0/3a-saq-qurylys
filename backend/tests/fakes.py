"""Test-only adapters. Never imported by the running application."""

from collections.abc import Callable
from copy import deepcopy
from threading import RLock

from app.core.errors import Conflict
from app.repositories.store import T, UnitOfWork


class MemoryUnitOfWork:
    def __init__(self, documents):
        self.documents = documents
        self.wrote = False

    def get(self, collection, record_id):
        if self.wrote:
            raise RuntimeError("Firestore transactions require all reads before writes")
        return deepcopy(self.documents.get(collection, {}).get(record_id))

    def create(self, collection, record_id, data):
        self.wrote = True
        target = self.documents.setdefault(collection, {})
        if record_id in target:
            raise Conflict()
        target[record_id] = deepcopy(data)

    def set(self, collection, record_id, data):
        self.wrote = True
        self.documents.setdefault(collection, {})[record_id] = deepcopy(data)


class MemoryStore:
    def __init__(self, seed=None):
        self.documents = {
            key: {row["id"]: deepcopy(row) for row in rows} for key, rows in (seed or {}).items()
        }
        self.lock = RLock()

    def get(self, collection, record_id):
        with self.lock:
            return deepcopy(self.documents.get(collection, {}).get(record_id))

    def list(self, collection, *, filters=None, after_id=None, limit=100):
        rows = sorted(self.documents.get(collection, {}).values(), key=lambda row: row["id"])
        rows = [row for row in rows if not after_id or row["id"] > after_id]
        for field, operator, value in filters or []:
            assert operator == "==", "Implement a test adapter only for used query operators"
            rows = [row for row in rows if row.get(field) == value]
        return deepcopy(rows[:limit])

    def atomic(self, operation: Callable[[UnitOfWork], T]) -> T:
        with self.lock:
            copy = deepcopy(self.documents)
            result = operation(MemoryUnitOfWork(copy))
            self.documents = copy
            return result
