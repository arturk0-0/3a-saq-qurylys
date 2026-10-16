"""Storage SDK failures are simulated explicitly; never connect to a bucket."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import RetryError, ServiceUnavailable

from app.core.errors import AppError
from app.services.files import FirebaseFileStorage


@pytest.mark.parametrize(
    "operation,method", [("put", "upload_from_string"), ("get", "download_as_bytes")]
)
def test_storage_retry_deadline_is_safe_unavailable(operation, method, caplog):
    blob = Mock()
    failure = RetryError("PRIVATE_STORAGE_DETAIL", ServiceUnavailable("PRIVATE_CAUSE"))
    getattr(blob, method).side_effect = failure
    bucket = Mock()
    bucket.blob.return_value = blob
    storage = FirebaseFileStorage(SimpleNamespace(bucket=lambda: bucket))
    with pytest.raises(AppError) as error:
        if operation == "put":
            storage.put("evidence/test/image", b"test bytes", "image/png")
        else:
            storage.get("evidence/test/image")
    assert (error.value.status_code, error.value.code) == (503, "INTEGRATION_UNAVAILABLE")
    assert "PRIVATE" not in caplog.text + error.value.message
    assert getattr(blob, method).call_count == 1
    blob.delete.assert_not_called()


def test_simultaneous_uploads_leave_only_the_committed_private_file():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.core.errors import Conflict
    from app.services.files import FileService
    from app.services.seed_data import build_demo_seed
    from app.services.workspace import WorkspaceService
    from tests.fakes import MemoryStore
    from tests.test_analysis import USER, FakeFiles, png

    class RacingFiles(FakeFiles):
        def put(self, path, data, media_type):
            super().put(path, data, media_type)
            gate.wait(timeout=5)

    gate = Barrier(2)
    store = MemoryStore(build_demo_seed())
    storage = RacingFiles()
    files = FileService(WorkspaceService(store), storage)

    def upload():
        try:
            return files.upload("demo-ad-01", 1, png(), "image/png", USER)
        except Conflict as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: upload(), range(2)))
    assert sum(isinstance(item, Conflict) for item in results) == 1
    ad = store.get("advertisements", "demo-ad-01")
    assert ad["version"] == 2 and len(ad["attachmentIds"]) == 1
    item = store.get("evidence", ad["attachmentIds"][0])
    assert set(storage.objects) == {item["storagePath"]}
    assert len(store.documents["auditLogs"]) == 1


@pytest.mark.parametrize("committed", [False, True])
def test_unknown_transaction_outcome_never_deletes_uploaded_evidence(monkeypatch, committed):
    from app.services.files import FileService
    from app.services.seed_data import build_demo_seed
    from app.services.workspace import WorkspaceService
    from tests.fakes import MemoryStore
    from tests.test_analysis import USER, FakeFiles, png

    store = MemoryStore(build_demo_seed())
    storage = FakeFiles()
    files = FileService(WorkspaceService(store), storage)
    atomic = store.atomic

    def interrupted(operation):
        if committed:
            atomic(operation)
        raise AppError(503, "INTEGRATION_UNAVAILABLE", "Test-only unknown commit result")

    monkeypatch.setattr(store, "atomic", interrupted)
    with pytest.raises(AppError) as error:
        files.upload("demo-ad-01", 1, png(), "image/png", USER)
    assert error.value.status_code == 503
    assert len(storage.objects) == 1
    ad = store.get("advertisements", "demo-ad-01")
    assert ad["version"] == (2 if committed else 1)
    if committed:
        item = store.get("evidence", ad["attachmentIds"][0])
        assert item["storagePath"] in storage.objects
        assert files.download(item["id"]) == (png(), "image/png")


def test_cleanup_failure_does_not_hide_original_version_conflict(monkeypatch, caplog):
    from app.core.errors import Conflict
    from app.services.files import FileService
    from app.services.seed_data import build_demo_seed
    from app.services.workspace import WorkspaceService
    from tests.fakes import MemoryStore
    from tests.test_analysis import USER, FakeFiles, png

    store = MemoryStore(build_demo_seed())
    storage = FakeFiles()
    files = FileService(WorkspaceService(store), storage)
    original_put = storage.put

    def losing_upload(path, data, media_type):
        original_put(path, data, media_type)
        # Explicit adapter for an intervening committed advertisement update.
        store.documents["advertisements"]["demo-ad-01"]["version"] += 1

    monkeypatch.setattr(storage, "put", losing_upload)
    monkeypatch.setattr(storage, "delete", Mock(side_effect=RuntimeError("PRIVATE_CLEANUP_DETAIL")))
    with pytest.raises(Conflict):
        files.upload("demo-ad-01", 1, png(), "image/png", USER)
    assert "Orphan upload cleanup failed" in caplog.text
    assert "PRIVATE_CLEANUP_DETAIL" not in caplog.text
    assert len(storage.objects) == 1  # operator cleanup required; no false success
    assert not store.documents.get("auditLogs")
