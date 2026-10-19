from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import CurrentUser
from app.api.workspace import Cursor, Limit, Workspace
from app.models.common import Identifier
from app.models.companies import RefreshCompany, SaveSourceProject
from app.services.companies import CompanyService

router = APIRouter(prefix="/api/v1", tags=["companies"])


def company_service(workspace: Workspace):
    return CompanyService(workspace)


Companies = Annotated[CompanyService, Depends(company_service)]


@router.get("/companies")
def companies(user: CurrentUser, service: Companies, cursor: Cursor = None, limit: Limit = 20):
    return service.list(cursor, limit)


@router.get("/companies/{record_id}")
def company(record_id: Identifier, user: CurrentUser, service: Companies):
    return service.get(record_id)


@router.post("/companies/{record_id}/refresh")
def refresh(record_id: Identifier, payload: RefreshCompany, user: CurrentUser, service: Companies):
    return service.refresh(record_id, payload, user)


@router.get("/company-projects/search")
def search(
    user: CurrentUser, service: Companies, q: Annotated[str, Query(min_length=3, max_length=100)]
):
    return service.search(q)


@router.get("/company-projects/{record_id}")
def preview(record_id: Identifier, user: CurrentUser, service: Companies):
    return service.preview(record_id)


@router.post("/company-projects/{record_id}")
def save(record_id: Identifier, payload: SaveSourceProject, user: CurrentUser, service: Companies):
    return service.save(record_id, payload, user)
