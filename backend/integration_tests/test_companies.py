"""Opt-in local Firestore SDK; all registry responses synthetic and injected."""

from copy import deepcopy

import pytest

from app.core.errors import Conflict
from app.models.companies import RefreshCompany, SaveSourceProject
from app.services.companies import CompanyService
from tests.test_companies import save
from tests.test_companies import service as service_fixture
from tests.test_monitoring import USER


def test_sdk_company_source_save_refresh_and_cursor(workspace):
    local = service_fixture.__wrapped__()
    service = CompanyService(workspace, local.registry)
    before = deepcopy(workspace.complex_detail("demo-complex-01"))
    result = save(service)
    first = service.list(limit=1)
    assert len(first["items"]) == 1 and first["nextCursor"]
    second = service.list(first["nextCursor"], limit=1)
    assert len(second["items"]) == 1 and second["items"][0]["id"] != first["items"][0]["id"]
    record = service.get(result["companyIds"][0])
    refreshed = service.refresh(
        record["id"], RefreshCompany(expected_version=record["version"]), USER
    )
    assert refreshed["version"] == record["version"] + 1
    assert workspace.complex_detail("demo-complex-01") == before


def test_sdk_real_import_atomic_parties_and_stale_source_save(workspace):
    local = service_fixture.__wrapped__()
    workspace.demo_only = False
    service = CompanyService(workspace, local.registry)
    preview = service.preview("12")
    payload = SaveSourceProject(
        expected_version=0,
        expected_document_sha256=preview["project"]["documentSha256"],
        import_to_registry=True,
    )
    saved = service.save("12", payload, USER)
    card = workspace.complex_detail(saved["registryId"])
    assert card["authorizedCompany"]["bin"] == "000000000002"
    assert card["risk"]["score"] == 0 and card["legalBasis"]["status"] == "unknown"
    with pytest.raises(Conflict):
        service.save("12", payload, USER)
    assert workspace.complex_detail(saved["registryId"]) == card
