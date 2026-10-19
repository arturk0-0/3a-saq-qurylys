"""Opt-in local company QA. Synthetic HTTP responses, memory data, test identity."""

import json

import httpx
from app.api.companies import company_service
from app.services.companies import CompanyService
from app.services.company_sources import CompanyRegistry
from app.services.registries import RegistryClient
from local_api import app, workspace
from tests.test_companies import project_data
from tests.test_company_directory import page

# ONLY this isolated QA process permits creating synthetic records with demo=False
# to exercise the live-scope contract. No Firebase credentials/clients are present.
workspace.demo_only = False


def response(request):
    if request.url.host == "pk.adata.kz":
        return httpx.Response(200, text=page(bin_=request.url.path.rsplit("/", 1)[1]))
    if request.url.host != "api.homeportal.kz":
        raise AssertionError("Unexpected external provider in local company QA")
    data = project_data()
    data["data"]["basicData"]["name"] = "Учебный берег · LOCAL QA"
    if request.url.path.endswith("getobjects"):
        return httpx.Response(
            200,
            json={
                "data": {
                    "objects": {
                        "data": [
                            {
                                "id": 12,
                                "name": "Учебный берег · LOCAL QA",
                                "address": "Учебный адрес, Усть-Каменогорск",
                                "region": {"ru": "Восточно-Казахстанская область"},
                            }
                        ],
                        "next_page_url": None,
                    }
                }
            },
        )
    return httpx.Response(200, content=json.dumps(data).encode())


service = CompanyService(
    workspace, CompanyRegistry(RegistryClient(httpx.MockTransport(response)))
)
app.dependency_overrides[company_service] = lambda: service
