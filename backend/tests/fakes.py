"""Test-only adapters. Never imported by the running application."""

from collections.abc import Callable
from copy import deepcopy
from threading import RLock

from app.core.errors import Conflict
from app.repositories.store import T, UnitOfWork, matches_filter


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

    def list(self, collection, *, filters=None, after_id=None, limit=100, newest_first=False):
        rows = sorted(self.documents.get(collection, {}).values(), key=lambda row: row["id"])
        if newest_first:
            rows.sort(key=lambda row: row["createdAt"], reverse=True)
        for field, operator, value in filters or []:
            rows = [row for row in rows if matches_filter(row, field, operator, value)]
        if after_id:
            if newest_first:
                index = next((i for i, row in enumerate(rows) if row["id"] == after_id), None)
                if index is None:
                    raise Conflict("Cursor no longer exists in this query")
                rows = rows[index + 1 :]
            else:
                rows = [row for row in rows if row["id"] > after_id]
        return deepcopy(rows[:limit])

    def atomic(self, operation: Callable[[UnitOfWork], T]) -> T:
        with self.lock:
            copy = deepcopy(self.documents)
            result = operation(MemoryUnitOfWork(copy))
            self.documents = copy
            return result
