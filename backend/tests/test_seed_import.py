from copy import deepcopy

import pytest

from app.core.errors import Conflict
from app.services.seed import import_demo_seed
from tests.fakes import MemoryStore


def test_seed_import_is_atomic_and_idempotent():
    store = MemoryStore()
    first = import_demo_seed(store, "admin-1")
    assert first["created"] == 37
    before = deepcopy(store.documents)
    second = import_demo_seed(store, "admin-1")
    assert second["alreadyImported"] is True
    assert store.documents == before


def test_seed_preserves_existing_analyst_activity():
    store = MemoryStore(
        {
            "complexes": [
                {"id": "demo-complex-01", "demo": True, "name": "Analyst edited this record"}
            ]
        }
    )
    result = import_demo_seed(store, "admin-1")
    assert result["skipped"] == 1
    assert store.get("complexes", "demo-complex-01")["name"] == "Analyst edited this record"


def test_collision_with_real_data_cancels_entire_import():
    store = MemoryStore({"complexes": [{"id": "demo-complex-01", "demo": False}]})
    before = deepcopy(store.documents)
    with pytest.raises(Conflict):
        import_demo_seed(store, "admin-1")
    assert store.documents == before


def test_transaction_failure_does_not_leave_partial_writes():
    store = MemoryStore()

    def operation(tx):
        tx.create("complexes", "one", {"id": "one"})
        raise RuntimeError("simulated interruption")

    with pytest.raises(RuntimeError):
        store.atomic(operation)
    assert store.documents == {}
