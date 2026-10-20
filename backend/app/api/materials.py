from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request

from app.api.analysis import Files
from app.api.dependencies import CurrentUser
from app.api.workspace import Workspace
from app.models.common import Identifier
from app.models.materials import MaterialRetry, MaterialReview
from app.services.files import FileService, FirebaseFileStorage
from app.services.gemini import GeminiClient
from app.services.material_analysis import MaterialProcessor
from app.services.materials import MaterialService

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])


def material_service(workspace: Workspace, files: Files):
    return MaterialService(workspace, files)


Materials = Annotated[MaterialService, Depends(material_service)]
MaterialCursor = Annotated[str | None, Query(max_length=1024, pattern=r"^[A-Za-z0-9_-]+$")]


def schedule_analysis(
    background, request, workspace, files=None, *, material_id=None, advertisement_id=None
):
    settings = request.app.state.settings
    client = getattr(request.app.state, "material_client", None) or GeminiClient(settings)
    files = (
        files
        or getattr(request.app.state, "material_files", None)
        or FileService(workspace, FirebaseFileStorage(request.app.state.firebase))
    )
    if advertisement_id:
        from app.services.material_projection import digest

        link = workspace.store.get(
            "materialLinks", digest(f"legacy:advertisement:{advertisement_id}")
        )
        material_id = link["materialId"] if link else None
    processor = MaterialProcessor(workspace, client, files, settings)
    # New input creates durable jobs in the SAME commit as the original record.
    # Background execution is an optimization; the existing worker drains leftovers.
    from app.models.auth import Principal

    def run():
        try:
            processor.process(
                Principal(uid="service-material-worker", role="analyst"), 1, material_id
            )
        except Exception:
            import logging

            logging.getLogger(__name__).error(
                "Material background worker interrupted; durable jobs retained"
            )

    background.add_task(run)


@router.get("")
def items(
    user: CurrentUser,
    service: Materials,
    q: Annotated[str, Query(max_length=100)] = "",
    review: Literal["all", "needs_review", "reviewed", "dismissed"] = "all",
    origin: Literal["all", "automatic", "manual"] = "all",
    platform: Annotated[str | None, Query(max_length=500)] = None,
    complexId: Identifier | None = None,
    sort: Literal["priority", "recent"] = "priority",
    cursor: MaterialCursor = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 30,
):
    return service.items(
        q=q,
        review=review,
        origin=origin,
        platform=platform,
        complex_id=complexId,
        sort=sort,
        cursor=cursor,
        limit=limit,
    )


@router.get("/{record_id}")
def detail(record_id: Identifier, user: CurrentUser, service: Materials):
    return service.detail(record_id)


@router.get("/{record_id}/occurrences")
def occurrences(
    record_id: Identifier,
    user: CurrentUser,
    service: Materials,
    cursor: MaterialCursor = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return service.occurrences(record_id, cursor, limit)


@router.post("/{record_id}/review")
def review(record_id: Identifier, payload: MaterialReview, user: CurrentUser, service: Materials):
    return service.review(record_id, payload, user)


@router.post("/{record_id}/retry-analysis")
def retry(
    record_id: Identifier,
    payload: MaterialRetry,
    user: CurrentUser,
    service: Materials,
    background: BackgroundTasks,
    request: Request,
):
    result = service.retry(record_id, payload, user)
    schedule_analysis(background, request, service.workspace, material_id=record_id)
    return result


@router.get("/{record_id}/occurrences/{occurrence_id}")
def occurrence(
    record_id: Identifier, occurrence_id: Identifier, user: CurrentUser, service: Materials
):
    return service.occurrence(record_id, occurrence_id)


@router.get("/{record_id}/history")
def history(
    record_id: Identifier,
    user: CurrentUser,
    service: Materials,
    cursor: MaterialCursor = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return service.history(record_id, cursor, limit)
