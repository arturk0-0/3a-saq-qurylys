"""Synthetic registry transports only. No live registry, AI or Firebase in tests."""

import csv
import io
from copy import deepcopy
from datetime import timedelta

import httpx
import pytest
from pydantic import ValidationError

from app.core.errors import AppError, Conflict
from app.models.common import utc_now
from app.models.monitoring import ItemBasisReview, ItemReview
from app.services.registries import RegistryClient
from tests.test_monitoring import USER, collect
from tests.test_monitoring import service as service_fixture


@pytest.fixture
def service():
    return service_fixture.__wrapped__()


def detail(**changes):
    basic = {
        "name": 'ЖК "Учебный берег", блок А',
        "authority": {"id": 1},
        "warranty_number": "SYNTHETIC-PERMIT-1",
        "issue_date": "01.01.2020",
        "region": {"id": 16},
        "address": "Риддер, вымышленный адрес, блок А",
    }
    basic.update(changes)
    return {
        "data": {
            "basicData": basic,
            "companyData": {
                "developerData": {
                    "name": "Учебный застройщик",
                    "bin": "000000000001",
                    "email": "never-return@example.test",
                },
                "authorizedData": {"name": "Учебный получатель", "bin": "000000000002"},
            },
        }
    }


def registry(response=None):
    return RegistryClient(
        httpx.MockTransport(lambda r: httpx.Response(200, json=response or detail()))
    )


def payload(item, **changes):
    values = dict(
        expected_version=item["version"],
        expected_document_sha256=registry().detail("12")["documentSha256"],
        record_id="12",
        advertisement_date=utc_now().date(),
        object_matches=True,
        phase_matches=True,
        holder_matches=True,
        document_validity_checked=True,
        advertisement_date_checked=True,
        other_risks_reviewed=True,
        notes="SYNTHETIC QA: документ/очередь/получатель и дата сверены",
    )
    values.update(changes)
    return ItemBasisReview(**values)


def test_home_detail_is_narrow_and_uses_fixed_endpoint():
    client = registry()
    row = client.detail("12")
    assert row["kind"] == "regional_permit" and row["reference"] == "SYNTHETIC-PERMIT-1"
    assert "email" not in str(row) and "never-return" not in str(row)
    assert len(row["responseSha256"]) == 64
    assert registry(detail(authority={"id": 2})).detail("12")["kind"] == "guarantee"


@pytest.mark.parametrize(
    "changes",
    [
        {"authority": {"id": 3}},
        {"warranty_number": ""},
        {"issue_date": "unknown"},
        {"region": {"id": 10}},
        {"address": "Семей, область Абай"},
    ],
)
def test_insufficient_or_other_territory_documents_never_confirm(changes):
    with pytest.raises(AppError) as error:
        registry(detail(**changes)).detail("12")
    assert error.value.code == "REGISTRY_RECORD_UNVERIFIABLE"


@pytest.mark.parametrize("value", ["../private", "https://internal.test", "12?secret=1", "0/12"])
def test_no_user_url_or_path_can_be_fetched(value):
    with pytest.raises(AppError):
        registry().detail(value)


def test_offline_or_schema_errors_are_not_a_negative_legal_finding():
    client = RegistryClient(
        httpx.MockTransport(lambda r: httpx.Response(503, text="provider-private"))
    )
    result = client.search("Учебный берег")
    assert all(row["status"] == "unavailable" for row in result["sources"])
    assert "provider-private" not in str(result)
    assert all(not row["candidates"] for row in result["sources"])
    assert (
        registry({"different": "schema"}).search("Учебный берег")["sources"][0]["status"]
        == "unavailable"
    )


