from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import CurrentUser, get_runtime
from app.api.workspace import Cursor, Limit, Workspace
from app.core.errors import AppError
from app.core.firebase import FirebaseRuntime
from app.models.analysis import AnalysisRequest, HypothesisDecision
from app.models.common import Identifier
from app.schemas.matching import MatchingCandidates
from app.services.analysis import AnalysisService
from app.services.files import MAX_UPLOAD, FileService, FirebaseFileStorage
from app.services.gemini import GeminiClient
from app.services.matching import match_candidates

router = APIRouter(prefix="/api/v1", tags=["analysis"])


def file_service(
    workspace: Workspace, runtime: Annotated[FirebaseRuntime, Depends(get_runtime)]
) -> FileService:
    return FileService(workspace, FirebaseFileStorage(runtime))


Files = Annotated[FileService, Depends(file_service)]


def analysis_service(request: Request, workspace: Workspace, files: Files) -> AnalysisService:
    settings = request.app.state.settings
    return AnalysisService(workspace, GeminiClient(settings), files, settings)


Analysis = Annotated[AnalysisService, Depends(analysis_service)]


@router.post("/advertisements/{record_id}/analyze")
def analyze(record_id: Identifier, payload: AnalysisRequest, user: CurrentUser, service: Analysis):
    return service.analyze(record_id, payload, user)


@router.get("/advertisements/{record_id}/analysis")
def runs(
    record_id: Identifier,
    user: CurrentUser,
    workspace: Workspace,
    cursor: Cursor = None,
    limit: Limit = 50,
):
    workspace.require_record("advertisements", record_id)
    return workspace.page(
        "analysisRuns",
        after_id=cursor,
        limit=limit,
        extra_filters=[("advertisementId", "==", record_id)],
    )


@router.get("/advertisements/{record_id}/hypotheses")
def hypotheses(
    record_id: Identifier,
    user: CurrentUser,
    workspace: Workspace,
    cursor: Cursor = None,
    limit: Limit = 50,
):
    workspace.require_record("advertisements", record_id)
    return workspace.page(
        "aiHypotheses",
        after_id=cursor,
        limit=limit,
        extra_filters=[("advertisementId", "==", record_id)],
    )


@router.get("/advertisements/{record_id}/matching-candidates", response_model=MatchingCandidates)
def matching_candidates(
    record_id: Identifier,
    run_id: Identifier,
    user: CurrentUser,
    workspace: Workspace,
):
    return match_candidates(workspace, record_id, run_id)


@router.post("/hypotheses/{record_id}/decision")
def review(
    record_id: Identifier, payload: HypothesisDecision, user: CurrentUser, service: Analysis
):
    return service.review(record_id, payload, user)


@router.post("/advertisements/{record_id}/screenshots", status_code=201)
async def screenshot(
    record_id: Identifier,
    request: Request,
    background: BackgroundTasks,
    user: CurrentUser,
    files: Files,
    expected_version: Annotated[int, Query(ge=1)],
):
    # Stream a raw image; multipart parsing must not buffer unbounded request bodies.
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_UPLOAD:
            raise AppError(413, "FILE_SIZE", "Image exceeds 6 MiB")
        data.extend(chunk)
    result = await run_in_threadpool(
        files.upload,
        record_id,
        expected_version,
        bytes(data),
        request.headers.get("content-type", ""),
        user,
    )
    from app.api.materials import schedule_analysis

    schedule_analysis(background, request, files.workspace, files, advertisement_id=record_id)
    return result


@router.get("/evidence/{record_id}/file")
def download(record_id: Identifier, user: CurrentUser, files: Files):
    data, media_type = files.download(record_id)
    return Response(
        data,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="{record_id}.{media_type.split("/")[1]}"',
        },
    )
