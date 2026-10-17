"""Native Firestore SDK tests on the opt-in local emulator; no real cloud/social requests."""

import os
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import AppError, Conflict
from app.models.auth import Principal
from app.models.monitoring import ItemAnalyze, ItemReview, SourceInput
from app.services.gemini import GeminiClient
from app.services.monitoring import MonitoringService
from app.services.public_sources import PublicCollector
from tests.test_public_sources import rss

USER = Principal(uid="sdk-monitor-reviewer", role="analyst")


def service(workspace):
    return MonitoringService(
        workspace,
        Settings(gemini_api_key="synthetic-not-real", gemini_model="test-model"),
        PublicCollector(httpx.MockTransport(lambda r: httpx.Response(200, text=rss()))),
    )


def create(monitor):
    return monitor.create_source(
        SourceInput(name="Synthetic SDK source", kind="web_search", target="Өскемен квартиры"), USER
    )


def test_sdk_ingest_review_pagination_and_private_rules(workspace, db):
    monitor = service(workspace)
    before = deepcopy(workspace.complex_detail("demo-complex-01"))
    source = create(monitor)
    result = monitor.run(source["id"], USER)
    assert result["created"] == 1
    item = monitor.items("new", limit=1)["items"][0]
    reviewed = monitor.review(
        item["id"],
        ItemReview(expected_version=1, decision="investigating", notes="SDK QA original check"),
        USER,
    )
    assert reviewed.reviewer == USER.uid and reviewed.version == 2
    assert monitor.items("new")["items"] == []
    assert monitor.history(item["id"], limit=1)["items"][0]["action"] == "item.review"
    db.collection("monitorSources").document(source["id"]).update({"nextRunAt": None})
    assert monitor.run(source["id"], USER)["duplicates"] == 1
    assert monitor.item(item["id"]).status == "investigating"
    assert workspace.complex_detail("demo-complex-01") == before
    host = os.environ["FIRESTORE_EMULATOR_HOST"]
    root = f"http://{host}/v1/projects/{db.project}/databases/(default)/documents"
    with httpx.Client(trust_env=False, timeout=10) as client:
        assert client.get(root + "/monitorItems/" + item["id"]).status_code == 403
        assert (
            client.patch(root + "/monitorSources/" + source["id"], json={"fields": {}}).status_code
            == 403
        )


def test_sdk_stale_lease_and_shared_ai_quota(workspace, db):
    monitor = service(workspace)
    source = create(monitor)
    old, run = monitor._reserve(source["id"], USER)
    db.collection("monitorSources").document(source["id"]).update(
        {"leaseUntil": "2000-01-01T00:00:00Z", "nextRunAt": None}
    )
    current, newrun = monitor._reserve(source["id"], USER)
    with pytest.raises(Conflict):
        monitor._finish(old, run)
    assert monitor.sources()["items"][0]["activeRunId"] == newrun.id
    newrun.status = "succeeded"
    monitor._finish(current, newrun)
    db.collection("monitorSources").document(source["id"]).update({"nextRunAt": None})
    monitor.run(source["id"], USER)
    item = monitor.items()["items"][0]
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "private test message"}})

    monitor.client = GeminiClient(monitor.settings, httpx.MockTransport(provider))
    request = ItemAnalyze(expected_version=1, request_id=uuid4())
    first = monitor.analyze(item["id"], request, USER)
    assert first.ai_status == "failed" and first.ai_error == "AI_PROVIDER_QUOTA"
    assert monitor.analyze(item["id"], request, USER) == first and len(calls) == 1
    monitor.settings.ai_daily_global_limit = 1
    with pytest.raises(AppError) as error:
        monitor.analyze(
            item["id"], ItemAnalyze(expected_version=first.version, request_id=uuid4()), USER
        )
    assert error.value.code == "AI_DAILY_LIMIT" and len(calls) == 1
