"""Native Firestore SDK with local emulator; all photos and AI responses synthetic."""

from copy import deepcopy

import pytest

from app.core.errors import Conflict
from app.models.drone import ReviewInspection
from app.services.drone import DroneService
from tests.test_analysis import USER
from tests.test_drone import analyze, create, uploaded
from tests.test_drone import service as service_fixture


def test_sdk_drone_scope_cursor_atomic_analysis_and_review(workspace):
    local = service_fixture.__wrapped__()
    service = DroneService(workspace, local.storage, local.client, local.settings)
    before = deepcopy(workspace.complex_detail("demo-complex-01"))
    item = uploaded(service, complex_id="demo-complex-01")
    create(service)
    first = service.list(limit=1)
    assert (
        first["nextCursor"]
        and first["items"][0]["id"] != service.list(first["nextCursor"], 1)["items"][0]["id"]
    )
    completed, _ = analyze(service, item)
    history = service.runs(item["id"], limit=1)
    assert history["items"][0]["id"] == completed["latestRunId"]
    payload = ReviewInspection(
        expected_version=completed["version"],
        run_id=completed["latestRunId"],
        decision="needs_followup",
        notes="Учебная проверка второго ракурса",
    )
    reviewed = service.review(item["id"], payload, USER)
    with pytest.raises(Conflict):
        service.review(item["id"], payload, USER)
    assert service.get(item["id"])["reviews"] == reviewed["reviews"]
    assert workspace.complex_detail("demo-complex-01") == before
