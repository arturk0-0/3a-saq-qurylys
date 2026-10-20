"""Separate local-only entry point. The production app never imports this package."""

import os
import secrets
import time
from pathlib import Path
from threading import RLock

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.analysis import analysis_service, file_service
from app.api.companies import company_service
from app.api.dependencies import get_runtime
from app.api.drone import drone_service
from app.api.monitoring import monitoring_service
from app.api.workspace import workspace_service
from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.models.auth import Principal
from app.models.monitoring import SourceInput
from app.services.analysis import AnalysisService
from app.services.companies import CompanyService
from app.services.company_sources import CompanyRegistry
from app.services.drone import DroneService
from app.services.files import FileService
from app.services.monitoring import MonitoringService
from app.services.registries import RegistryClient
from app.services.workspace import WorkspaceService
from local_demo.providers import LocalAnalysis, LocalCollector, LocalDrone
from local_demo.seed import local_seed
from local_demo.storage import LocalFiles, LocalStore

EMAIL = "analyst@example.test"
PASSWORD = "demo-demo"
USER = Principal(
    uid="local-demo-analyst", role="analyst", email=EMAIL, display_name="Аналитик DEMO"
)


class LocalIdentity:
    def __init__(self):
        self.sessions = {}
        self.lock = RLock()

    def login(self, email, password):
        if email != EMAIL or not secrets.compare_digest(password, PASSWORD):
            raise AppError(401, "INVALID_TOKEN", "Use the documented local demo account")
        with self.lock:
            now = time.monotonic()
            self.sessions = {k: v for k, v in self.sessions.items() if v > now}
            if len(self.sessions) >= 100:
                raise AppError(429, "DEMO_SESSION_LIMIT", "Too many local sessions")
            token = secrets.token_urlsafe(32)
            self.sessions[token] = now + 8 * 60 * 60
            return token

    def verify_token(self, token):
        with self.lock:
            if self.sessions.get(token, 0) <= time.monotonic():
                raise AppError(401, "INVALID_TOKEN", "Sign in to the local demo again")
            return USER


class Login(BaseModel):
    email: str = Field(max_length=100)
    password: str = Field(max_length=100)


def unavailable_registry(request):
    # External lookups are deliberately disabled, never silently routed to the Internet.
    return httpx.Response(503, json={"localDemo": True})


def create_local_app(root: Path | None = None):
    if os.environ.get("K_SERVICE") or os.environ.get("K_REVISION"):
        raise RuntimeError("Local demonstration must not run in Cloud Run")
    root = root or Path(os.environ.get("SAQ_LOCAL_DATA", ".local-demo-data"))
    # Explicit values ignore developer/cloud credentials, .env and injected API keys.
    settings = Settings(
        _env_file=None,
        firebase_enabled=False,
        firebase_project_id="demo-saq-local",
        firebase_credentials_path=None,
        firebase_storage_bucket="",
        firebase_demo_only=True,
        gemini_api_key="",
        gemini_model="local-demo-rules-not-gemini",
        searchapi_api_key="",
        searchapi_enabled=False,
        searchapi_schedule_enabled=False,
        cors_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    )
    workspace = WorkspaceService(LocalStore(root, local_seed()))
    files = FileService(workspace, LocalFiles(root))
    client = LocalAnalysis()
    identity = LocalIdentity()
    registry = RegistryClient(httpx.MockTransport(unavailable_registry))
    monitoring = MonitoringService(workspace, settings, LocalCollector(), client, registry)
    for name, kind, target in [
        ("DEMO — Telegram", "telegram", "demo_housing"),
        ("DEMO — Instagram", "instagram_ads", "квартиры Өскемен"),
    ]:
        monitoring.create_source(SourceInput(name=name, kind=kind, target=target), USER)
    if not workspace.store.list("monitorRuns", limit=1):
        source = monitoring.sources()["items"][0]
        monitoring.run(source["id"], USER)
    app = create_app(settings)
    app.state.local_identity = identity
    app.state.local_workspace = workspace
    app.dependency_overrides[get_runtime] = lambda: identity
    app.dependency_overrides[workspace_service] = lambda: workspace
    app.dependency_overrides[file_service] = lambda: files
    analysis = AnalysisService(workspace, client, files, settings)
    drone = DroneService(workspace, files.storage, LocalDrone(), settings)
    companies = CompanyService(workspace, CompanyRegistry(registry))
    app.dependency_overrides[analysis_service] = lambda: analysis
    app.dependency_overrides[drone_service] = lambda: drone
    app.dependency_overrides[monitoring_service] = lambda: monitoring
    app.dependency_overrides[company_service] = lambda: companies

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        host = request.url.hostname
        origin = request.headers.get("origin")
        if host not in {"localhost", "127.0.0.1", "backend"} or (
            origin is not None and origin not in settings.cors_origins
        ):
            return JSONResponse({"code": "LOCAL_ONLY", "message": "Local demo only"}, 403)
        response = await call_next(request)
        response.headers["X-SAQ-Mode"] = "local-demo"
        return response

    @app.post("/api/local-demo/session")
    def login(payload: Login):
        return {"token": identity.login(payload.email, payload.password), "mode": "local-demo"}

    @app.delete("/api/local-demo/session", status_code=204)
    def logout(request: Request):
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        with identity.lock:
            identity.sessions.pop(token, None)

    @app.get("/api/local-demo/info")
    def info():
        return {"mode": "local-demo", "data": "fictional", "ai": "not-connected"}

    return app
