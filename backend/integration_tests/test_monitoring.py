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


def test_sdk_meta_provider_lease_reserve_and_private_queue(workspace):
    from app.services.searchapi import SearchApiCollector
    from tests.test_searchapi import ad

    config = Settings(
        _env_file=None,
        searchapi_enabled=True,
        searchapi_api_key="sdk-synthetic-key",
    )
    calls = []

    def provider(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/me"):
            return httpx.Response(200, json={"account": {"remaining_credits": 21}})
        return httpx.Response(200, json={"ads": [ad()]})

    monitor = MonitoringService(
        workspace, config, SearchApiCollector(config, httpx.MockTransport(provider))
    )
    first = monitor.create_source(
        SourceInput(name="DEMO SDK Meta", kind="instagram_ads", target="квартиры Өскемен"), USER
    )
    second = monitor.create_source(
        SourceInput(name="DEMO SDK Meta 2", kind="instagram_ads", target="квартиры Риддер"), USER
    )
    original, run = monitor._reserve(first["id"], USER)
    with pytest.raises(AppError) as error:
        monitor.run(second["id"], USER)
    assert error.value.code == "SEARCHAPI_BUSY" and not calls
    run.status = "failed"
    monitor._finish(original, run)
    result = monitor.run(second["id"], USER)
    assert result["created"] == 1 and calls == ["/api/v1/me", "/api/v1/search"]
    assert monitor.status()["searchApi"]["unsettledAttempts"] == 0
    assert monitor.items()["items"][0]["adArchiveId"] == "100000000000001"


def test_sdk_active_queue_cursor_and_registry_confirmation(workspace, db):
    from app.models.monitoring import MonitorItem
    from app.services.registries import RegistryClient
    from tests.test_registries import detail, payload

    monitor = service(workspace)
    source = create(monitor)
    monitor.run(source["id"], USER)
    original = monitor.items()["items"][0]
    before = deepcopy(workspace.complex_detail("demo-complex-01"))
    for index, status in enumerate(["new", "investigating", "dismissed"]):
        row = MonitorItem.model_validate({**original, "id": f"sdk-item-{index}", "status": status})
        db.collection("monitorItems").document(row.id).set(
            row.model_dump(mode="json", by_alias=True)
        )
    first = monitor.items("active", limit=1)
    seen = [first["items"][0]["id"]]
    cursor = first["nextCursor"]
    while cursor:
        page = monitor.items("active", cursor=cursor, limit=1)
        seen += [row["id"] for row in page["items"]]
        cursor = page["nextCursor"]
    assert len(seen) == len(set(seen)) == 3 and "sdk-item-2" not in seen
    db.collection("monitorItems").document(seen[0]).update({"status": "dismissed"})
    with pytest.raises(Conflict):
        monitor.items("active", cursor=first["nextCursor"], limit=1)
    monitor.registry = RegistryClient(
        httpx.MockTransport(lambda r: httpx.Response(200, json=detail()))
    )
    updated = monitor.confirm_basis("sdk-item-1", payload(original), USER)
    assert updated.basis_review.document.reference == "SYNTHETIC-PERMIT-1"
    assert "sdk-item-1" not in [row["id"] for row in monitor.items("active")["items"]]
    assert monitor.history("sdk-item-1")["items"][0]["action"] == "item.basis.confirm"
    assert workspace.complex_detail("demo-complex-01") == before
