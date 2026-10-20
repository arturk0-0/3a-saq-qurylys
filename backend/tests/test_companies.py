"""All companies, projects and transports below are synthetic. No paid/cloud requests."""

from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.companies import company_service
from app.api.dependencies import current_user
from app.api.workspace import workspace_service
from app.core.config import Settings
from app.core.errors import AppError, Conflict
from app.main import create_app
from app.models.companies import RefreshCompany, SaveSourceProject
from app.services.companies import CompanyService
from app.services.company_sources import CompanyRegistry
from app.services.registries import RegistryClient
from app.services.seed_data import build_demo_seed
from app.services.workspace import WorkspaceService
from tests.fakes import MemoryStore
from tests.test_monitoring import USER
from tests.test_registries import detail


def project_data():
    value = detail()
    value["data"]["basicData"].update(
        city={"name_ru": "Усть-Каменогорск"}, address="Учебный адрес, Усть-Каменогорск"
    )
    value["data"]["locationData"] = {"latitude": "49.95", "longitude": "82.62"}
    value["data"]["companyData"]["developerData"]["develpoer_website"] = (
        "https://example.test/synthetic"
    )
    return value


@pytest.fixture
def service():
    def response(request):
        if request.url.path.endswith("getobjects"):
            return httpx.Response(
                200, json={"data": {"objects": {"data": [{"id": 12}], "next_page_url": None}}}
            )
        return httpx.Response(200, json=project_data())

    return CompanyService(
        WorkspaceService(MemoryStore(build_demo_seed())),
        CompanyRegistry(RegistryClient(httpx.MockTransport(response))),
    )


def save(service, import_=False, expected_version=0):
    preview = service.preview("12")
    return service.save(
        "12",
        SaveSourceProject(
            expected_version=expected_version,
            expected_document_sha256=preview["project"]["documentSha256"],
            import_to_registry=import_,
        ),
        USER,
    )


def test_preview_strips_contacts_and_requires_source_not_planned_date(service):
    result = service.preview("12")["project"]
    assert len(result["parties"]) == 2 and result["coordinates"]["latitude"] == 49.95
    assert result["stage"] == "under_construction"
    assert result["commissioningDate"] is None
    assert "email" not in str(result) and "phone" not in str(result)
    assert result["source"]["url"] == "https://homeportal.kz/ru/projects/12"
    assert len(result["documentSha256"]) == 64


def test_company_identity_provenance_and_unknown_fields_do_not_change_demo_or_scores(service):
    before = deepcopy(service.store.documents["complexes"])
    result = save(service)
    assert result["companyIds"] == ["bin-000000000001", "bin-000000000002"]
    company = service.get(result["companyIds"][0])
    assert company["foundCompletedCount"] is None
    assert {f["field"] for f in company["facts"]} == {"name", "bin", "website"}
    assert all(f["source"]["url"].endswith("/12") for f in company["facts"])
    assert service.store.documents["complexes"] == before
    assert len(service.store.documents["auditLogs"]) == 1
    assert service.get("demo-developer-01")["demo"] is True
    assert service.get("demo-developer-01")["facts"] == []


def test_real_import_is_explicit_scope_guarded_and_never_overwrites_existing_registry(service):
    with pytest.raises(AppError) as error:
        save(service, True)
    assert error.value.status_code == 403
    assert not service.store.documents.get("companies")
    service.workspace.demo_only = False
    result = save(service, True)
    card = service.workspace.complex_detail(result["registryId"])
    assert card["demo"] is False and card["legalBasis"]["status"] == "unknown"
    assert card["risk"]["score"] == 0 and not card["factors"]
    assert card["developer"]["bin"] == "000000000001"
    assert card["authorizedCompany"]["bin"] == "000000000002"
    assert card["participantSource"]["publisher"] == "Homeportal · КЖК"
    assert card["coordinateStatus"] == "source_point"
    before = deepcopy(card)
    with pytest.raises(Conflict):
        save(service, True, expected_version=1)
    assert service.workspace.complex_detail(result["registryId"]) == before


def test_same_bin_in_two_roles_has_one_profile(service):
    data = project_data()
    data["data"]["companyData"]["authorizedData"]["bin"] = "000000000001"
    service.registry.client = RegistryClient(
        httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    )
    result = save(service)
    assert result["companyIds"] == ["bin-000000000001"]
    assert len(service.list()["items"]) == 1
    assert len(service.get(result["companyIds"][0])["projects"][0]["parties"]) == 2


@pytest.mark.parametrize(
    "coordinates",
    [("0", "0"), ("43.2", "76.8"), ("NaN", "82.62"), ("49.95", "Infinity"), ("bad", "bad")],
)
def test_bad_or_other_city_points_are_not_turned_into_a_city_centre(service, coordinates):
    data = project_data()
    data["data"]["locationData"] = dict(zip(["latitude", "longitude"], coordinates, strict=True))
    service.registry.client = RegistryClient(
        httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    )
    assert service.preview("12")["project"]["coordinates"] is None


