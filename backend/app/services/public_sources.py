"""Bounded public discovery adapters. No cookies, arbitrary fetch, redirects or login."""

import hashlib
import re
import time
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree

import httpx

from app.core.errors import AppError
from app.models.monitoring import MonitorSource, Observation

MAX_BYTES = 1_500_000
MAX_ITEMS = 30


def normalize_target(kind: str, target: str) -> str:
    target = target.strip()
    if kind == "web_search":
        if not target or len(target) > 250 or any(ord(c) < 32 for c in target):
            raise AppError(422, "MONITOR_SOURCE_INVALID", "Enter a public search query")
        return target
    if target.startswith("https://t.me/"):
        parts = urlsplit(target)
        if parts.query or parts.fragment:
            raise AppError(422, "MONITOR_SOURCE_INVALID", "Enter a public Telegram channel")
        target = parts.path.removeprefix("/s/").strip("/")
    target = target.removeprefix("@")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", target):
        raise AppError(422, "MONITOR_SOURCE_INVALID", "Enter a public Telegram channel")
    return target.lower()


def safe_original_url(value: str) -> str | None:
    try:
        p = urlsplit(value)
        host = (p.hostname or "").lower()
        if (
            p.scheme != "https"
            or p.username is not None
            or p.password is not None
            or p.port not in (None, 443)
            or not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host)
            or host.endswith((".local", ".internal", ".localhost", ".invalid"))
            or re.fullmatch(r"[0-9.]+", host)
            or len(value) > 2000
        ):
            return None
        query = urlencode(
            [
                (k, v)
                for k, v in parse_qsl(p.query, keep_blank_values=True)
                if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
            ]
        )
        return urlunsplit(("https", host, p.path or "/", query, ""))
    except ValueError:
        return None


def date_or_none(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            result = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return None
    return result if result.tzinfo is not None else None


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag == "br" and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div"} and not self.hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(html: str) -> str:
    parser = PlainText()
    parser.feed(html)
    return "".join(parser.parts).strip()


class TelegramPage(HTMLParser):
    def __init__(self, channel: str):
        super().__init__(convert_charrefs=True)
        self.channel = channel
        self.stack: list[tuple[str, bool]] = []
        self.current: dict | None = None
        self.text: list[str] = []
        self.items: list[Observation] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        post = a.get("data-post", "")
        if not self.current and re.fullmatch(re.escape(self.channel) + r"/[0-9]+", post, re.I):
            self.current = {"post": post, "depth": len(self.stack), "date": None}
            self.text = []
        in_text = "tgme_widget_message_text" in a.get("class", "").split()
        inherited = bool(self.stack and self.stack[-1][1])
        if self.current and tag == "time":
            self.current["date"] = a.get("datetime")
        if tag == "br" and (inherited or in_text):
            self.text.append("\n")
        if tag not in {"br", "img", "meta", "link", "hr", "input", "wbr", "source"}:
            if len(self.stack) >= 256:
                raise AppError(502, "MONITOR_SOURCE_FORMAT", "Source nesting exceeds the limit")
            self.stack.append((tag, (inherited or in_text) and tag not in {"script", "style"}))

    def handle_endtag(self, tag):
        index = next(
            (i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i][0] == tag), None
        )
        if index is None:
            return
        if self.current and index <= self.current["depth"]:
            text = "".join(self.text).strip()
            if text and len(text) <= 20000 and len(self.items) < MAX_ITEMS:
                self.items.append(
                    Observation(
                        original_url=f"https://t.me/{self.current['post']}",
                        text=text,
                        published_at=date_or_none(self.current["date"]),
                        content_kind="telegram_post",
                        account=self.channel,
                    )
                )
            self.current = None
        del self.stack[index:]

    def handle_data(self, data):
        if self.current and self.stack and self.stack[-1][1]:
            self.text.append(data)


@dataclass(frozen=True)
class FetchResult:
    items: list[Observation]
    discovery_url: str
    response_sha256: str
    limited: bool


