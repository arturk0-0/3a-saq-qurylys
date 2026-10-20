"""Single-process, local JSON persistence for fictional demonstration records only."""

import json
import os
from copy import deepcopy
from pathlib import Path
from threading import RLock

from app.core.errors import AppError, Conflict
from app.repositories.store import matches_filter


class Transaction:
    def __init__(self, documents):
        self.documents = documents
        self.wrote = False

    def get(self, collection, record_id):
        if self.wrote:
            raise RuntimeError("All transaction reads must precede writes")
        return deepcopy(self.documents.get(collection, {}).get(record_id))

    def create(self, collection, record_id, data):
        if record_id in self.documents.get(collection, {}):
            raise Conflict()
        self.set(collection, record_id, data)

    def set(self, collection, record_id, data):
        self.wrote = True
        self.documents.setdefault(collection, {})[record_id] = deepcopy(data)


class LocalStore:
    def __init__(self, root: Path, seed: dict):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "demo.json"
        self.lock = RLock()
        if self.path.exists():
            self.documents = json.loads(self.path.read_text())
        else:
            self.documents = {k: {r["id"]: r for r in rows} for k, rows in seed.items()}
            self._persist(self.documents)

    def _persist(self, documents):
        pending = self.path.with_suffix(".pending")
        with pending.open("w", encoding="utf-8") as stream:
            json.dump(documents, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, self.path)

    def get(self, collection, record_id):
        with self.lock:
            return deepcopy(self.documents.get(collection, {}).get(record_id))

    def list(self, collection, *, filters=None, after_id=None, limit=100, newest_first=False):
        with self.lock:
            rows = sorted(self.documents.get(collection, {}).values(), key=lambda r: r["id"])
            if newest_first:
                rows.sort(key=lambda r: r["createdAt"], reverse=True)
            for field, operator, value in filters or []:
                rows = [r for r in rows if matches_filter(r, field, operator, value)]
            if after_id:
                if newest_first:
                    index = next((i for i, r in enumerate(rows) if r["id"] == after_id), None)
                    if index is None:
                        raise Conflict("Cursor no longer exists")
                    rows = rows[index + 1 :]
                else:
                    rows = [r for r in rows if r["id"] > after_id]
            return deepcopy(rows[:limit])

    def atomic(self, operation):
        with self.lock:
            pending = deepcopy(self.documents)
            result = operation(Transaction(pending))
            self._persist(pending)
            self.documents = pending
            return result


class LocalFiles:
    def __init__(self, root: Path):
        self.root = (root / "uploads").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name):
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise AppError(400, "INVALID_FILE_PATH", "Invalid local file path")
        return path

    def put(self, path, data, media_type):
        target = self.path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)

    def get(self, path):
        try:
            return self.path(path).read_bytes()
        except FileNotFoundError:
            raise AppError(404, "NO_FILE", "Local file is missing") from None

    def delete(self, path):
        self.path(path).unlink(missing_ok=True)
