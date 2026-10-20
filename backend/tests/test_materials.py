"""Actual services/routes with explicit local providers; no cloud or paid calls."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import current_user
from app.api.workspace import workspace_service
from app.core.config import Settings
from app.core.errors import AppError, Conflict
from app.main import create_app
from app.models.analysis import Extraction
from app.models.auth import Principal
from app.models.common import utc_now
from app.models.materials import MaterialRetry, MaterialReview
from app.models.monitoring import Observation
from app.schemas.workspace import AdvertisementCreate
from app.services.files import FileService
from app.services.material_analysis import MaterialProcessor
from app.services.material_projection import monitor_occurrence, stage_occurrence
from app.services.materials import MaterialService
from app.services.seed_data import build_demo_seed
from app.services.workspace import WorkspaceService
from tests.fakes import MemoryStore
from tests.test_analysis import FakeFiles, png

USER = Principal(uid="material-qa", role="analyst", display_name="Тестовый аналитик")
TEXT = "Квартиры в строящемся доме. Внесите депозит 150 000 тенге."
CID = "demo-complex-04"


class Provider:
    def __init__(self):
        self.calls = []
        self.error = None
        self.on_call = None

    def check_config(self):
        pass

    def extract(self, text, image):
        self.calls.append((text, image))
        if self.on_call:
            self.on_call()
        if self.error:
            raise self.error
        hs = []
        for code, quote in [
            ("R2", "Внесите депозит 150 000 тенге."),
            ("R3", "Квартиры в строящемся доме."),
        ]:
            if quote in text:
                hs.append({"code": code, "quote": quote, "explanation": "Синтетический результат"})
        return Extraction(
            hypotheses=hs,
            mentioned_complexes=[],
            payment_terms=[],
            uncertainty="Только тестовый адаптер",
        )


@pytest.fixture
def services():
    seed = build_demo_seed()
    for key in ["advertisements", "evidence"]:
        seed[key] = []
    next(c for c in seed["complexes"] if c["id"] == CID)["factors"] = []
    store = MemoryStore(seed)
    workspace = WorkspaceService(store)
    files = FileService(workspace, FakeFiles())
    provider = Provider()
    settings = Settings(_env_file=None, gemini_api_key="", gemini_model="local-test")
    return (
        workspace,
        MaterialService(workspace),
        MaterialProcessor(workspace, provider, files, settings),
        provider,
        files,
    )


def ad(workspace, text=TEXT, url=None, cid=CID):
    return workspace.create_advertisement(
        AdvertisementCreate(
            complex_id=cid,
            text=text,
            platform="Telegram",
            account="DEMO QA",
            source_url=url or "https://example.org/" + uuid4().hex,
            published_at=utc_now(),
        ),
        USER,
    )


def detail(materials):
    rows = materials.items()["items"]
    assert len(rows) == 1
    return materials.detail(rows[0]["id"])


def review_payload(item, **kw):
    return MaterialReview(
        request_id=uuid4(),
        expected_version=item["version"],
        revision_id=item["revisionId"],
        complex_id=item["complex"]["id"] if item["complex"] else None,
        expected_complex_version=item["complex"]["version"] if item["complex"] else None,
        notes="Проверены оригинал, платёж и строительство.",
        disposition=kw.get("disposition", "reviewed"),
        decisions=[
            {"hypothesisId": h["id"], "decision": kw.get("decision", "confirmed")}
            for h in item["hypotheses"]
        ],
    )


def test_auto_intake_duplicate_one_analysis_and_no_automatic_confirmed_score(services):
    w, m, processor, provider, _ = services
    first = ad(w)
    before = w.complex(CID)
    assert detail(m)["analysis"]["status"] == "queued"
    assert detail(m)["priority"]["score"] is None
    assert processor.process(USER)[0]["status"] == "ready"
    result = detail(m)
    assert result["priority"]["score"] == 35
    assert result["confirmedRisk"]["score"] == 0
    assert w.complex(CID) == before
    ad(w, url="https://example.org/other-channel")
    duplicate = detail(m)
    assert duplicate["occurrenceCount"] == 2
    assert duplicate["revisionId"] == result["revisionId"]
    assert processor.process(USER) == [] and len(provider.calls) == 1
    assert m.detail(first.id)["id"] == result["id"]


def test_one_review_changes_factors_atomically_preserves_signal_pdf_and_idempotency(services):
    w, m, processor, _, _ = services
    ad(w)
    processor.process(USER)
    item = detail(m)
    payload = review_payload(item)
    saved = m.review(item["id"], payload, USER)
    assert saved["confirmedRisk"]["score"] == 35
    assert saved["priority"]["score"] == 0 and saved["reviewState"] == "reviewed"
    version = w.complex(CID).version
    count = len(w.store.documents["auditLogs"])
    m.review(item["id"], payload, USER)
    assert w.complex(CID).version == version
    assert len(w.store.documents["auditLogs"]) == count
    assert all(e["reviewer"] == USER.uid for e in w.store.documents["evidence"].values())
    # Backfill of the derived originals must not reopen/recount the group.
    assert detail(m)["occurrenceCount"] == 1
    from app.models.signals import SignalCreate
    from app.services.signals import SignalService

    signal = SignalService(w).create(
        SignalCreate(
            complex_id=CID,
            expected_complex_version=version,
            title="DEMO — материал",
            reason="Проверенные источники",
        ),
        USER,
    )
    assert signal.snapshot.risk.score == 35


def test_stale_and_partial_invalid_reviews_have_no_writes(services):
    w, m, processor, _, _ = services
    ad(w)
    processor.process(USER)
    item = detail(m)
    payload = review_payload(item)
    payload.expected_complex_version += 1
    before = deepcopy(w.store.documents)
    with pytest.raises(Conflict):
        m.review(item["id"], payload, USER)
    assert w.store.documents == before
    # R2 valid but R3 impossible for a commissioned object: even R2 must not commit.
    w.store.documents["complexes"][CID]["stage"] = "commissioned"
    item = detail(m)
    before = deepcopy(w.store.documents)
    with pytest.raises(AppError, match="under construction"):
        m.review(item["id"], review_payload(item), USER)
    assert w.store.documents == before


def test_rejected_duplicates_do_not_reopen_but_new_terms_do(services):
    w, m, processor, provider, _ = services
    original = ad(w)
    processor.process(USER)
    item = detail(m)
    m.review(item["id"], review_payload(item, decision="rejected"), USER)
    ad(w)
    repeated = detail(m)
    assert repeated["reviewState"] == "reviewed" and repeated["priority"]["score"] == 0
    assert processor.process(USER) == [] and len(provider.calls) == 1
    # Same publication, materially changed terms: one card, new revision, new analysis.
    w.store.documents["advertisements"][original.id]["text"] = TEXT + " Новый взнос 250 000 тенге."
    changed = detail(m)
    assert changed["revisionId"] != repeated["revisionId"]
    assert changed["reviewState"] == "needs_review"
    assert changed["occurrenceCount"] == 2
    processor.process(USER)
    assert len(provider.calls) == 2


def test_new_photo_has_own_analysis_private_auth_and_stale_revision(services):
    w, m, processor, provider, files = services
    original = ad(w)
    processor.process(USER)
    item = detail(m)
    payload = review_payload(item)
    upload = files.upload(original.id, original.version, png(), "image/png", USER)
    changed = detail(m)
    assert changed["revisionId"] != item["revisionId"]
    with pytest.raises(Conflict):
        m.review(item["id"], payload, USER)
    processor.process(USER)
    assert len(provider.calls) == 2 and provider.calls[-1][1][0] == png()
    current = detail(m)
    assert any(media["analyzed"] for o in current["occurrences"] for media in o["media"])
    m.review(current["id"], review_payload(current), USER)
    assert files.download(upload.id)[0] == png()


def test_quota_retains_queued_input_and_failed_outcome_requires_explicit_retry(services):
    w, m, processor, provider, _ = services
    ad(w)
    day = utc_now().strftime("%Y%m%d")
    w.store.documents["usageLimits"] = {f"global-{day}": {"id": f"global-{day}", "count": 100}}
    assert processor.process(USER)[0]["errorCode"] == "AI_DAILY_LIMIT"
    queued = detail(m)
    assert (
        queued["analysis"]["status"] == "queued"
        and queued["analysis"]["errorCode"] == "AI_DAILY_LIMIT"
    )
    assert not provider.calls
    w.store.documents["usageLimits"] = {}
    for job in w.store.documents["materialJobs"].values():
        job["nextAttemptAt"] = None
    provider.error = AppError(503, "AI_NETWORK", "private provider text")
    processor.process(USER)
    failed = detail(m)
    assert failed["analysis"]["status"] == "failed"
    processor.process(USER)
    assert len(provider.calls) == 1
    p = MaterialRetry(request_id=uuid4(), expected_version=failed["version"])
    m.retry(failed["id"], p, USER)
    m.retry(failed["id"], p, USER)
    provider.error = None
    processor.process(USER)
    assert detail(m)["analysis"]["status"] == "ready" and len(provider.calls) == 2


def test_concurrent_workers_and_expired_lease_do_not_repeat_unknown_paid_call(services):
    w, m, processor, provider, _ = services
    ad(w)
    started, finish = Event(), Event()
    provider.on_call = lambda: (started.set(), finish.wait(5))
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(processor.process, USER)
        assert started.wait(3)
        assert processor.process(USER) == []
        finish.set()
        future.result()
    assert len(provider.calls) == 1
    job = next(iter(w.store.documents["materialJobs"].values()))
    job.update(status="running", leaseUntil=(utc_now() - timedelta(minutes=1)).isoformat())
    assert processor.process(USER)[0]["errorCode"] == "AI_OUTCOME_UNKNOWN"
    assert len(provider.calls) == 1


def test_live_monitoring_groups_cross_platform_and_never_confirms_demo_registry(services):
    w, m, processor, _, _ = services
    for i, platform in enumerate(["telegram_post", "instagram_ad"]):
        observation = Observation(
            original_url=f"https://example.org/public/{i}",
            text=TEXT,
            content_kind=platform,
            account="DEMO fictitious",
            title="DEMO finding",
        )
        row = observation.model_dump(mode="json", by_alias=True) | {
            "id": f"lead-{i}",
            "createdAt": utc_now().isoformat(),
            "lastSeenAt": utc_now().isoformat(),
        }
        w.store.atomic(lambda tx, row=row: stage_occurrence(tx, monitor_occurrence(row)))
    item = detail(m)
    assert item["origins"] == ["automatic"] and len(item["platforms"]) == 2
    processor.process(USER)
    item = detail(m)
    payload = review_payload(item)
    payload.complex_id = CID
    payload.expected_complex_version = w.complex(CID).version
    with pytest.raises(AppError, match="fictional"):
        m.review(item["id"], payload, USER)
    assert w.complex_detail(CID)["risk"]["score"] == 0


def test_pagination_search_filters_cover_whole_collection_and_cursor_is_bound(services):
    w, m, _, _, _ = services
    for i in range(205):
        ad(w, text=f"DEMO предложение {i:04d}")
    result = m.items(q="0204", origin="manual")
    assert len(result["items"]) == 1
    first = m.items(limit=3)
    second = m.items(limit=3, cursor=first["nextCursor"])
    assert not {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}
    with pytest.raises(Conflict):
        m.items(limit=3, cursor=first["nextCursor"], review="needs_review")
    with pytest.raises(AppError):
        m.items(cursor="bad_cursor")


def test_routes_auto_analyze_and_role_auth_preserved(services):
    w, _, _, provider, files = services
    app = create_app(Settings(_env_file=None, gemini_api_key="", gemini_model="local-test"))
    app.state.material_client, app.state.material_files = provider, files
    app.dependency_overrides[workspace_service] = lambda: w
    with TestClient(app) as client:
        assert client.get("/api/v1/materials").status_code == 401
        app.dependency_overrides[current_user] = lambda: USER
        response = client.post(
            "/api/v1/advertisements",
            json={
                "complexId": CID,
                "platform": "Telegram",
                "account": "DEMO QA",
                "text": TEXT,
                "sourceUrl": "https://example.org/route",
                "publishedAt": utc_now().isoformat(),
            },
        )
        assert response.status_code == 201
        rows = client.get("/api/v1/materials").json()["items"]
        item = client.get("/api/v1/materials/" + rows[0]["id"]).json()
        assert item["analysis"]["status"] == "ready" and len(provider.calls) == 1
        decision = review_payload(item).model_dump(mode="json", by_alias=True)
        reviewed = client.post("/api/v1/materials/" + item["id"] + "/review", json=decision)
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["confirmedRisk"]["score"] == 35
