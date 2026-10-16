from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import CurrentUser, get_runtime
from app.core.firebase import FirebaseRuntime
from app.models.ad_trace import AdLink, TraceDecision, TraceSave
from app.models.common import Identifier
from app.models.entities import Advertisement, Evidence
from app.models.risk import RiskResult, RiskZone, VerificationStatus
from app.repositories.firestore import FirestoreStore
from app.schemas.workspace import (
    AdvertisementCreate,
    ComplexCreate,
    EvidenceCreate,
    EvidenceReview,
    FactorDecision,
    LegalBasisUpdate,
)
from app.services.ad_links import AdLinksService
from app.services.risk import calculate_risk
from app.services.workspace import WorkspaceService

router = APIRouter(prefix="/api/v1", tags=["workspace"])
Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]


def workspace_service(
    request: Request, user: CurrentUser, runtime: Annotated[FirebaseRuntime, Depends(get_runtime)]
) -> WorkspaceService:
    # Authentication runs before opening a database connection.
    return WorkspaceService(
        FirestoreStore(runtime.db()), demo_only=request.app.state.settings.firebase_demo_only
    )


Workspace = Annotated[WorkspaceService, Depends(workspace_service)]


@router.get("/complexes")
def complexes(
    user: CurrentUser,
    service: Workspace,
    q: Annotated[str, Query(max_length=100)] = "",
    city: Annotated[str | None, Query(max_length=100)] = None,
    zone: RiskZone | None = None,
    sort: Literal["risk", "name"] = "risk",
    cursor: Annotated[int, Query(ge=0, le=500)] = 0,
    limit: Limit = 50,
) -> dict:
    return service.list_complexes(q=q, city=city, zone=zone, sort=sort, offset=cursor, limit=limit)


@router.get("/complexes/{record_id}")
def complex_detail(record_id: Identifier, user: CurrentUser, service: Workspace) -> dict:
    return service.complex_detail(record_id)


@router.get("/complexes/{record_id}/risk", response_model=RiskResult)
def complex_risk(record_id: Identifier, user: CurrentUser, service: Workspace) -> RiskResult:
    return calculate_risk(service.complex(record_id).factors)


@router.post("/complexes", status_code=201)
def create_complex(payload: ComplexCreate, user: CurrentUser, service: Workspace) -> dict:
    return service.create_complex(payload, user)


@router.patch("/complexes/{record_id}/legal-basis")
def update_basis(
    record_id: Identifier, payload: LegalBasisUpdate, user: CurrentUser, service: Workspace
) -> dict:
    return service.update_basis(record_id, payload, user)


@router.post("/complexes/{record_id}/factors/decision")
def factor_decision(
    record_id: Identifier, payload: FactorDecision, user: CurrentUser, service: Workspace
) -> dict:
    return service.factor_decision(record_id, payload, user)


@router.get("/developers")
def developers(
    user: CurrentUser, service: Workspace, cursor: Cursor = None, limit: Limit = 50
) -> dict:
    return service.page("developers", after_id=cursor, limit=limit)


@router.get("/advertisements")
def advertisements(
    user: CurrentUser, service: Workspace, cursor: Cursor = None, limit: Limit = 50
) -> dict:
    return service.page("advertisements", after_id=cursor, limit=limit)


@router.get("/complexes/{record_id}/advertisements")
def complex_advertisements(
    record_id: Identifier,
    user: CurrentUser,
    service: Workspace,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> dict:
    return service.page("advertisements", complex_id=record_id, after_id=cursor, limit=limit)


@router.post("/advertisements", response_model=Advertisement, status_code=201)
def create_advertisement(
    payload: AdvertisementCreate, user: CurrentUser, service: Workspace
) -> Advertisement:
    return service.create_advertisement(payload, user)


@router.get("/advertisements/{record_id}", response_model=Advertisement)
def advertisement_detail(
    record_id: Identifier, user: CurrentUser, service: Workspace
) -> Advertisement:
    return Advertisement.model_validate(service.require_record("advertisements", record_id))


@router.get("/complexes/{record_id}/evidence")
def evidence_list(
    record_id: Identifier,
    user: CurrentUser,
    service: Workspace,
    cursor: Cursor = None,
    limit: Limit = 50,
    status: VerificationStatus | None = None,
) -> dict:
    return service.page(
        "evidence",
        complex_id=record_id,
        after_id=cursor,
        limit=limit,
        extra_filters=[("status", "==", status)] if status else [],
    )


@router.get("/evidence/{record_id}", response_model=Evidence)
def evidence_detail(record_id: Identifier, user: CurrentUser, service: Workspace) -> Evidence:
    return Evidence.model_validate(service.require_record("evidence", record_id))


@router.post("/evidence", response_model=Evidence, status_code=201)
def create_evidence(payload: EvidenceCreate, user: CurrentUser, service: Workspace) -> Evidence:
    return service.create_evidence(payload, user)


@router.post("/evidence/{record_id}/decision", response_model=Evidence)
def review_evidence(
    record_id: Identifier, payload: EvidenceReview, user: CurrentUser, service: Workspace
) -> Evidence:
    return service.review_evidence(record_id, payload, user)


@router.get("/complexes/{record_id}/history")
def history(
    record_id: Identifier,
    user: CurrentUser,
    service: Workspace,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> dict:
    return service.page("auditLogs", complex_id=record_id, after_id=cursor, limit=limit)


@router.get("/advertisements/{record_id}/trace")
def advertisement_trace(record_id: Identifier, user: CurrentUser, service: Workspace) -> dict:
    return AdLinksService(service).candidates(record_id)


@router.post("/advertisements/{record_id}/trace", response_model=AdLink)
def propose_ad_link(
    record_id: Identifier, payload: TraceSave, user: CurrentUser, service: Workspace
) -> AdLink:
    return AdLinksService(service).save(record_id, payload, user)


@router.post("/ad-links/{record_id}/decision", response_model=AdLink)
def review_ad_link(
    record_id: Identifier, payload: TraceDecision, user: CurrentUser, service: Workspace
) -> AdLink:
    return AdLinksService(service).decide(record_id, payload, user)
