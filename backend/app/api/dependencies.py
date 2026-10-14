from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import AppError
from app.core.firebase import FirebaseRuntime
from app.models.auth import Principal

bearer = HTTPBearer(auto_error=False)


def get_runtime(request: Request) -> FirebaseRuntime:
    return request.app.state.firebase


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    runtime: Annotated[FirebaseRuntime, Depends(get_runtime)],
) -> Principal:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise AppError(401, "AUTH_REQUIRED", "Sign in to continue")
    if len(credentials.credentials) > 8192:
        raise AppError(401, "INVALID_TOKEN", "Sign in again")
    return runtime.verify_token(credentials.credentials)


CurrentUser = Annotated[Principal, Depends(current_user)]


def admin_user(user: CurrentUser) -> Principal:
    if user.role != "admin":
        raise AppError(403, "ADMIN_REQUIRED", "Admin role is required")
    return user


AdminUser = Annotated[Principal, Depends(admin_user)]
