from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import current_user
from app.api.workspace import workspace_service
from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.models.auth import Principal
from app.models.entities import Complex
from app.services.matching import candidate_reason, match_candidates, normalized_name
from app.services.seed_data import build_demo_seed
from app.services.workspace import WorkspaceService
from tests.fakes import MemoryStore


def workspace(mentions):
    store = MemoryStore(build_demo_seed())
    store.documents["analysisRuns"] = {
        "run1": {
            "id": "run1",
            "advertisementId": "demo-ad-01",
            "status": "succeeded",
            "demo": True,
            "extraction": {
                "hypotheses": [],
                "mentionedComplexes": mentions,
                "paymentTerms": [],
                "uncertainty": "Нужна проверка",
            },
        }
    }
    return WorkspaceService(store)


@pytest.mark.parametrize(
    "value", ["DEMO — ЖК Янтарный берег", "ЖК «ЯНТАРНЫЙ-БЕРЕГ»", "янтарный берег"]
)
def test_name_normalization_handles_case_labels_and_punctuation(value):
    assert normalized_name(value) == "янтарный берег"


def test_exact_alias_and_partial_candidates_never_relink_or_change_factors():
    service = workspace(["ЖК Янтарный берег", "Учебный берег", "Жилой комплекс Янтарный берег"])
    service.store.documents["complexes"]["demo-complex-01"]["aliases"] = ["Учебный берег"]
    before = deepcopy(service.store.documents)
    result = match_candidates(service, "demo-ad-01", "run1")
    assert [group["candidates"][0]["matchedBy"] for group in result["groups"]] == [
        "name",
        "alias",
        "partial_name",
    ]
    assert all(
        group["candidates"][0]["complexId"] == "demo-complex-01" for group in result["groups"]
    )
    assert result["currentComplexId"] == "demo-complex-01"
    assert service.store.documents == before


def test_ambiguous_aliases_remain_multiple_and_unknown_names_are_not_findings():
    service = workspace(["Общий учебный бренд", "Неизвестный проект", "квартал", "DEMO — ЖК"])
    for key in ["demo-complex-01", "demo-complex-02"]:
        service.store.documents["complexes"][key]["aliases"] = ["Общий учебный бренд"]
    result = match_candidates(service, "demo-ad-01", "run1")
    assert result["groups"][0]["ambiguous"] is True
    assert result["groups"][0]["candidateCount"] == 2
    assert all(not group["candidates"] for group in result["groups"][1:])
    assert "R1" not in repr(result)
    assert "selectedComplexId" not in result


def test_partial_match_requires_two_shared_words_and_legacy_records_need_no_migration():
    row = build_demo_seed()["complexes"][0]
    row.pop("aliases", None)
    complex_ = Complex.model_validate(row)
    assert complex_.aliases == []
    assert candidate_reason("берег", complex_) is None
    assert candidate_reason("Янтарный берег секция 2", complex_)[1] == "partial_name"


def test_matching_preserves_scope_and_rejects_wrong_or_incomplete_runs():
    service = workspace(["Янтарный берег"])
    service.store.documents["complexes"]["demo-complex-01"]["demo"] = False
    assert not match_candidates(service, "demo-ad-01", "run1")["groups"][0]["candidates"]
    with pytest.raises(AppError) as error:
        match_candidates(service, "demo-ad-02", "run1")
    assert error.value.status_code == 422
    service.store.documents["analysisRuns"]["run1"]["status"] = "failed"
    with pytest.raises(AppError) as error:
        match_candidates(service, "demo-ad-01", "run1")
    assert error.value.status_code == 409


def test_endpoint_requires_auth_and_exposes_typed_read_only_candidates():
    app = create_app(Settings(_env_file=None))
    path = "/api/v1/advertisements/demo-ad-01/matching-candidates?run_id=run1"
    service = workspace(["Янтарный берег"])
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        app.dependency_overrides[current_user] = lambda: Principal(uid="analyst", role="analyst")
        app.dependency_overrides[workspace_service] = lambda: service
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["groups"][0]["candidates"][0]["complexId"] == "demo-complex-01"
        assert client.get(path.replace("run1", "../invalid")).status_code == 422


def test_scan_and_candidate_limits_are_reported_without_silent_unique_match():
    service = workspace(["Общий учебный бренд"])
    original = service.store.documents["complexes"]["demo-complex-01"]
    for index in range(500):
        key = f"bounded-{index:03}"
        service.store.documents["complexes"][key] = {
            **original,
            "id": key,
            "aliases": ["Общий учебный бренд"],
        }
    result = match_candidates(service, "demo-ad-01", "run1")
    assert result["catalogLimited"] is True
    group = result["groups"][0]
    assert group["ambiguous"] and group["candidatesLimited"]
    assert group["candidateCount"] == 500 and len(group["candidates"]) == 10
