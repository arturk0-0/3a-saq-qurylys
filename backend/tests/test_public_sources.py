"""Synthetic public pages through MockTransport; never live social ads or real Gemini."""

import gzip

import httpx
import pytest

from app.core.errors import AppError
from app.models.common import utc_now
from app.models.monitoring import MonitorSource
from app.services.public_sources import (
    MAX_BYTES,
    PublicCollector,
    date_or_none,
    normalize_target,
    relevance,
    safe_original_url,
)

TEXT = "DEMO — Өскемен, квартиры в строящемся доме. Внесите депозит 150 000 тенге."


def source(kind="web_search", target="квартиры Өскемен"):
    return MonitorSource(
        id="test-source",
        name="Synthetic QA source",
        kind=kind,
        target=target,
        created_at=utc_now(),
        created_by="test-reviewer",
    )


def rss(text=TEXT, url="https://example.org/ad/1", title="DEMO"):
    return f"""<rss version="2.0"><channel><item><title>{title}</title><link>{url}</link>
    <description><![CDATA[{text}]]></description></item></channel></rss>"""


def telegram(text=TEXT):
    return f"""<html><div class="tgme_widget_message" data-post="saq_demo/42">
    <div class="tgme_widget_message_text js-message_text">{text}<br>Только вымысел.</div>
    <a><time datetime="2026-10-17T10:00:00+00:00"></time></a></div></html>"""


def collector(body, status=200, headers=None):
    return PublicCollector(
        httpx.MockTransport(
            lambda request: httpx.Response(
                status, content=body.encode() if isinstance(body, str) else body, headers=headers
            )
        )
    )


def test_search_fixed_host_query_and_explicit_snippet_unknown_date():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=rss())

    result = PublicCollector(httpx.MockTransport(handler)).fetch(source())
    assert len(requests) == 1 and requests[0].url.host == "www.bing.com"
    assert requests[0].url.params["q"] == source().target
    assert result.items[0].content_kind == "search_snippet"
    assert result.items[0].published_at is None and TEXT in result.items[0].text
    assert len(result.response_sha256) == 64


def test_telegram_visible_text_and_date_without_fetching_links():
    html = telegram(TEXT + ' <a href="http://127.0.0.1/secret">ссылка</a><script>SECRET</script>')
    post = collector(html).fetch(source("telegram", "saq_demo")).items[0]
    assert post.original_url == "https://t.me/saq_demo/42"
    assert TEXT in post.text and "SECRET" not in post.text and "\nТолько вымысел." in post.text
    assert post.published_at.isoformat() == "2026-10-17T10:00:00+00:00"
    assert post.content_kind == "telegram_post"


@pytest.mark.parametrize(
    "target",
    [
        "http://localhost",
        "https://t.me.evil.org/name",
        "https://t.me/saq_demo/42",
        "https://t.me/+private",
        "https://t.me/saq_demo?before=1",
        "../internal",
        "@ab",
    ],
)
def test_telegram_target_rejects_arbitrary_or_private_urls(target):
    with pytest.raises(AppError):
        normalize_target("telegram", target)


@pytest.mark.parametrize(
    "target", ["@saq_demo", "SAQ_DEMO", "https://t.me/saq_demo", "https://t.me/s/saq_demo"]
)
def test_public_telegram_target_is_canonical(target):
    assert normalize_target("telegram", target) == "saq_demo"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/",
        "https://u:p@example.org/",
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://metadata.google.internal/",
        "https://example.org:8000/",
        "javascript:alert(1)",
    ],
)
def test_original_links_safe_metadata_never_fetch_targets(url):
    assert safe_original_url(url) is None


def test_canonical_url_keeps_meaningful_query_not_tracking():
    assert (
        safe_original_url("https://EXAMPLE.org/ad?id=1&utm_source=ad#tracking")
        == "https://example.org/ad?id=1"
    )


@pytest.mark.parametrize("status", [301, 302, 401, 403, 429, 500])
def test_redirects_blocks_provider_errors_do_not_follow_or_leak(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, headers={"Location": "http://127.0.0.1/private"}, text="PRIVATE provider error"
        )

    with pytest.raises(AppError) as error:
        PublicCollector(httpx.MockTransport(handler)).fetch(source())
    assert len(calls) == 1
    assert "PRIVATE" not in str(error.value) and "127.0.0.1" not in str(error.value)


def test_expanded_response_bytes_limit():
    body = gzip.compress(b"x" * (MAX_BYTES + 1))
    with pytest.raises(AppError) as error:
        collector(body, headers={"Content-Encoding": "gzip"}).fetch(source())
    assert error.value.code == "MONITOR_SOURCE_SIZE"


@pytest.mark.parametrize(
    "body",
    [
        "<html>login or challenge</html>",
        "<!DOCTYPE rss [<!ENTITY e 'bomb'>]><rss><channel/></rss>",
        "<rss><channel>",
    ],
)
def test_feed_dtd_challenge_and_malformed_xml_fail(body):
    with pytest.raises(AppError) as error:
        collector(body).fetch(source())
    assert error.value.code == "MONITOR_SOURCE_FORMAT"


def test_empty_search_differs_from_unreadable_telegram():
    assert collector("<rss><channel/></rss>").fetch(source()).items == []
    with pytest.raises(AppError):
        collector("<html>channel unavailable</html>").fetch(source("telegram", "saq_demo"))


def test_lexical_match_explained_not_legal_score():
    region, housing, payment = relevance(TEXT)
    assert "өскемен" in region and "квартир" in housing and "депозит" in payment
    assert not relevance("DEMO квартиры в Алматы")[0]
    assert date_or_none("unknown") is None and date_or_none("2026-10-17T10:00:00") is None
