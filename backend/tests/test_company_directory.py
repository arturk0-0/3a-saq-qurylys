"""Synthetic public HTML graphs only; no network or personal records."""

import json

import httpx
import pytest

from app.core.errors import AppError
from app.models.companies import RefreshCompany
from app.services.company_directory import CompanyDirectory
from app.services.registries import RegistryClient
from tests.test_companies import save
from tests.test_companies import service as service_fixture
from tests.test_monitoring import USER


def page(bin_="000000000001", date="01-02-2010 (16 лет 8 месяцев)"):
    nodes = [{"bin": 1, "reg_date": 2, "director_name": 3}, bin_, date, "DO NOT COLLECT"]
    return '<script type="application/json" id="__NUXT_DATA__">' + json.dumps(nodes) + "</script>"


def test_bin_matched_registration_date_only_and_fixed_public_url():
    def transport(request):
        assert str(request.url) == "https://pk.adata.kz/company/000000000001"
        return httpx.Response(200, text=page())

    fact = CompanyDirectory(RegistryClient(httpx.MockTransport(transport))).registration(
        "000000000001"
    )
    assert fact.value == "2010-02-01" and fact.field == "registrationDate"
    assert fact.source.publisher == "ADATA · открытый справочник"
    assert fact.source.effective_date is None  # The registration date is not source freshness.
    assert "DO NOT COLLECT" not in fact.model_dump_json()


@pytest.mark.parametrize(
    "html",
    [
        page(bin_="000000000002"),
        page(date="01-01-2099"),
        page(date="not a date"),
        page(date="31-02-2010"),
        '<script id="__NUXT_DATA__">[]</script>',
        '<script id="__NUXT_DATA__">not JSON</script>',
        '<script id="__NUXT_DATA__">[{"bin":-1,"reg_date":-1}]</script>',
        '<script id="__NUXT_DATA__">[{"bin":1,"reg_date":2},["Ref",1],["Ref",2]]</script>',
        (
            '<script id="__NUXT_DATA__">[{"bin":1,"reg_date":2},'
            '"000000000001","01-01-2010",{"bin":1,"reg_date":4},"02-01-2010"]</script>'
        ),
    ],
)
def test_unmatched_malformed_future_or_unresolved_dates_stay_unknown(html):
    directory = CompanyDirectory(
        RegistryClient(httpx.MockTransport(lambda r: httpx.Response(200, text=html)))
    )
    with pytest.raises(AppError) as error:
        directory.registration("000000000001")
    assert error.value.code == "COMPANY_DIRECTORY_UNAVAILABLE"


def test_secondary_unavailable_retains_cached_registration_and_other_sources():
    service = service_fixture.__wrapped__()
    original = service.registry.client.transport

    def response(request):
        if request.url.host == "pk.adata.kz":
            return httpx.Response(200, text=page(bin_=request.url.path.rsplit("/", 1)[1]))
        return original.handle_request(request)

    service.registry.client.transport = httpx.MockTransport(response)
    result = save(service)
    before = service.get(result["companyIds"][0])
    registration = next(f for f in before["facts"] if f["field"] == "registrationDate")
    service.registry.client.transport = original
    after = service.refresh(before["id"], RefreshCompany(expected_version=before["version"]), USER)
    assert registration in after["facts"]
    assert after["lastError"] == "COMPANY_DIRECTORY_UNAVAILABLE"
    assert after["projects"] and after["version"] == before["version"] + 1


def test_bad_bin_and_redirect_never_fetch_arbitrary_or_redirect_target():
    requests = []

    def response(request):
        requests.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    directory = CompanyDirectory(RegistryClient(httpx.MockTransport(response)))
    with pytest.raises(AppError):
        directory.registration("../../secret")
    assert not requests
    with pytest.raises(AppError):
        directory.registration("000000000001")
    assert requests == ["https://pk.adata.kz/company/000000000001"]