def test_dataset_uses_actual_columns_and_keeps_snapshot_date_not_construction_deadline():
    out = io.StringIO()
    keys = [
        "id",
        "object_name",
        "builder_name",
        "auth_org_name",
        "address_name",
        "number",
        "sdu_load_date",
        "date_end",
    ]
    writer = csv.DictWriter(out, fieldnames=keys)
    writer.writeheader()
    for address in ["Риддер, вымышленный адрес", "Семей, Восточно-Казахстанская область"]:
        writer.writerow(
            dict(
                zip(
                    keys,
                    [
                        "1",
                        "Учебный берег Блок А",
                        "Учебная компания",
                        "Получатель",
                        address,
                        "SYNTHETIC-REF",
                        "2026-06-15",
                        "2027-01-01",
                    ],
                    strict=True,
                )
            )
        )
    client = RegistryClient(httpx.MockTransport(lambda r: httpx.Response(200, text=out.getvalue())))
    rows, limited = client.ashyq_search("Учебный берег")
    assert len(rows) == 1 and not limited and rows[0]["dataAsOf"] == "2026-06-15"
    assert "validUntil" not in rows[0] and "confirmed" not in str(rows[0])


def test_results_remain_candidates_and_empty_catalog_is_not_illegal():
    catalog = {"data": {"objects": {"data": [], "next_page_url": None}}}
    result = registry(catalog).search("Учебный берег")
    assert result["sources"][0]["status"] == "ok"
    assert result["sources"][0]["candidates"] == []
    assert "R1" not in str(result)


def test_authority_record_needs_valid_provenance_fields():
    broken = detail()
    broken["data"]["companyData"]["authorizedData"]["bin"] = "not-a-bin"
    with pytest.raises(AppError):
        registry(broken).detail("12")


def test_confirmation_archives_only_this_finding_and_keeps_risk_and_audit(service):
    before = deepcopy(service.store.documents.get("complexes"))
    _, _, item = collect(service)
    service.registry = registry()
    review = service.confirm_basis(item["id"], payload(item), USER)
    assert review.status == "dismissed" and review.basis_review.document.kind == "regional_permit"
    assert not service.items("active")["items"]
    assert len(service.items()["items"]) == 1
    assert service.store.documents["complexes"] == before
    history = service.history(item["id"])["items"]
    assert history[0]["action"] == "item.basis.confirm"
    assert history[0]["actorUid"] == USER.uid
    assert history[0]["details"]["document"]["reference"] == "SYNTHETIC-PERMIT-1"
    reopened = service.review(
        item["id"],
        ItemReview(
            expected_version=review.version,
            decision="investigating",
            notes="SYNTHETIC QA: повторная проверка",
        ),
        USER,
    )
    assert reopened.basis_review is None
    assert len(service.items("active")["items"]) == 1
    assert any(e["action"] == "item.basis.confirm" for e in service.history(item["id"])["items"])


@pytest.mark.parametrize(
    "check",
    [
        "object_matches",
        "phase_matches",
        "holder_matches",
        "document_validity_checked",
        "advertisement_date_checked",
        "other_risks_reviewed",
    ],
)
def test_scope_and_other_risks_must_be_explicitly_checked(check):
    with pytest.raises(ValidationError):
        payload({"version": 1}, **{check: False})


def test_late_permit_does_not_clear_earlier_advertisement(service):
    _, _, item = collect(service)
    service.registry = registry(
        detail(issue_date=(utc_now() + timedelta(days=1)).strftime("%d.%m.%Y"))
    )
    with pytest.raises(AppError) as error:
        service.confirm_basis(
            item["id"],
            payload(item, expected_document_sha256=service.registry.detail("12")["documentSha256"]),
            USER,
        )
    assert error.value.code == "REGISTRY_DOCUMENT_TOO_RECENT"
    assert service.item(item["id"]).basis_review is None


def test_unknown_published_date_requires_human_date_and_future_is_rejected(service):
    _, _, item = collect(service)
    service.registry = registry()
    with pytest.raises(AppError) as error:
        service.confirm_basis(
            item["id"], payload(item, advertisement_date=utc_now().date() + timedelta(days=1)), USER
        )
    assert error.value.code == "REGISTRY_DATE_MISMATCH"


def test_stale_and_concurrent_review_preserve_existing_decisions(service):
    _, _, item = collect(service)
    calls = []

    def response(request):
        calls.append(request)
        service.review(
            item["id"],
            ItemReview(expected_version=1, decision="investigating", notes="Another expert"),
            USER,
        )
        return httpx.Response(200, json=detail())

    service.registry = RegistryClient(httpx.MockTransport(response))
    with pytest.raises(Conflict):
        service.confirm_basis(item["id"], payload(item), USER)
    assert service.item(item["id"]).notes == "Another expert"
    with pytest.raises(Conflict):
        service.confirm_basis(item["id"], payload(item), USER)
    assert len(calls) == 1


