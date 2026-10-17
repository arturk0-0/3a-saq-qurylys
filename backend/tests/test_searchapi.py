"""Synthetic SearchAPI replies only. No real keys, provider quota or third-party ad copy."""

import gzip
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import AppError
from app.models.auth import Principal
from app.models.common import utc_now
from app.models.monitoring import ItemReview, MonitorSource, SourceInput
from app.services.monitoring import MonitoringService
from app.services.public_sources import PublicCollector
from app.services.searchapi import SearchApiCollector, parse_ads
from app.services.seed_data import build_demo_seed
from app.services.workspace import WorkspaceService
from tests.fakes import MemoryStore

TEXT = "DEMO — Өскемен, квартиры в строящемся доме. Внесите депозит 150 000 тенге."
USER = Principal(uid="meta-qa-reviewer", role="analyst")
KEY = "synthetic-not-a-real-key"


def settings(**kwargs):
    return Settings(_env_file=None, searchapi_api_key=KEY, searchapi_enabled=True, **kwargs)


def source():
    return MonitorSource(
        id="qa-source",
        name="Synthetic Meta source",
        kind="instagram_ads",
        target="квартиры Өскемен",
        created_at=utc_now(),
        created_by=USER.uid,
    )


def ad(**changes):
    row = {
        "ad_archive_id": "100000000000001",
        "is_active": True,
        "publisher_platform": ["FACEBOOK", "INSTAGRAM"],
        "start_date": "2026-10-15T07:00:00Z",
        "snapshot": {
            "page_name": "DEMO fictional advertiser",
            "body": {"text": TEXT},
            "cards": [],
            "images": [{"original_image_url": "https://cdn.example.org/demo.jpg?sig=a"}],
            "videos": [
                {
                    "video_hd_url": "https://cdn.example.org/demo.mp4",
                    "video_preview_image_url": "https://cdn.example.org/preview.jpg",
                }
            ],
        },
    }
    row.update(changes)
    return row


def client(rows=None, credits=100, hook=None, code=200, payload=None):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "www.searchapi.io"
        assert request.headers["authorization"] == "Bearer " + KEY
        assert "api_key" not in request.url.params
        if request.url.path.endswith("/me"):
            if hook:
                hook()
            return httpx.Response(200, json={"account": {"remaining_credits": credits}})
        assert dict(request.url.params) == {
            "engine": "meta_ad_library",
            "q": request.url.params["q"],
            "country": "KZ",
            "platforms": "instagram",
            "ad_type": "all",
            "active_status": "active",
        }
        return httpx.Response(
            code,
            json=payload
            if payload is not None
            else {
                "ads": rows if rows is not None else [ad()],
            },
        )

    return SearchApiCollector(settings(), httpx.MockTransport(handler)), calls


def service(collector=None, **kw):
    c, calls = client() if collector is None else collector
    config = settings(**kw)
    monitor = MonitoringService(
        WorkspaceService(MemoryStore(build_demo_seed())),
        config,
        c,
    )
    return monitor, calls


def create(monitor, target="квартиры Өскемен"):
    return monitor.create_source(
        SourceInput(name="DEMO Meta source", kind="instagram_ads", target=target),
        USER,
    )


def error_code(action, code):
    with pytest.raises(AppError) as raised:
        action()
    assert raised.value.code == code
    assert KEY not in raised.value.message
    return raised.value


def test_real_meta_engine_not_google_preserves_copy_dates_platforms_and_media():
    collector, calls = client()
    result = collector.fetch(source())
    item = result.items[0]
    assert [r.url.path for r in calls] == ["/api/v1/me", "/api/v1/search"]
    assert item.text == TEXT and item.content_kind == "instagram_ad"
    assert item.ad_archive_id == "100000000000001"
    assert (
        item.published_at is None and item.ad_started_at.isoformat() == "2026-10-15T07:00:00+00:00"
    )
    assert item.ad_active is True and "INSTAGRAM" in item.platforms
    assert len(item.media) == 3 and result.provider_credits_before == 100
    assert len(result.response_sha256) == 64
    assert "facebook.com/ads/library/" in result.discovery_url


@pytest.mark.parametrize("remaining", [0, 19, 20])
def test_twenty_credit_reserve_prevents_any_search(remaining):
    collector, calls = client(credits=remaining)
    error_code(lambda: collector.fetch(source()), "SEARCHAPI_RESERVE")
    assert len(calls) == 1 and calls[0].url.path.endswith("/me")


def test_one_credit_above_reserve_allows_only_one_page():
    collector, calls = client(
        credits=21,
        payload={
            "ads": [ad()],
            "pagination": {"next_page_token": "opaque-test-only-token"},
        },
    )
    result = collector.fetch(source())
    assert result.limited and len(calls) == 2


