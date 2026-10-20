"""The publication gate rejects missing/building indexes and wrong cursor ordering."""

import runpy
from pathlib import Path

import pytest

check = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "deploy/check-index-readiness.py")
)["pending_indexes"]


@pytest.mark.parametrize("explicit_name", [False, True])
def test_index_gate_requires_ready_and_exact_order(explicit_name):
    fields = [{"fieldPath": "createdAt", "order": "DESCENDING"}]
    name = {"fieldPath": "__name__", "order": "ASCENDING"}
    expected = {
        "indexes": [
            {"collectionGroup": "droneRuns", "fields": fields + ([name] if explicit_name else [])}
        ]
    }
    remote = {
        "name": "projects/demo/databases/(default)/collectionGroups/droneRuns/indexes/example",
        "fields": fields + [name],
        "queryScope": "COLLECTION",
        "state": "CREATING",
    }
    assert check(expected, [])
    assert check(expected, [remote])
    remote["state"] = "READY"
    assert check(expected, [remote]) == []
    remote["fields"] = [{"fieldPath": "createdAt", "order": "ASCENDING"}, name]
    assert check(expected, [remote])
    if explicit_name:
        remote["fields"] = fields + [{"fieldPath": "__name__", "order": "DESCENDING"}]
        assert check(expected, [remote])
