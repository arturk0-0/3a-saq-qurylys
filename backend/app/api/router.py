from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Process health only; external integrations are not checked."""
    return HealthResponse()
