from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import CurrentUser
from app.api.workspace import Cursor, Limit, Workspace
from app.models.common import Identifier
from app.models.monitoring import (
    ItemAnalyze,
    ItemAttach,
    ItemBasisReview,
    ItemReview,
    SourceInput,
    SourceUpdate,
)
from app.services.monitoring import MonitoringService
from app.services.workspace import serialize

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


def monitoring_service(request: Request, workspace: Workspace):
    return MonitoringService(workspace, request.app.state.settings)


Monitor = Annotated[MonitoringService, Depends(monitoring_service)]


@router.get("/status")
def status(user: CurrentUser, service: Monitor):
    return service.status()


@router.get("/sources")
def sources(user: CurrentUser, service: Monitor):
    return service.sources()


@router.post("/sources", status_code=201)
def create_source(payload: SourceInput, user: CurrentUser, service: Monitor):
    return service.create_source(payload, user)


@router.patch("/sources/{record_id}")
def update_source(
    record_id: Identifier, payload: SourceUpdate, user: CurrentUser, service: Monitor
):
    return service.update_source(record_id, payload, user)


@router.post("/sources/{record_id}/run")
def run(record_id: Identifier, user: CurrentUser, service: Monitor):
    return service.run(record_id, user)


@router.get("/items")
def items(
    user: CurrentUser,
    service: Monitor,
    cursor: Cursor = None,
    limit: Limit = 30,
    status: Literal["active", "new", "investigating", "dismissed"] | None = None,
):
    return service.items(status, cursor, limit)


@router.get("/items/{record_id}")
def item(record_id: Identifier, user: CurrentUser, service: Monitor):
    return serialize(service.item(record_id))


@router.post("/items/{record_id}/review")
def review(record_id: Identifier, payload: ItemReview, user: CurrentUser, service: Monitor):
    return serialize(service.review(record_id, payload, user))


@router.get("/items/{record_id}/history")
def item_history(
    record_id: Identifier,
    user: CurrentUser,
    service: Monitor,
    cursor: Cursor = None,
    limit: Limit = 20,
):
    return service.history(record_id, cursor, limit)


@router.post("/items/{record_id}/analyze")
def analyze(record_id: Identifier, payload: ItemAnalyze, user: CurrentUser, service: Monitor):
    return serialize(service.analyze(record_id, payload, user))


@router.post("/items/{record_id}/attach")
def attach(record_id: Identifier, payload: ItemAttach, user: CurrentUser, service: Monitor):
    return service.attach(record_id, payload, user)


@router.get("/runs")
def runs(user: CurrentUser, service: Monitor, cursor: Cursor = None, limit: Limit = 20):
    return service.runs(cursor, limit)


@router.get("/items/{record_id}/registry")
def registry_search(
    record_id: Identifier,
    user: CurrentUser,
    service: Monitor,
    q: Annotated[str, Query(min_length=3, max_length=100)],
):
    return service.registry_search(record_id, q)


@router.get("/items/{record_id}/registry/{registry_id}")
def registry_detail(
    record_id: Identifier, registry_id: Identifier, user: CurrentUser, service: Monitor
):
    return service.registry_detail(record_id, registry_id)


@router.post("/items/{record_id}/basis-review")
def confirm_basis(
    record_id: Identifier, payload: ItemBasisReview, user: CurrentUser, service: Monitor
):
    return serialize(service.confirm_basis(record_id, payload, user))
