"""Local QA only: real routes/services, existing test adapters, no cloud traffic.

Run from backend with PYTHONPATH pointing to this directory (see README.md).
Never import this module from the production application.
"""

import json

import httpx
from app.api.analysis import analysis_service, file_service
from app.api.dependencies import get_runtime
from app.api.monitoring import monitoring_service
from app.api.workspace import workspace_service
from app.core.config import Settings
from app.core.errors import AppError
from app.main import create_app
from app.models.auth import Principal
from app.services.analysis import AnalysisService
from app.services.files import FileService
from app.services.gemini import GeminiClient
from app.services.monitoring import MonitoringService
from app.services.public_sources import PublicCollector
from app.services.seed_data import build_demo_seed
from app.services.workspace import WorkspaceService
from tests.fakes import MemoryStore
from tests.test_analysis import FakeFiles


class TestIdentity:
    def verify_token(self, token):
        if token != "qa-local-analyst":
            raise AppError(401, "INVALID_TOKEN", "Test session expired")
        return Principal(
            uid="qa-local-analyst", role="analyst", email="qa@example.test"
        )


def model_response(request):
    source = json.loads(json.loads(request.content)["contents"][0]["parts"][0]["text"])[
        "sourceText"
    ]
    quote = source if "депозит" in source.lower() else ""
    payload = {
        "hypotheses": [
            {
                "code": "R2",
                "quote": quote,
                "explanation": "TEST hypothesis; verify the original",
                "confidence": None,
            }
        ]
        if quote
        else [],
        "mentionedComplexes": [],
        "paymentTerms": [],
        "uncertainty": "TEST RESPONSE from MockTransport; not a real Gemini result",
    }
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": json.dumps(payload)}]},
                }
            ]
        },
    )


settings = Settings(
    _env_file=None,
    firebase_enabled=False,
    firebase_credentials_path=None,
    firebase_storage_bucket="",
    gemini_api_key="qa-placeholder-not-a-key",
    gemini_model="test-model",
    ai_daily_user_limit=1000,
    ai_daily_global_limit=10000,
)
workspace = WorkspaceService(MemoryStore(build_demo_seed()))
files = FileService(workspace, FakeFiles())
analysis = AnalysisService(
    workspace,
    GeminiClient(settings, httpx.MockTransport(model_response)),
    files,
    settings,
)
app = create_app(settings)
app.dependency_overrides[get_runtime] = lambda: TestIdentity()
app.dependency_overrides[workspace_service] = lambda: workspace
app.dependency_overrides[file_service] = lambda: files
app.dependency_overrides[analysis_service] = lambda: analysis

# Explicit synthetic public-source HTTP adapter, never a production fallback.
def public_source_response(request):
    return httpx.Response(200, text='''<rss><channel><item>
    <title>LOCAL QA DEMO — реклама жилья</title><link>https://example.org/qa-housing</link>
    <description>DEMO — вымышленная публикация. Өскемен, квартиры в строящемся доме.
    Внесите депозит 150 000 тенге. Это локальная тестовая страница.</description>
    </item></channel></rss>''')


monitoring = MonitoringService(workspace, settings,
    PublicCollector(httpx.MockTransport(public_source_response)),
    GeminiClient(settings, httpx.MockTransport(model_response)))
app.dependency_overrides[monitoring_service] = lambda: monitoring
