"""Unified intake/review against native Firestore transactions; synthetic providers only."""

import pytest

from app.core.config import Settings
from app.core.errors import Conflict
from app.models.auth import Principal
from app.services.files import FileService
from app.services.material_analysis import MaterialProcessor
from app.services.materials import MaterialService
from tests.test_analysis import FakeFiles
from tests.test_materials import CID, Provider, ad, review_payload


def test_native_material_dedup_cache_atomic_review_and_stale_fence(workspace):
    user = Principal(uid="native-material-reviewer", role="analyst")
    settings = Settings(_env_file=None, gemini_api_key="", gemini_model="local-test")
    files = FileService(workspace, FakeFiles())
    provider = Provider()
    first = ad(workspace)
    ad(workspace)
    materials = MaterialService(workspace, files)
    before = materials.detail(first.id)
    assert before["occurrenceCount"] == 2
    processor = MaterialProcessor(workspace, provider, files, settings)
    processor.process(user, 20)
    item = materials.detail(before["id"])
    assert item["priority"]["score"] == 35
    assert len(provider.calls) == 1
    payload = review_payload(item)
    reviewed = materials.review(item["id"], payload, user)
    assert reviewed["confirmedRisk"]["score"] == 35
    assert materials.review(item["id"], payload, user) == reviewed
    with pytest.raises(Conflict):
        materials.review(item["id"], review_payload(item, decision="rejected"), user)
    assert workspace.complex_detail(CID)["risk"]["score"] == 35
    current = materials.detail(item["id"])
    rejected = materials.review(current["id"], review_payload(current, decision="rejected"), user)
    # The seed's independent R3 proof remains; only the new source is withdrawn.
    assert rejected["confirmedRisk"]["score"] == 10
    events = workspace.store.list("auditLogs", filters=[("entityId", "==", item["id"])], limit=20)
    assert len(events) == 2