class PublicCollector:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        self.transport = transport

    def fetch(self, source: MonitorSource) -> FetchResult:
        target = normalize_target(source.kind, source.target)
        url = (
            "https://www.bing.com/search?" + urlencode({"format": "rss", "q": target})
            if source.kind == "web_search"
            else f"https://t.me/s/{target}"
        )
        try:
            deadline = time.monotonic() + 20
            with (
                httpx.Client(
                    timeout=httpx.Timeout(12, connect=4),
                    follow_redirects=False,
                    transport=self.transport,
                    headers={
                        "User-Agent": "SAQ-QURYLYS/1.0 PublicSourceMonitor",
                        "Accept": "text/html, application/rss+xml, application/xml",
                    },
                ) as client,
                client.stream("GET", url) as response,
            ):
                if response.status_code in {401, 403, 429}:
                    raise AppError(
                        503,
                        "MONITOR_SOURCE_BLOCKED",
                        "Source blocked access or rate limited collection",
                    )
                if not response.is_success:
                    raise AppError(503, "MONITOR_SOURCE_HTTP", "Source unavailable or redirected")
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    if time.monotonic() > deadline:
                        raise AppError(
                            503, "MONITOR_SOURCE_TIMEOUT", "Collection time limit exceeded"
                        )
                    if len(body) + len(chunk) > MAX_BYTES:
                        raise AppError(
                            502,
                            "MONITOR_SOURCE_SIZE",
                            "Source response exceeds the collection limit",
                        )
                    body.extend(chunk)
        except httpx.HTTPError:
            raise AppError(503, "MONITOR_SOURCE_NETWORK", "Public source request failed") from None
        digest = hashlib.sha256(body).hexdigest()
        html = bytes(body).decode("utf-8", errors="replace")
        if source.kind == "telegram":
            parser = TelegramPage(target)
            parser.feed(html)
            if not parser.items:
                raise AppError(
                    502,
                    "MONITOR_SOURCE_FORMAT",
                    "No readable public posts; channel may be unavailable",
                )
            return FetchResult(parser.items, url, digest, len(parser.items) == MAX_ITEMS)
        if re.search(r"<!\s*(DOCTYPE|ENTITY)", html, re.I):
            raise AppError(502, "MONITOR_SOURCE_FORMAT", "Unsupported feed structure")
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError:
            raise AppError(
                502, "MONITOR_SOURCE_FORMAT", "Search provider did not return a readable feed"
            ) from None
        if root.tag != "rss" or root.find("channel") is None:
            raise AppError(502, "MONITOR_SOURCE_FORMAT", "Search provider did not return RSS")
        rows = root.findall("./channel/item")
        items = []
        for row in rows[:MAX_ITEMS]:
            original = safe_original_url(unescape(row.findtext("link", "")))
            title = plain_text(row.findtext("title", ""))[:500]
            description = plain_text(row.findtext("description", ""))
            text = f"{title}\n{description}".strip()
            if original and text and len(text) <= 20000:
                items.append(
                    Observation(
                        original_url=original,
                        title=title,
                        text=text,
                        published_at=date_or_none(row.findtext("pubDate")),
                        content_kind="search_snippet",
                        account=urlsplit(original).hostname or "",
                    )
                )
        return FetchResult(items, url, digest, len(rows) > MAX_ITEMS)


REGION_TERMS = (
    "усть-каменогорск",
    "усть каменогорск",
    "оскемен",
    "өскемен",
    "риддер",
    "шемонаих",
    "зайсан",
    "серебрянск",
    "вко",
    "шығыс қазақстан",
    "восточно-казахстан",
    "алтай",
)
HOUSING_TERMS = (
    "новострой",
    "строящ",
    "квартир",
    "жилой комплекс",
    "жк ",
    "тұрғын",
    "пәтер",
    "құрылыс",
    "салынып",
)
PAYMENT_TERMS = (
    "брон",
    "депозит",
    "взнос",
    "задаток",
    "бронир",
    "жарна",
    "төлем",
    "алдын ала",
    "резерв",
)


def relevance(text: str) -> tuple[list[str], list[str], list[str]]:
    lowered = text.casefold()
    return tuple(
        [word for word in terms if word in lowered]
        for terms in (REGION_TERMS, HOUSING_TERMS, PAYMENT_TERMS)
    )
