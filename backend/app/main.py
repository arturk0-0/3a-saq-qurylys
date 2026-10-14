import logging
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.responses import Response

from app.api.router import router
from app.core.config import Settings
from app.schemas.errors import ErrorResponse

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    application = FastAPI(title="SAQ QURYLYS API", version="0.1.0")
    application.include_router(router)

    def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid4()))
        body = ErrorResponse(code=code, message=message, requestId=request_id)
        return JSONResponse(
            status_code=status,
            content=body.model_dump(),
            headers={"X-Request-ID": request_id},
        )

    @application.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(request, exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail))

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
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )
    return application


app = create_app()