def test_missing_authorized_company_stays_unknown(service):
    data = project_data()
    data["data"]["companyData"].pop("authorizedData")
    service.registry.client = RegistryClient(
        httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    )
    result = save(service)
    assert len(result["companyIds"]) == 1
    assert service.get(result["companyIds"][0])["projects"][0]["parties"][0]["role"] == "developer"


def test_refresh_retains_disagreement_and_offline_snapshot_with_dates(service):
    company_id = save(service)["companyIds"][0]
    initial = service.get(company_id)
    data = project_data()
    data["data"]["companyData"]["developerData"]["name"] = "Иное учебное наименование"
    service.registry.client = RegistryClient(
        httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    )
    updated = service.refresh(company_id, RefreshCompany(expected_version=1), USER)
    assert len({f["value"] for f in updated["facts"] if f["field"] == "name"}) == 2
    assert updated["projects"][0]["stage"] is None  # No catalogue membership in this transport.
    service.registry.client = RegistryClient(
        httpx.MockTransport(lambda r: httpx.Response(503, text="private-provider-body"))
    )
    offline = service.refresh(company_id, RefreshCompany(expected_version=2), USER)
    assert offline["facts"] == updated["facts"] and offline["updatedAt"] == updated["updatedAt"]
    assert offline["lastError"] == "REGISTRY_UNAVAILABLE"
    assert initial["facts"][0]["source"]["retrievedAt"]
    assert "private-provider" not in str(offline)
    with pytest.raises(Conflict):
        service.refresh(company_id, RefreshCompany(expected_version=2), USER)


def test_new_bin_does_not_replace_original_company_or_link_it_to_wrong_projects(service):
    company_id = save(service)["companyIds"][0]
    data = project_data()
    data["data"]["companyData"]["developerData"]["bin"] = "000000000003"
    service.registry.client = RegistryClient(
        httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    )
    before = service.get(company_id)
    updated = service.refresh(company_id, RefreshCompany(expected_version=1), USER)
    assert updated["facts"] == before["facts"] and updated["lastError"] == "COMPANY_SOURCE_CHANGED"
    assert updated["bin"] == "000000000001"


def test_source_change_and_stale_version_abort_save(service):
    preview = service.preview("12")
    data = project_data()
    data["data"]["basicData"]["name"] = "Иной учебный блок"
    service.registry.client = RegistryClient(
        httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    )
    with pytest.raises(AppError) as error:
        service.save(
            "12",
            SaveSourceProject(
                expected_version=0, expected_document_sha256=preview["project"]["documentSha256"]
            ),
            USER,
        )
    assert error.value.code == "REGISTRY_DOCUMENT_CHANGED"
    save(service)
    with pytest.raises(Conflict):
        save(service)


def test_issued_permit_or_planned_end_is_not_commissioning_evidence(service):
    data = project_data()
    data["data"]["basicData"].update(
        commissioning_date="01.01.2020", act_date="01.01.2020", act_number="SYNTHETIC"
    )
    service.registry.client = RegistryClient(
        httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    )
    assert service.preview("12")["project"]["commissioningReference"] is None
    data["data"]["basicData"].update(
        act_registration_date="02.01.2020", act_registration_number="QA-1"
    )
    result = service.preview("12")["project"]
    assert result["stage"] == "commissioned"
    save(service)
    assert service.get("bin-000000000001")["foundCompletedCount"] == 1


@pytest.mark.parametrize(
    "path,method",
    [
        ("/companies", "GET"),
        ("/companies/bin-000000000001", "GET"),
        ("/companies/bin-000000000001/refresh", "POST"),
        ("/company-projects/search?q=test", "GET"),
        ("/company-projects/12", "GET"),
        ("/company-projects/12", "POST"),
    ],
)
def test_every_endpoint_requires_authentication(path, method):
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        assert client.request(method, "/api/v1" + path, json={}).status_code == 401


def test_api_workflow_uses_only_injected_synthetic_transport(service):
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[current_user] = lambda: USER
    app.dependency_overrides[workspace_service] = lambda: service.workspace
    app.dependency_overrides[company_service] = lambda: service
    with TestClient(app) as client:
        preview = client.get("/api/v1/company-projects/12").json()
        result = client.post(
            "/api/v1/company-projects/12",
            json={
                "expectedVersion": 0,
                "expectedDocumentSha256": preview["project"]["documentSha256"],
            },
        )
        assert result.status_code == 200
        profile = client.get("/api/v1/companies/" + result.json()["companyIds"][0]).json()
        assert profile["facts"] and profile["coverage"] == "saved_source_projects_only"
        assert (
            client.post(
                "/api/v1/companies/" + profile["id"] + "/refresh",
                json={"expectedVersion": profile["version"]},
            ).status_code
            == 200
        )


