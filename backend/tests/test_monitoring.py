"""Local-only intake, concurrency, quota and expert workflow regression tests."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import current_user
from app.api.monitoring import monitoring_service
from app.core.config import Settings
from app.core.errors import AppError, Conflict
from app.main import create_app
from app.models.analysis import Extraction
from app.models.auth import Principal
from app.models.common import utc_now
from app.models.monitoring import ItemAnalyze, ItemAttach, ItemReview, SourceInput, SourceUpdate
from app.services.gemini import GeminiClient
from app.services.monitoring import MonitoringService
from app.services.public_sources import PublicCollector
from app.services.seed_data import build_demo_seed
from app.services.workspace import WorkspaceService
from tests.fakes import MemoryStore
from tests.test_public_sources import TEXT, rss

USER = Principal(uid="monitor-qa", role="analyst")


@pytest.fixture
def service():
    return MonitoringService(
        WorkspaceService(MemoryStore(build_demo_seed())),
        Settings(gemini_api_key="test-not-real", gemini_model="test-model"),
        PublicCollector(httpx.MockTransport(lambda r: httpx.Response(200, text=rss()))),
    )


def create(service, **kw):
    return service.create_source(
        SourceInput(name="DEMO QA", kind="web_search", target="Өскемен квартиры", **kw), USER
    )


def due(service, s):
    service.store.documents["monitorSources"][s["id"]]["nextRunAt"] = None


def collect(service):
    s = create(service)
    run = service.run(s["id"], USER)
    return s, run, service.items()["items"][0]


def use_ai(service, on_call=None):
    calls = []

    def handler(request):
        calls.append(request)
        if on_call:
            on_call()
        extraction = Extraction(
            hypotheses=[
                {
                    "code": "R2",
                    "quote": "Внесите депозит 150 000 тенге.",
                    "explanation": "DEMO QA hypothesis",
                    "confidence": 0.8,
                }
            ],
            mentioned_complexes=[],
            payment_terms=["150 000 тенге"],
            uncertainty="DEMO test response",
        )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": extraction.model_dump_json(by_alias=True)}]},
                    }
                ]
            },
        )

    service.client = GeminiClient(service.settings, httpx.MockTransport(handler))
    return calls


def test_real_queue_separate_from_demo_and_deduplicated(service):
    before = deepcopy(service.store.documents)
    s, run, item = collect(service)
    assert (run["fetched"], run["created"], run["duplicates"]) == (1, 1, 0)
    assert item["demo"] is False and item["publishedAt"] is None
    assert item["status"] == "new" and item["extraction"] is None
    assert all(
        item[k]
        for k in [
            "regionMatches",
            "housingMatches",
            "paymentMatches",
            "textSha256",
            "responseSha256",
            "discoveryUrl",
        ]
    )
    due(service, s)
    assert service.run(s["id"], USER)["duplicates"] == 1
    assert len(service.items()["items"]) == 1
    for c in ["complexes", "advertisements", "evidence", "signals", "aiHypotheses"]:
        assert service.store.documents.get(c) == before.get(c)


def test_revisions_preserve_reviewed_original_and_audit(service):
    s, _, item = collect(service)
    reviewed = service.review(
        item["id"],
        ItemReview(expected_version=1, decision="investigating", notes="DEMO: проверить оригинал"),
        USER,
    )
    service.collector = PublicCollector(
        httpx.MockTransport(
            lambda r: httpx.Response(200, text=rss(TEXT.replace("150 000", "250 000")))
        )
    )
    due(service, s)
    service.run(s["id"], USER)
    rows = service.items()["items"]
    assert len(rows) == 2 and len({r["revisionKey"] for r in rows}) == 1
    old = service.item(item["id"])
    assert old.status == "investigating" and old.notes == reviewed.notes and "150 000" in old.text
    assert service.history(item["id"])["items"][0]["actorUid"] == USER.uid
    with pytest.raises(Conflict):
        service.review(
            item["id"], ItemReview(expected_version=1, decision="dismissed", notes="stale"), USER
        )


def test_pause_interval_fetch_quota_failure_are_explicit(service):
    s = create(service)
    service.update_source(
        s["id"], SourceUpdate(expected_version=1, enabled=False, auto_analyze=False), USER
    )
    with pytest.raises(AppError, match="paused"):
        service.run(s["id"], USER)
    service.update_source(
        s["id"], SourceUpdate(expected_version=2, enabled=True, auto_analyze=False), USER
    )
    service.collector = PublicCollector(
        httpx.MockTransport(lambda r: httpx.Response(403, text="private provider body"))
    )
    with pytest.raises(AppError) as e:
        service.run(s["id"], USER)
    assert e.value.code == "MONITOR_SOURCE_BLOCKED"
    assert service.runs()["items"][0]["status"] == "failed"
    assert service.sources()["items"][0]["lastError"] == e.value.code
    assert service.status()["dailyFetchUsed"] == 1
    with pytest.raises(AppError) as e:
        service.run(s["id"], USER)
    assert e.value.code == "MONITOR_NOT_DUE"
    service.settings.monitor_daily_fetch_limit = 1
    due(service, s)
    with pytest.raises(AppError) as e:
        service.run(s["id"], USER)
    assert e.value.code == "MONITOR_DAILY_LIMIT"


def test_concurrent_workers_one_http_call(service):
    entered, release = Event(), Event()
    calls = []

    def handler(r):
        calls.append(r)
        entered.set()
        assert release.wait(5)
        return httpx.Response(200, text=rss())

    service.collector = PublicCollector(httpx.MockTransport(handler))
    s = create(service)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.run, s["id"], USER)
        assert entered.wait(5)
        second = pool.submit(service.run, s["id"], USER)
        try:
            with pytest.raises(AppError) as e:
                second.result(5)
            assert e.value.code == "MONITOR_BUSY"
        finally:
            release.set()
        assert first.result(5)["created"] == 1
    assert len(calls) == 1


def test_old_worker_cannot_complete_new_lease(service):
    s = create(service)
    old, oldrun = service._reserve(s["id"], USER)
    service.store.documents["monitorSources"][s["id"]]["leaseUntil"] = "2000-01-01T00:00:00Z"
    due(service, s)
    _, newrun = service._reserve(s["id"], USER)
    with pytest.raises(Conflict):
        service._finish(old, oldrun)
    assert service.sources()["items"][0]["activeRunId"] == newrun.id
    assert service.store.get("monitorRuns", oldrun.id)["errorCode"] == "MONITOR_LEASE_LOST"


def test_auto_ai_opt_in_at_most_one_and_shared_quota(service):
    calls = use_ai(service)
    s, _, item = collect(service)
    assert calls == []
    service.update_source(
        s["id"], SourceUpdate(expected_version=1, enabled=True, auto_analyze=True), USER
    )
    due(service, s)
    assert service.run(s["id"], USER)["autoAiStatus"] == "succeeded" and len(calls) == 1
    assert service.store.get("usageLimits", f"global-{utc_now():%Y%m%d}")["count"] == 1
    due(service, s)
    service.run(s["id"], USER)
    assert len(calls) == 1 and service.item(item["id"]).extraction.hypotheses[0].code == "R2"
    assert service.workspace.complex("demo-complex-01").version == 1


def test_ai_idempotency_quota_and_concurrent_human_notes(service):
    _, _, item = collect(service)

    def review_during_ai():
        current = service.item(item["id"])
        service.review(
            current.id,
            ItemReview(
                expected_version=current.version,
                decision="investigating",
                notes="DEMO: заметка во время AI",
            ),
            USER,
        )

    calls = use_ai(service, review_during_ai)
    request = ItemAnalyze(expected_version=1, request_id=uuid4())
    result = service.analyze(item["id"], request, USER)
    assert result.notes == "DEMO: заметка во время AI" and result.ai_status == "succeeded"
    assert service.analyze(item["id"], request, USER) == result and len(calls) == 1
    service.settings.ai_daily_user_limit = 1
    cached = service.analyze(
        item["id"], ItemAnalyze(expected_version=result.version, request_id=uuid4()), USER
    )
    assert cached.ai_status == "succeeded" and len(calls) == 1
    from app.services.monitoring import sha

    changed = service.store.get("monitorItems", item["id"])
    changed["id"] = "new-input"
    changed["text"] += " Новое предложение."
    changed["textSha256"] = sha(changed["text"])
    changed["aiStatus"] = "not_requested"
    service.store.atomic(lambda tx: tx.create("monitorItems", changed["id"], changed))
    with pytest.raises(AppError) as e:
        service.analyze(
            changed["id"],
            ItemAnalyze(expected_version=changed["version"], request_id=uuid4()),
            USER,
        )
    assert e.value.code == "AI_DAILY_LIMIT" and len(calls) == 1


def test_failed_ai_keeps_source_and_safe_diagnostic(service):
    _, _, item = collect(service)
    service.client = GeminiClient(
        service.settings,
        httpx.MockTransport(lambda r: httpx.Response(404, text="private provider body")),
    )
    result = service.analyze(item["id"], ItemAnalyze(expected_version=1, request_id=uuid4()), USER)
    assert result.ai_status == "failed" and result.ai_error == "AI_MODEL_UNAVAILABLE"
    assert "private provider body" not in json.dumps(service.store.documents)
    assert result.text == item["text"]


def test_attach_no_demo_laundering_no_automatic_risk_and_replay(service):
    _, _, item = collect(service)
    use_ai(service)
    analyzed = service.analyze(
        item["id"], ItemAnalyze(expected_version=1, request_id=uuid4()), USER
    )
    payload = ItemAttach(
        expected_version=analyzed.version,
        complex_id="demo-complex-01",
        notes="DEMO isolated QA fixture link",
    )
    with pytest.raises(AppError) as e:
        service.attach(item["id"], payload, USER)
    assert e.value.code == "MONITOR_LIVE_REGISTRY_REQUIRED"
    service.workspace.demo_only = False
    with pytest.raises(AppError) as e:
        service.attach(item["id"], payload, USER)
    assert e.value.code == "SCOPE_MISMATCH"
    service.store.documents["complexes"][payload.complex_id]["demo"] = False
    before = deepcopy(service.store.documents["complexes"])
    linked = service.attach(item["id"], payload, USER)
    ad = service.store.get("advertisements", linked["advertisementId"])
    assert not ad["demo"] and ad["text"] == item["text"] and ad["publishedAt"] is None
    assert service.attach(item["id"], payload, USER) == linked
    assert service.store.documents["complexes"] == before
    hs = [
        h
        for h in service.store.documents["aiHypotheses"].values()
        if h["advertisementId"] == ad["id"]
    ]
    assert len(hs) == 1 and hs[0]["status"] == "proposed"
    assert service.store.get("evidence", hs[0]["evidenceId"])["status"] == "proposed"


def test_pagination_tied_dates_and_status_filter(service):
    _, _, item = collect(service)
    for i in range(5):
        row = {**item, "id": f"page-{i}", "createdAt": "2026-10-17T10:00:00+00:00"}
        service.store.documents["monitorItems"][row["id"]] = row
    ids = []
    cursor = None
    while True:
        page = service.items("new", cursor, 2)
        ids.extend(r["id"] for r in page["items"])
        cursor = page["nextCursor"]
        if not cursor:
            break
    assert len(ids) == len(set(ids)) == 6
    assert service.items("dismissed")["items"] == []


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/status", None),
        ("get", "/sources", None),
        ("post", "/sources", {"name": "s", "kind": "web_search", "target": "ВКО"}),
        ("get", "/items", None),
        ("get", "/items/item", None),
        ("get", "/items/item/registry?q=test", None),
        ("get", "/items/item/registry/12", None),
        ("post", "/items/item/basis-review", {}),
        ("get", "/runs", None),
        ("post", "/sources/source/run", None),
        ("get", "/items/item/history", None),
        ("patch", "/sources/source", {"expectedVersion": 1, "enabled": True, "autoAnalyze": False}),
        ("post", "/items/item/review", {"expectedVersion": 1, "decision": "new", "notes": "QA"}),
        ("post", "/items/item/analyze", {"expectedVersion": 1, "requestId": str(uuid4())}),
        ("post", "/items/item/attach", {"expectedVersion": 1, "complexId": "c", "notes": "QA"}),
    ],
)
def test_all_monitor_routes_require_auth(method, path, payload):
    with TestClient(create_app(Settings())) as client:
        r = client.request(
            method, "/api/v1/monitoring" + path, **({"json": payload} if payload else {})
        )
    assert r.status_code == 401


def test_api_collection_review_and_worker_heartbeat(service):
    app = create_app(Settings())
    app.dependency_overrides[current_user] = lambda: USER
    app.dependency_overrides[monitoring_service] = lambda: service
    with TestClient(app) as c:
        s = c.post(
            "/api/v1/monitoring/sources",
            json={"name": "QA", "kind": "web_search", "target": "Өскемен квартиры"},
        ).json()
        run = c.post(f"/api/v1/monitoring/sources/{s['id']}/run")
        assert run.status_code == 200 and run.json()["created"] == 1
        item = c.get("/api/v1/monitoring/items").json()["items"][0]
        result = c.post(
            f"/api/v1/monitoring/items/{item['id']}/review",
            json={"expectedVersion": 1, "decision": "investigating", "notes": "QA check original"},
        )
        assert result.status_code == 200 and result.json()["reviewer"] == USER.uid
        assert c.get("/api/v1/monitoring/items?status=dismissed").json()["items"] == []
    assert service.status()["workerLastTickAt"] is None
    assert service.run_due(USER) == []
    assert service.status()["workerLastTickAt"] is not None


def test_worker_prioritizes_oldest_due_sources_not_smallest_ids(service):
    sources = [
        service.create_source(
            SourceInput(name=f"QA source {i}", kind="web_search", target=f"Өскемен квартиры {i}"),
            USER,
        )
        for i in range(5)
    ]
    ordered = sorted(sources, key=lambda row: row["id"])
    for i, source in enumerate(ordered):
        service.store.documents["monitorSources"][source["id"]]["nextRunAt"] = (
            f"2000-01-{5 - i:02}T00:00:00Z"
        )
    service.settings.monitor_sources_per_tick = 2
    results = service.run_due(USER)
    assert [r["sourceId"] for r in results] == [ordered[4]["id"], ordered[3]["id"]]
    assert service.sources()["items"][0]["id"]  # Collection remains usable.
