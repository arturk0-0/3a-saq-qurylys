from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.api.analysis import Files
from app.api.dependencies import CurrentUser
from app.api.workspace import Cursor, Limit, Workspace
from app.core.errors import AppError
from app.models.common import Identifier
from app.models.drone import (
    DEFAULT_CHECKLIST,
    AnalyzeInspection,
    CreateInspection,
    ReviewInspection,
)
from app.services.drone import DroneService
from app.services.drone_gemini import DroneGeminiClient
from app.services.files import MAX_UPLOAD
from app.services.workspace import serialize

router = APIRouter(prefix="/api/v1/drone-inspections", tags=["drone"])


def drone_service(request: Request, workspace: Workspace, files: Files) -> DroneService:
    settings = request.app.state.settings
    return DroneService(workspace, files.storage, DroneGeminiClient(settings), settings)


Drone = Annotated[DroneService, Depends(drone_service)]


@router.get("/checklist")
def checklist(user: CurrentUser):
    return {"items": [serialize(c) for c in DEFAULT_CHECKLIST], "version": "visual-starter-v1"}


@router.get("")
def inspections(user: CurrentUser, service: Drone, cursor: Cursor = None, limit: Limit = 20):
    return service.list(cursor, limit)


@router.post("", status_code=201)
def create(payload: CreateInspection, user: CurrentUser, service: Drone):
    return service.create(payload, user)


@router.get("/{record_id}")
def detail(record_id: Identifier, user: CurrentUser, service: Drone):
    return service.get(record_id)


@router.post("/{record_id}/photo", status_code=201)
async def upload(
    record_id: Identifier,
    request: Request,
    user: CurrentUser,
    service: Drone,
    expected_version: Annotated[int, Query(ge=1)],
):
    # Verify access before buffering the body or touching private storage.
    await run_in_threadpool(service.require, record_id)
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_UPLOAD:
            raise AppError(413, "FILE_SIZE", "Photo exceeds 6 MiB")
        data.extend(chunk)
    return await run_in_threadpool(
        service.upload,
        record_id,
        expected_version,
        bytes(data),
        request.headers.get("content-type", ""),
        user,
    )


@router.get("/{record_id}/photo")
def photo(record_id: Identifier, user: CurrentUser, service: Drone):
    data, media_type = service.download(record_id)
    filename = f"drone-{record_id}.{media_type.split('/')[1]}"
    return Response(
        data,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post("/{record_id}/analyze")
def analyze(record_id: Identifier, payload: AnalyzeInspection, user: CurrentUser, service: Drone):
    return service.analyze(record_id, payload, user)


@router.post("/{record_id}/review")
def review(record_id: Identifier, payload: ReviewInspection, user: CurrentUser, service: Drone):
    return service.review(record_id, payload, user)


@router.get("/{record_id}/runs")
def runs(
    record_id: Identifier,
    user: CurrentUser,
    service: Drone,
    cursor: Cursor = None,
    limit: Limit = 20,
):
    return service.runs(record_id, cursor, limit)