def test_missing_or_disabled_key_stops_before_network():
    collector, calls = client()
    collector.settings.searchapi_enabled = False
    error_code(lambda: collector.fetch(source()), "SEARCHAPI_DISABLED")
    collector.settings.searchapi_enabled = True
    collector.settings.searchapi_api_key = Settings(searchapi_api_key="").searchapi_api_key
    error_code(lambda: collector.fetch(source()), "SEARCHAPI_NOT_CONFIGURED")
    assert calls == []
    with pytest.raises(ValidationError):
        settings(searchapi_credit_reserve=19)


@pytest.mark.parametrize("credits", [None, "100", True, -1])
def test_unknown_balance_fails_closed_without_search(credits):
    collector, calls = client(credits=credits)
    error_code(lambda: collector.fetch(source()), "SEARCHAPI_FORMAT")
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "SEARCHAPI_CREDENTIALS"),
        (403, "SEARCHAPI_CREDENTIALS"),
        (429, "SEARCHAPI_QUOTA"),
        (500, "SEARCHAPI_TEMPORARY"),
        (302, "SEARCHAPI_TEMPORARY"),
    ],
)
def test_provider_errors_are_safe_and_never_retried(status, code):
    collector, calls = client(code=status, payload={"error": KEY + " PRIVATE"})
    error_code(lambda: collector.fetch(source()), code)
    assert len(calls) == 2


def test_carousel_templates_and_unsafe_media_are_not_invented_copy_or_fetches():
    row = ad()
    row["snapshot"] = {
        "body": {"text": "{{product.name}}"},
        "page_name": "DEMO",
        "cards": [
            {
                "title": "DEMO квартиры Өскемен",
                "body": "Внесите депозит.",
                "link_description": "Тест",
                "original_image_url": "http://localhost/private",
            }
        ],
        "images": [{"original_image_url": "https://127.0.0.1/private"}],
        "videos": [{"video_hd_url": "javascript:alert(1)"}],
    }
    result = parse_ads({"ads": [row]}, "f" * 64, "QA", 100)
    item = result.items[0]
    assert item.text == "DEMO квартиры Өскемен\n\nВнесите депозит.\n\nТест"
    assert not item.media and "{{" not in item.text


def test_inactive_other_platform_malformed_and_media_only_ads_are_counted_not_fabricated():
    result = parse_ads(
        {
            "ads": [
                ad(),
                ad(is_active=False),
                ad(publisher_platform=["FACEBOOK"]),
                ad(snapshot={"body": None}),
                ad(ad_archive_id="bad?x"),
                ad(snapshot=None),
                None,
            ]
        },
        "f" * 64,
        "QA",
        100,
    )
    assert result.fetched_count == 7 and len(result.items) == 1 and result.unreadable == 6


def test_empty_success_is_distinct_from_missing_or_error_payload():
    assert parse_ads({"ads": []}, "f" * 64, "QA", 100).items == []
    assert parse_ads({"search_information": {"total_results": 0}}, "f" * 64, "QA", 100).items == []
    for payload in [{}, {"error": "private"}, {"ads": "bad"}]:
        error_code(
            lambda payload=payload: parse_ads(payload, "f" * 64, "QA", 100), "SEARCHAPI_FORMAT"
        )


def test_one_page_and_media_limits_are_explicit():
    rows = [ad(ad_archive_id=str(1000 + n)) for n in range(35)]
    result = parse_ads({"ads": rows}, "f" * 64, "QA", 100)
    assert len(result.items) == 30 and result.fetched_count == 35 and result.limited
    with pytest.raises(AppError):
        PublicCollector().fetch(source())


def test_size_decompression_bad_json_and_network_errors_are_safe():
    def oversized(r):
        return httpx.Response(
            200, content=gzip.compress(b"x" * 2_000_001), headers={"Content-Encoding": "gzip"}
        )

    collector = SearchApiCollector(settings(), httpx.MockTransport(oversized))
    error_code(lambda: collector.fetch(source()), "SEARCHAPI_SIZE")
    for exception, expected in [
        (httpx.ConnectTimeout(KEY), "SEARCHAPI_TIMEOUT"),
        (httpx.ConnectError(KEY), "SEARCHAPI_NETWORK"),
    ]:

        def network(r, exception=exception):
            raise exception

        c = SearchApiCollector(settings(), httpx.MockTransport(network))
        error_code(lambda c=c: c.fetch(source()), expected)
    c = SearchApiCollector(
        settings(), httpx.MockTransport(lambda r: httpx.Response(200, text="not JSON"))
    )
    error_code(lambda: c.fetch(source()), "SEARCHAPI_FORMAT")


def test_scheduled_calls_are_opt_in_and_day_limit_is_shared_across_sources():
    monitor, calls = service(searchapi_daily_limit=1)
    one = create(monitor)
    two = create(monitor, "квартиры Риддер")
    assert monitor.run_due(USER) == [] and calls == []
    before = deepcopy(monitor.workspace.complex_detail("demo-complex-01"))
    result = monitor.run(one["id"], USER)
    assert result["providerCreditsBefore"] == 100 and result["fetched"] == 1
    error_code(lambda: monitor.run(two["id"], USER), "SEARCHAPI_DAILY_LIMIT")
    assert len(calls) == 2 and monitor.workspace.complex_detail("demo-complex-01") == before
    status = monitor.status()
    assert status["instagramTargetedAds"] == "configured"
    assert status["searchApi"]["dailyUsed"] == 1 and status["searchApi"]["creditReserve"] == 20
    assert status["searchApi"]["creditsObservedBefore"] == 100