def test_duplicate_commissioning_act_at_same_address_is_not_counted_as_another_object(service):
    data = project_data()
    data["data"]["basicData"].update(
        act_number="QA-ACT",
        act_date="01.01.2020",
        act_registration_number="QA-REGISTERED",
        act_registration_date="02.01.2020",
    )
    service.registry.client = RegistryClient(
        httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    )
    save(service)
    data["data"]["basicData"]["name"] = "Переименованная учебная карточка"
    preview = service.preview("13")
    service.save(
        "13",
        SaveSourceProject(
            expected_version=0, expected_document_sha256=preview["project"]["documentSha256"]
        ),
        USER,
    )
    assert len(service.get("bin-000000000001")["projects"]) == 2
    assert service.get("bin-000000000001")["foundCompletedCount"] == 1


def test_bad_optional_website_does_not_discard_the_legal_parties(service):
    for website in ["https://", "https://user:password@example.test/", "javascript:alert(1)"]:
        data = project_data()
        data["data"]["companyData"]["developerData"]["develpoer_website"] = website
        service.registry.client = RegistryClient(
            httpx.MockTransport(lambda r, data=data: httpx.Response(200, json=data))
        )
        preview = service.preview("12")["project"]
        assert len(preview["parties"]) == 2 and preview["parties"][0]["website"] is None
        assert "password" not in str(preview)


def test_project_party_names_and_citations_are_snapshots_not_shared_global_aliases(service):
    service.workspace.demo_only = False
    first = save(service, True)
    original = service.workspace.complex_detail(first["registryId"])
    data = project_data()
    data["data"]["companyData"]["developerData"]["name"] = "Иное учебное имя застройщика"
    data["data"]["companyData"]["authorizedData"].update(
        bin="000000000001", name="Учебное имя роли получателя"
    )

    def response(request):
        if request.url.path.endswith("getobjects"):
            return httpx.Response(200, json={"data": {"objects": {"data": [{"id": 13}]}}})
        return httpx.Response(200, json=data)

    service.registry.client = RegistryClient(httpx.MockTransport(response))
    preview = service.preview("13")
    second = service.save(
        "13",
        SaveSourceProject(
            expected_version=0,
            expected_document_sha256=preview["project"]["documentSha256"],
            import_to_registry=True,
        ),
        USER,
    )
    card = service.workspace.complex_detail(second["registryId"])
    assert card["developer"]["name"] == "Иное учебное имя застройщика"
    assert card["authorizedCompany"]["name"] == "Учебное имя роли получателя"
    assert card["partySnapshots"][0]["source"]["url"].endswith("/13")
    assert service.workspace.complex_detail(first["registryId"]) == original


def test_signal_and_pdf_use_new_project_snapshot_without_changing_old_signal(service):
    from app.models.signals import SignalCreate
    from app.services.reports import report_html
    from app.services.signals import SignalService

    service.workspace.demo_only = False
    first = save(service, True)
    signals = SignalService(service.workspace)
    old = signals.create(
        SignalCreate(
            complex_id=first["registryId"],
            expected_complex_version=1,
            title="Учебная проверка исходников",
            reason="Synthetic QA only",
        ),
        USER,
    )
    data = project_data()
    data["data"]["companyData"]["developerData"]["name"] = "Иное учебное наименование"
    data["data"]["basicData"].update(
        act_number="QA-1",
        act_date="01.01.2020",
        act_registration_number="QA-2",
        act_registration_date="02.01.2020",
    )
    service.registry.client = RegistryClient(
        httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    )
    preview = service.preview("13")
    saved = service.save(
        "13",
        SaveSourceProject(
            expected_version=0,
            expected_document_sha256=preview["project"]["documentSha256"],
            import_to_registry=True,
        ),
        USER,
    )
    new = signals.create(
        SignalCreate(
            complex_id=saved["registryId"],
            expected_complex_version=1,
            title="Учебная проверка нового снимка",
            reason="Synthetic QA only",
        ),
        USER,
    )
    assert new.snapshot.developer.name == "Иное учебное наименование"
    assert new.snapshot.authorized_company.bin == "000000000002"
    html = report_html(new)
    assert "Иное учебное наименование" in html and "Уполномоченная компания" in html
    assert "DEMO — вымышленные данные" not in html and "вымышленный БИН" not in html
    assert (
        signals.workspace.require_record("signals", old.id)["snapshot"]["developer"]["name"]
        == old.snapshot.developer.name
    )
