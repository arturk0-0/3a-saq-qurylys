from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, Response

from app.api.dependencies import CurrentUser
from app.api.workspace import Cursor, Limit, Workspace
from app.models.common import Identifier
from app.models.signals import Signal, SignalCreate, SignalDecision
from app.services.reports import render_pdf, report_html
from app.services.signals import SignalService

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


def signal_service(workspace: Workspace) -> SignalService:
    return SignalService(workspace)


Signals = Annotated[SignalService, Depends(signal_service)]


@router.get("")
def list_signals(
    user: CurrentUser,
    workspace: Workspace,
    cursor: Cursor = None,
    limit: Limit = 50,
    status: Literal["draft", "pending_review", "confirmed", "returned"] | None = None,
):
    page = workspace.page(
        "signals",
        after_id=cursor,
        limit=limit,
        extra_filters=[("status", "==", status)] if status else [],
    )
    # Keep list responses bounded; full snapshots are available in detail.
    page["items"] = [
        {k: v for k, v in row.items() if k != "snapshot"}
        | {"complexName": row["snapshot"]["complex"]["name"], "risk": row["snapshot"]["risk"]}
        for row in page["items"]
    ]
    return page


@router.post("", response_model=Signal, status_code=201)
def create(payload: SignalCreate, user: CurrentUser, service: Signals):
    return service.create(payload, user)


@router.get("/{record_id}", response_model=Signal)
def detail(record_id: Identifier, user: CurrentUser, service: Signals):
    return service.get(record_id)


@router.post("/{record_id}/decision", response_model=Signal)
def decide(record_id: Identifier, payload: SignalDecision, user: CurrentUser, service: Signals):
    return service.decision(record_id, payload, user)


@router.get("/{record_id}/revisions/{version}", response_model=Signal)
def revision(record_id: Identifier, version: int, user: CurrentUser, workspace: Workspace):
    workspace.require_record("signals", record_id)
    return workspace.require_record("signalRevisions", f"{record_id}-{version}")


@router.get("/{record_id}/history")
def history(
    record_id: Identifier,
    user: CurrentUser,
    workspace: Workspace,
    cursor: Cursor = None,
    limit: Limit = 50,
):
    workspace.require_record("signals", record_id)
    return workspace.page(
        "auditLogs", after_id=cursor, limit=limit, extra_filters=[("entityId", "==", record_id)]
    )


@router.get("/{record_id}/report")
def report(
    record_id: Identifier,
    user: CurrentUser,
    service: Signals,
    format: Annotated[Literal["pdf", "html"], Query()] = "pdf",
):
    signal = service.get(record_id)
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if format == "html":
        headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; sandbox"
        )
        headers["Content-Disposition"] = f'attachment; filename="signal-{record_id}.html"'
        return HTMLResponse(report_html(signal), headers=headers)
    headers["Content-Disposition"] = f'attachment; filename="signal-{record_id}.pdf"'
    return Response(render_pdf(signal), media_type="application/pdf", headers=headers)
