"""Threaded workflow regressions with explicit MemoryStore/MockTransport adapters.

These exercise application atomicity boundaries, not live Firestore contention.
Real SDK retry behavior is covered separately in test_transaction_failures.py.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Event
from uuid import uuid4

import httpx

from app.core.errors import AppError, Conflict
from app.models.analysis import AnalysisRequest
from app.models.auth import Principal
from app.models.signals import SignalCreate, SignalDecision
from app.schemas.workspace import FactorDecision
from app.services.analysis import AnalysisService
from app.services.files import FileService
from app.services.gemini import GeminiClient
from app.services.seed_data import build_demo_seed
from app.services.signals import SignalService
from app.services.workspace import WorkspaceService, serialize
from tests.fakes import MemoryStore
from tests.test_analysis import USER, FakeFiles, extraction, mock_response, settings


def analysis_fixture(handler=None, **limits):
    store = MemoryStore(build_demo_seed())
    workspace = WorkspaceService(store)
    quote = store.get("advertisements", "demo-ad-01")["text"]
    config = settings(**limits)
    client = GeminiClient(
        config, httpx.MockTransport(handler or (lambda _: mock_response(extraction(quote))))
    )
    service = AnalysisService(workspace, client, FileService(workspace, FakeFiles()), config)
    return service, store


def test_parallel_duplicate_analysis_has_one_provider_call_and_one_quota_charge():
    entered, release = Event(), Event()
    calls = []
    quote = build_demo_seed()["advertisements"][0]["text"]

    def handler(request):
        calls.append(request)
        entered.set()
        assert release.wait(timeout=5), "Test must release the simulated provider"
        return mock_response(extraction(quote))

    service, store = analysis_fixture(handler)
    original_complexes = deepcopy(store.documents["complexes"])
    payload = AnalysisRequest(request_id=uuid4(), expected_version=1)

    def duplicate():
        try:
            return service.analyze("demo-ad-01", payload, USER)
        except Conflict as error:
            return error

    with ThreadPoolExecutor(max_workers=5) as pool:
        first = pool.submit(duplicate)
        try:
            assert entered.wait(timeout=5)
            duplicates = [pool.submit(duplicate) for _ in range(4)]
            assert all(isinstance(task.result(timeout=5), Conflict) for task in duplicates)
        finally:
            release.set()
        completed = first.result(timeout=5)
    assert completed["status"] == "succeeded"
    assert service.analyze("demo-ad-01", payload, USER) == completed
    assert len(calls) == 1
    assert len(store.documents["analysisRuns"]) == len(store.documents["aiHypotheses"]) == 1
    assert len(store.documents["auditLogs"]) == 1
    assert all(row["count"] == 1 for row in store.documents["usageLimits"].values())
    assert store.documents["complexes"] == original_complexes


def test_parallel_users_cannot_exceed_global_or_personal_analysis_limits():
    service, store = analysis_fixture(ai_daily_global_limit=3, ai_daily_user_limit=2)
    original_complexes = deepcopy(store.documents["complexes"])
    start = Barrier(12)

    def analyze(index):
        user = Principal(uid=f"test-user-{index % 3}", role="analyst")
        start.wait(timeout=5)
        try:
            return service.analyze(
                "demo-ad-01", AnalysisRequest(request_id=uuid4(), expected_version=1), user
            )
        except AppError as error:
            return error

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(analyze, range(12)))
    failures = [result for result in results if isinstance(result, AppError)]
    assert len(failures) == 9
    assert all((error.status_code, error.code) == (429, "AI_DAILY_LIMIT") for error in failures)
    assert len(store.documents["analysisRuns"]) == len(store.documents["aiHypotheses"]) == 3
    counters = store.documents["usageLimits"]
    assert sum(row["count"] for key, row in counters.items() if key.startswith("global-")) == 3
    personal = [row["count"] for key, row in counters.items() if key.startswith("user-")]
    assert sum(personal) == 3 and max(personal) <= 2
    assert len(store.documents["auditLogs"]) == 3
    assert store.documents["complexes"] == original_complexes


def test_lost_success_response_replays_saved_analysis_without_second_provider_call(monkeypatch):
    calls = []
    quote = build_demo_seed()["advertisements"][0]["text"]

    def handler(request):
        calls.append(request)
        return mock_response(extraction(quote))

    service, store = analysis_fixture(handler)
    atomic = store.atomic
    transactions = 0

    def ambiguous_commit(operation):
        nonlocal transactions
        transactions += 1
        result = atomic(operation)
        if transactions == 2:  # completion persisted, but its acknowledgement was lost
            raise AppError(503, "INTEGRATION_UNAVAILABLE", "Test-only lost commit reply")
        return result

    monkeypatch.setattr(store, "atomic", ambiguous_commit)
    payload = AnalysisRequest(request_id=uuid4(), expected_version=1)
    try:
        service.analyze("demo-ad-01", payload, USER)
    except AppError as error:
        assert error.status_code == 503
    else:
        raise AssertionError("The simulated reply must fail")
    saved = store.get("analysisRuns", str(payload.request_id))
    assert saved["status"] == "succeeded" and "errorCode" not in saved
    before = deepcopy(store.documents)
    assert service.analyze("demo-ad-01", payload, USER) == saved
    assert len(calls) == 1 and store.documents == before


def test_competing_factor_decisions_have_one_winner_and_one_audit_event():
    store = MemoryStore(build_demo_seed())
    workspace = WorkspaceService(store)
    start = Barrier(2)

    def decide(index):
        user = Principal(uid=f"test-reviewer-{index}", role="analyst")
        start.wait(timeout=5)
        try:
            result = workspace.factor_decision(
                "demo-complex-01",
                FactorDecision(
                    code="R2", decision="rejected", expected_version=1, notes=f"Review {index}"
                ),
                user,
            )
            return user.uid, result
        except Conflict as error:
            return user.uid, error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, range(2)))
    winners = [(uid, result) for uid, result in results if isinstance(result, dict)]
    assert len(winners) == 1
    winner, result = winners[0]
    assert result["version"] == 2 and result["risk"]["score"] == 10
    assert len(store.documents["auditLogs"]) == 1
    event = next(iter(store.documents["auditLogs"].values()))
    assert event["actorUid"] == winner
    assert (event["details"]["beforeScore"], event["details"]["afterScore"]) == (35, 10)
    factor = next(row for row in result["factors"] if row["code"] == "R2")
    assert factor["reviewer"] == winner


def test_competing_signal_confirm_and_return_preserve_one_immutable_revision():
    store = MemoryStore(build_demo_seed())
    signals = SignalService(WorkspaceService(store))
    draft = signals.create(
        SignalCreate(
            complex_id="demo-complex-02",
            expected_complex_version=1,
            title="DEMO concurrent review",
            reason="Test-only review reason",
        ),
        USER,
    )
    pending = signals.decision(
        draft.id, SignalDecision(action="submit", expected_version=1, notes="For review"), USER
    )
    old_revision = deepcopy(store.get("signalRevisions", f"{draft.id}-2"))
    start = Barrier(2)

    def decide(action):
        user = Principal(uid=f"test-{action}", role="analyst")
        start.wait(timeout=5)
        try:
            return signals.decision(
                pending.id,
                SignalDecision(action=action, expected_version=2, notes=f"Test {action}"),
                user,
            )
        except Conflict as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, ["confirm", "return"]))
    assert sum(isinstance(result, Conflict) for result in results) == 1
    final = signals.get(pending.id)
    assert final.version == 3 and final.status in {"confirmed", "returned"}
    assert len(store.documents["signalRevisions"]) == len(store.documents["auditLogs"]) == 3
    assert store.get("signalRevisions", f"{draft.id}-2") == old_revision == serialize(pending)
    assert store.get("signalRevisions", f"{draft.id}-3") == serialize(final)
    assert final.snapshot == pending.snapshot
    last = next(
        row
        for row in store.documents["auditLogs"].values()
        if row["details"].get("signalVersion") == 3
    )
    assert last["actorUid"] == final.reviewer


def test_parallel_seed_imports_keep_one_marker_and_one_original_actor():
    from app.services.seed import import_demo_seed

    store = MemoryStore()
    start = Barrier(4)

    def seed(index):
        start.wait(timeout=5)
        return import_demo_seed(store, f"test-admin-{index}")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(seed, range(4)))
    assert sum(not result["alreadyImported"] for result in results) == 1
    assert sum(result["created"] for result in results) == 37
    assert len(store.documents["seedRuns"]) == len(store.documents["auditLogs"]) == 1
    marker = next(iter(store.documents["seedRuns"].values()))
    event = next(iter(store.documents["auditLogs"].values()))
    assert marker["actorUid"] == event["actorUid"]
    assert len(store.documents["complexes"]) == len(store.documents["developers"]) == 8
    assert len(store.documents["advertisements"]) == 12