def test_shared_provider_lease_prevents_concurrent_account_checks_and_searches():
    entered, finish = Event(), Event()

    def hold():
        entered.set()
        assert finish.wait(5)

    monitor, calls = service(client(hook=hold))
    one = create(monitor)
    two = create(monitor, "квартиры Риддер")
    with ThreadPoolExecutor(2) as pool:
        future = pool.submit(monitor.run, one["id"], USER)
        assert entered.wait(5)
        try:
            error_code(lambda: monitor.run(two["id"], USER), "SEARCHAPI_BUSY")
            assert len(calls) == 1
        finally:
            finish.set()
        assert future.result()["created"] == 1
    assert monitor.store.get("monitorLimits", "searchapi")["activeRunId"] is None


def test_provider_lock_released_on_balance_error_and_attempt_quota_not_refunded():
    monitor, calls = service(client(credits=20))
    one = create(monitor)
    error_code(lambda: monitor.run(one["id"], USER), "SEARCHAPI_RESERVE")
    assert len(calls) == 1
    assert monitor.store.get("monitorLimits", "searchapi")["activeRunId"] is None
    assert monitor.runs()["items"][0]["errorCode"] == "SEARCHAPI_RESERVE"
    assert monitor.status()["searchApi"]["dailyUsed"] == 1


def test_creative_revision_ignores_rotating_signature_and_keeps_human_notes():
    monitor, _ = service(searchapi_daily_limit=5)
    one = create(monitor)
    monitor.run(one["id"], USER)
    first = monitor.items()["items"][0]
    monitor.review(
        first["id"], ItemReview(expected_version=1, decision="investigating", notes="QA"), USER
    )
    changed = ad()
    changed["snapshot"]["images"][0]["original_image_url"] = (
        "https://other.example.org/demo.jpg?sig=b"
    )
    monitor.collector = client([changed])[0]
    monitor.store.documents["monitorSources"][one["id"]]["nextRunAt"] = None
    assert monitor.run(one["id"], USER)["duplicates"] == 1
    changed["snapshot"]["images"][0]["original_image_url"] = (
        "https://cdn.example.org/new-creative.jpg"
    )
    monitor.collector = client([changed])[0]
    monitor.store.documents["monitorSources"][one["id"]]["nextRunAt"] = None
    assert monitor.run(one["id"], USER)["created"] == 1
    assert monitor.item(first["id"]).notes == "QA" and len(monitor.items()["items"]) == 2


def test_lost_lease_after_account_check_prevents_search():
    holder = {}

    def steal():
        state = holder["monitor"].store.documents["monitorLimits"]["searchapi"]
        state["activeRunId"] = "new-owner"

    monitor, calls = service(client(hook=steal))
    holder["monitor"] = monitor
    one = create(monitor)
    error_code(lambda: monitor.run(one["id"], USER), "SEARCHAPI_BUSY")
    assert len(calls) == 1
    assert monitor.store.get("monitorLimits", "searchapi")["activeRunId"] == "new-owner"


def test_unknown_search_outcome_keeps_conservative_reservation():
    def provider(request):
        if request.url.path.endswith("/me"):
            return httpx.Response(200, json={"account": {"remaining_credits": 21}})
        raise httpx.ReadTimeout("synthetic unknown billing outcome")

    collector = SearchApiCollector(settings(), httpx.MockTransport(provider))
    monitor, _ = service((collector, []))
    one = create(monitor)
    error_code(lambda: monitor.run(one["id"], USER), "SEARCHAPI_TIMEOUT")
    state = monitor.store.get("monitorLimits", "searchapi")
    assert len(state["pendingSearches"]) == 1 and state["activeRunId"] is None
    another, calls = client(credits=21)
    monitor.collector = another
    two = create(monitor, "квартиры Риддер")
    error_code(lambda: monitor.run(two["id"], USER), "SEARCHAPI_RESERVE")
    assert len(calls) == 1  # Only account call; reserve also covers the unknown prior request.


def test_stale_finished_worker_cannot_release_new_provider_lease():
    monitor, _ = service()
    one = create(monitor)
    two = create(monitor, "квартиры Риддер")
    source_one, old = monitor._reserve(one["id"], USER)
    monitor.store.documents["monitorLimits"]["searchapi"]["leaseUntil"] = "2000-01-01T00:00:00Z"
    _, new = monitor._reserve(two["id"], USER)
    old.status = "failed"
    monitor._finish(source_one, old)
    assert monitor.store.get("monitorLimits", "searchapi")["activeRunId"] == new.id
