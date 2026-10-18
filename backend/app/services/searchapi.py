"""SearchAPI Meta Ad Library: one authenticated page, never Google SERP or media fetch."""

import hashlib
import json
import re
import time
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.core.errors import AppError
from app.models.monitoring import MediaReference, MonitorSource, Observation
from app.services.public_sources import (
    MAX_ITEMS,
    FetchResult,
    PublicCollector,
    date_or_none,
    normalize_target,
    safe_original_url,
)

ENDPOINT = "https://www.searchapi.io/api/v1/"
MAX_RESPONSE_BYTES = 2_000_000


def fail(code: str, status: int = 503):
    raise AppError(status, code, "Meta ad provider request could not be completed")


def ad_text(snapshot: dict) -> str:
    """Join actual copy/card fields; unresolved product templates are not ad copy."""
    parts = []
    body = snapshot.get("body")
    candidates = [body.get("text") if isinstance(body, dict) else body]
    cards = snapshot.get("cards")
    if isinstance(cards, list):
        for card in cards[:30]:
            if not isinstance(card, dict):
                continue
            candidates.extend(card.get(key) for key in ("title", "body", "link_description"))
    for text in candidates:
        if isinstance(text, str) and text.strip() and not re.search(r"\{\{.*?\}\}", text):
            if text not in parts:
                parts.append(text)
    return "\n\n".join(parts)


def media_references(snapshot: dict) -> list[MediaReference]:
    refs, seen = [], set()

    def add(kind, value):
        if not isinstance(value, str):
            return
        url = safe_original_url(value)
        if url and len(refs) < 12 and (kind, url) not in seen:
            refs.append(MediaReference(kind=kind, url=url))
            seen.add((kind, url))

    for field in ("images", "videos", "cards"):
        rows = snapshot.get(field)
        if not isinstance(rows, list):
            continue
        for row in rows[:30]:
            if not isinstance(row, dict):
                continue
            add("image", row.get("original_image_url") or row.get("resized_image_url"))
            add("video", row.get("video_hd_url") or row.get("video_sd_url"))
            add("thumbnail", row.get("video_preview_image_url"))
    return refs


def parse_ads(data: dict, response_sha256: str, query: str, credits: int) -> FetchResult:
    rows = data.get("ads")
    info = data.get("search_information")
    if rows is None and isinstance(info, dict) and info.get("total_results") == 0:
        rows = []
    if not isinstance(rows, list) or data.get("error"):
        fail("SEARCHAPI_FORMAT", 502)
    items, unreadable = [], 0
    for row in rows[:MAX_ITEMS]:
        if not isinstance(row, dict):
            unreadable += 1
            continue
        platforms = row.get("publisher_platform")
        if not isinstance(platforms, list):
            unreadable += 1
            continue
        platforms = [x.upper() for x in platforms if isinstance(x, str) and len(x) <= 40][:10]
        # Provider filters are verified per item; other publishers alone do not qualify.
        if "INSTAGRAM" not in platforms or row.get("is_active") is not True:
            unreadable += 1
            continue
        ad_id, snapshot = row.get("ad_archive_id"), row.get("snapshot")
        if not isinstance(ad_id, str) or not re.fullmatch(r"[0-9]{1,40}", ad_id):
            unreadable += 1
            continue
        if not isinstance(snapshot, dict):
            unreadable += 1
            continue
        text = ad_text(snapshot)
        if not text.strip() or len(text) > 20000:
            unreadable += 1
            continue
        account = snapshot.get("page_name") or row.get("page_name") or ""
        if not isinstance(account, str):
            account = ""
        started = row.get("start_date")
        items.append(
            Observation(
                original_url=f"https://www.facebook.com/ads/library/?id={ad_id}",
                title=account[:500],
                text=text,
                # Campaign start is NOT the original Instagram post publication date.
                published_at=None,
                content_kind="instagram_ad",
                account=account[:500],
                ad_archive_id=ad_id,
                ad_started_at=date_or_none(started) if isinstance(started, str) else None,
                ad_active=True,
                platforms=platforms,
                media=media_references(snapshot),
            )
        )
    pagination = data.get("pagination")
    more = bool(isinstance(pagination, dict) and pagination.get("next_page_token"))
    more = more or bool(
        isinstance(info, dict)
        and isinstance(info.get("total_results"), int)
        and info["total_results"] > len(rows)
    )
    discovery = "https://www.facebook.com/ads/library/?" + urlencode(
        {"country": "KZ", "ad_type": "all", "active_status": "active", "q": query}
    )
    return FetchResult(
        items,
        discovery,
        response_sha256,
        more or len(rows) > MAX_ITEMS,
        fetched_count=len(rows),
        unreadable=unreadable,
        provider_credits_before=credits,
    )


class SearchApiCollector:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings, self.transport = settings, transport

    def check_config(self):
        if not self.settings.searchapi_enabled:
            fail("SEARCHAPI_DISABLED")
        if not self.settings.searchapi_api_key.get_secret_value():
            fail("SEARCHAPI_NOT_CONFIGURED")

    def _get(self, client, path, params=None) -> tuple[dict, str]:
        deadline = time.monotonic() + 85
        try:
            with client.stream("GET", ENDPOINT + path, params=params) as response:
                if response.status_code in {401, 403}:
                    fail("SEARCHAPI_CREDENTIALS")
                if response.status_code == 429:
                    fail("SEARCHAPI_QUOTA", 429)
                if not response.is_success:
                    fail("SEARCHAPI_TEMPORARY")
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                        fail("SEARCHAPI_SIZE", 502)
                    if time.monotonic() > deadline:
                        fail("SEARCHAPI_TIMEOUT")
                    body.extend(chunk)
        except httpx.TimeoutException:
            fail("SEARCHAPI_TIMEOUT")
        except httpx.HTTPError:
            fail("SEARCHAPI_NETWORK")
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError):
            fail("SEARCHAPI_FORMAT", 502)
        if not isinstance(data, dict):
            fail("SEARCHAPI_FORMAT", 502)
        return data, hashlib.sha256(body).hexdigest()

    def fetch(self, source: MonitorSource, before_search=None) -> FetchResult:
        self.check_config()
        query = normalize_target("instagram_ads", source.target)
        # Fixed host; key is only in Authorization, never a URL, log or persisted body.
        with httpx.Client(
            headers={
                "Authorization": "Bearer " + self.settings.searchapi_api_key.get_secret_value()
            },
            timeout=httpx.Timeout(80, connect=5),
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            account, _ = self._get(client, "me")
            usage = account.get("account")
            credits = usage.get("remaining_credits") if isinstance(usage, dict) else None
            if type(credits) is not int or credits < 0:
                fail("SEARCHAPI_FORMAT", 502)
            if credits <= self.settings.searchapi_credit_reserve:
                fail("SEARCHAPI_RESERVE", 429)
            if before_search:
                before_search(credits)
            data, digest = self._get(
                client,
                "search",
                {
                    "engine": "meta_ad_library",
                    "q": query,
                    "country": "KZ",
                    "platforms": "instagram",
                    "ad_type": "all",
                    "active_status": "active",
                },
            )
        # Never follow pagination, fetch creatives or automatically retry.
        return parse_ads(data, digest, query, credits)


class MonitoringCollector:
    """Dispatch without letting a new source silently become a generic web search."""

    def __init__(self, settings: Settings):
        self.public, self.instagram = PublicCollector(), SearchApiCollector(settings)

    def fetch(self, source: MonitorSource, before_search=None) -> FetchResult:
        if source.kind == "instagram_ads":
            return self.instagram.fetch(source, before_search=before_search)
        return self.public.fetch(source)
