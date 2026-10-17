import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.responses import Response

from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.router import router
from app.api.signals import router as signals_router
from app.api.workspace import router as workspace_router
from app.core.config import Settings
from app.core.errors import AppError
from app.core.firebase import FirebaseRuntime
from app.core.request_context import request_id_context
from app.schemas.errors import ErrorResponse

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    runtime = FirebaseRuntime(settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        yield
        runtime.close()

    application = FastAPI(title="SAQ QURYLYS API", version="0.2.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.firebase = runtime
    application.include_router(router)
    application.include_router(auth_router)
    application.include_router(workspace_router)
    application.include_router(analysis_router)
    application.include_router(signals_router)

    def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid4()))
        body = ErrorResponse(code=code, message=message, requestId=request_id)
        return JSONResponse(
            status_code=status,
            content=body.model_dump(),
            headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
        )

    @application.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        token = request_id_context.set(request.state.request_id)
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                # Keep private exception text out of the ASGI server traceback.
                response = await unexpected_error(request, exc)
            response.headers["X-Request-ID"] = request.state.request_id
            if request.url.path.startswith("/api/v1/"):
                response.headers["Cache-Control"] = "no-store"
            return response
        finally:
            request_id_context.reset(token)

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        response = error_response(
            request, exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail)
        )
        response.headers.update(exc.headers or {})
        return response

    @application.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500 or exc.status_code == 429:
            logger.warning(
                "Request failed: request_id=%s code=%s",
                getattr(request.state, "request_id", "unknown"),
                exc.code,
            )
        response = error_response(request, exc.status_code, exc.code, exc.message)
        if exc.status_code == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not echo submitted values, which may contain secrets.
        return error_response(request, 422, "VALIDATION_ERROR", "Invalid request")

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled request failure: request_id=%s exception_type=%s",
            getattr(request.state, "request_id", "unknown"),
            type(exc).__name__,
        )
        return error_response(request, 500, "INTERNAL_ERROR", "Internal server error")

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["X-Request-ID"],
    )
    return application


app = create_app()