def test_daily_limits_stop_reads_before_provider_request(service):
    _, _, item = collect(service)
    key = f"registry-{utc_now():%Y%m%d}"
    service.store.documents["monitorLimits"][key] = {"id": key, "count": 100}
    with pytest.raises(AppError) as error:
        service.registry_search(item["id"], "Учебный берег")
    assert error.value.code == "REGISTRY_LIMIT"


def test_bounded_body_and_redirect_are_not_followed():
    for response in [
        httpx.Response(302, headers={"Location": "http://127.0.0.1/private"}),
        httpx.Response(200, content=b"x" * 2_000_001),
    ]:
        with pytest.raises(AppError):
            RegistryClient(httpx.MockTransport(lambda r, response=response: response)).detail("12")


def test_home_catalog_limits_candidates_and_never_follows_pagination_url():
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "objects": {
                        "data": [
                            {
                                "id": 12,
                                "name": "Учебный берег",
                                "region": {"ru": "Восточно-Казахстанская область"},
                                "address": "Риддер, учебный адрес",
                                "developerName": "Учебная компания",
                            }
                        ],
                        "next_page_url": "http://127.0.0.1/private",
                    }
                }
            },
        )

    rows, limited = RegistryClient(httpx.MockTransport(provider)).home_search("Учебный берег")
    assert len(rows) == 1 and limited and len(calls) == 1
    assert rows[0]["sourceUrl"] == "https://homeportal.kz/ru/projects/12"
    assert rows[0]["reference"] == "" and "confirmed" not in str(rows)


def test_bin_must_not_be_truncated_into_a_different_valid_identifier():
    broken = detail()
    broken["data"]["companyData"]["authorizedData"]["bin"] = "0000000000029"
    with pytest.raises(AppError):
        registry(broken).detail("12")


def test_known_publication_date_cannot_be_substituted_with_campaign_date(service):
    _, _, item = collect(service)
    service.store.documents["monitorItems"][item["id"]]["publishedAt"] = "2020-01-01T12:00:00Z"
    service.registry = registry()
    with pytest.raises(AppError) as error:
        service.confirm_basis(item["id"], payload(item), USER)
    assert error.value.code == "REGISTRY_DATE_MISMATCH"


def test_attached_or_running_item_cannot_be_archived_using_basis(service):
    _, _, item = collect(service)
    service.registry = registry()
    for change in [
        {"advertisementId": "linked-ad"},
        {"advertisementId": None, "aiStatus": "running"},
    ]:
        service.store.documents["monitorItems"][item["id"]].update(change)
        with pytest.raises(Conflict):
            service.confirm_basis(item["id"], payload(item), USER)


def test_document_change_after_view_requires_new_scope_review(service):
    _, _, item = collect(service)
    service.registry = registry(detail(warranty_number="SYNTHETIC-CHANGED"))
    with pytest.raises(AppError) as error:
        service.confirm_basis(item["id"], payload(item), USER)
    assert error.value.code == "REGISTRY_DOCUMENT_CHANGED"
    assert service.item(item["id"]).basis_review is None
    assert service.item(item["id"]).status == "new"


def test_document_fingerprint_ignores_fetch_time_and_unrelated_contacts():
    original = registry().detail("12")
    response = detail()
    response["data"]["companyData"]["developerData"]["email"] = "changed@example.test"
    fresh = registry(response).detail("12")
    assert original["documentSha256"] == fresh["documentSha256"]
    assert original["responseSha256"] != fresh["responseSha256"]


def test_archived_duplicates_do_not_trigger_automatic_ai(service):
    from tests.test_monitoring import due, use_ai

    source, _, item = collect(service)
    service.registry = registry()
    service.confirm_basis(item["id"], payload(item), USER)
    service.store.documents["monitorSources"][source["id"]]["autoAnalyze"] = True
    due(service, source)
    calls = use_ai(service)
    assert service.run(source["id"], USER)["duplicates"] == 1
    assert calls == []
    assert service.item(item["id"]).basis_review is not None
