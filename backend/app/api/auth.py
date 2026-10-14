from fastapi import APIRouter

from app.api.dependencies import CurrentUser
from app.models.auth import Principal

router = APIRouter(prefix="/api/v1", tags=["identity"])


@router.get("/me", response_model=Principal)
def me(user: CurrentUser) -> Principal:
    return user
