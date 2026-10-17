"""Bounded, offline advertising-link proposals. No network, persistence or risk decisions.

Offsets refer to Python string/code-point positions in the exact original text,
not UTF-16 offsets for a browser. A match is never evidence of common ownership.
"""

import hashlib
import ipaddress
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Literal
from urllib.parse import parse_qs, unquote, urlsplit

from app.services.matching import normalized_name

TRACE_VERSION = "ad-trace-v1"
MAX_TEXT = 20000
MAX_DOCUMENTS = 200
MAX_NAMES = 100
MAX_OCCURRENCES = 100
MAX_PROPOSALS = 200
Kind = Literal["phone", "domain", "alias"]
_PHONE = re.compile(r"(?<![\w+])(?:\+7|7|8)(?:[ \t\u00a0\u202f().\-–—]*[0-9]){10}(?!\w)")
_URL = re.compile(
    r"(?<![\w@])(?:https?://|www\.|wa\.me/|(?:api\.)?whatsapp\.com/)[^\s<>\"«»]+", re.I
)
_DOMAIN = re.compile(
    r"(?<![\w@/])(?:[^\W_](?:[^\W_]|-){0,62}\.)+[^\W\d_]{2,63}"
    r"(?:/[^\s<>\"«»]*)?(?![\w-])",
    re.I,
)
_WORD = re.compile(r"[^\W_]+")
# A common publishing/contact platform is not a shared advertiser website.
_PLATFORM_DOMAINS = frozenset(
    {
        "instagram.com",
        "facebook.com",
        "fb.com",
        "t.me",
        "telegram.me",
        "telegram.org",
        "wa.me",
        "whatsapp.com",
        "api.whatsapp.com",
        "web.whatsapp.com",
        "tiktok.com",
        "youtube.com",
        "youtu.be",
        "vk.com",
        "krisha.kz",
        "olx.kz",
    }
)


@dataclass(frozen=True, slots=True)
class TraceDocument:
    id: str
    text: str
    version: int = 1
    demo: bool = True


@dataclass(frozen=True, slots=True)
class Occurrence:
    kind: Kind
    normalized: str
    quote: str
    start: int
    end: int
    origin: Literal["text", "whatsapp_url", "website_url", "known_name"]


@dataclass(frozen=True, slots=True)
class Identifiers:
    occurrences: tuple[Occurrence, ...]
    limited: bool


@dataclass(frozen=True, slots=True)
class SharedIdentifier:
    kind: Kind
    normalized: str
    left: tuple[Occurrence, ...]
    right: tuple[Occurrence, ...]


@dataclass(frozen=True, slots=True)
class TraceProposal:
    left_id: str
    right_id: str
    left_version: int
    right_version: int
    left_text_sha256: str
    right_text_sha256: str
    demo: bool
    matches: tuple[SharedIdentifier, ...]
    # An alias alone is a weak clue; even a shared contact needs human review.
    name_only: bool


@dataclass(frozen=True, slots=True)
class TraceResult:
    proposals: tuple[TraceProposal, ...]
    identifiers_limited: bool
    proposals_limited: bool
    version: str = TRACE_VERSION


def normalize_phone(value: str) -> str | None:
    """Only explicit 11-digit +7/7/8 forms, no guesses from local seven-digit numbers."""
    if not re.fullmatch(r"\+?[0-9 \t\u00a0\u202f().\-–—]+", value):
        return None
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) != 11 or digits[0] not in "78" or (value.startswith("+") and digits[0] != "7"):
        return None
    return "+7" + digits[1:]


def _url(value: str):
    if any(ord(char) < 32 for char in value) or "\\" in value:
        return None
    try:
        parsed = urlsplit(value if "://" in value else "https://" + value)
        if parsed.scheme.lower() not in {"http", "https"} or parsed.username is not None:
            return None
        if not parsed.hostname or parsed.port == 0:
            return None
        return parsed
    except ValueError:
        return None


def normalize_domain(value: str) -> str | None:
    """Canonical full host, never eTLD guesses, URL fetching or cross-script transliteration."""
    parsed = _url(value)
    if parsed is None:
        return None
    try:
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    if host.startswith("www."):
        host = host[4:]
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    labels = host.split(".")
    if len(host) > 253 or len(labels) < 2 or labels[-1].isdigit():
        return None
    if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels):
        return None
    if host.endswith((".localhost", ".local", ".internal")):
        return None
    return host


def normalize_whatsapp(value: str) -> str | None:
    parsed = _url(value)
    host = normalize_domain(value)
    if parsed is None:
        return None
    if host == "wa.me":
        phone = unquote(parsed.path.strip("/"))
    elif host in {"api.whatsapp.com", "whatsapp.com"} and parsed.path.rstrip("/") == "/send":
        values = parse_qs(parsed.query).get("phone", [])
        if len(values) != 1:
            return None
        phone = values[0]
    else:
        return None
    return normalize_phone(phone)


def _platform(host: str) -> bool:
    return any(host == platform or host.endswith("." + platform) for platform in _PLATFORM_DOMAINS)


def extract_identifiers(text: str, *, known_names: Sequence[str] = ()) -> Identifiers:
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        raise ValueError("Trace text exceeds the supported input limit")
    if len(known_names) > MAX_NAMES or any(
        not isinstance(n, str) or len(n) > 500 for n in known_names
    ):
        raise ValueError("Trace names exceed the supported input limit")
    found: list[Occurrence] = []
    url_spans: list[tuple[int, int]] = []

    def add(kind: Kind, value: str, start: int, end: int, origin):
        found.append(Occurrence(kind, value, text[start:end], start, end, origin))

    for match in _URL.finditer(text):
        if len(found) > MAX_OCCURRENCES:
            break
        raw = match.group().rstrip(".,;!?:)]}»")
        start, end = match.start(), match.start() + len(raw)
        url_spans.append((start, end))
        if phone := normalize_whatsapp(raw):
            add("phone", phone, start, end, "whatsapp_url")
        elif (host := normalize_domain(raw)) and not _platform(host):
            add("domain", host, start, end, "website_url")
    for match in _DOMAIN.finditer(text):
        if len(found) > MAX_OCCURRENCES:
            break
        if any(start <= match.start() < end for start, end in url_spans):
            continue
        raw = match.group().rstrip(".,;!?:)]}»")
        url_spans.append((match.start(), match.start() + len(raw)))
        if (host := normalize_domain(raw)) and not _platform(host):
            add("domain", host, match.start(), match.start() + len(raw), "website_url")
    for match in _PHONE.finditer(text):
        if len(found) > MAX_OCCURRENCES:
            break
        if any(start <= match.start() < end for start, end in url_spans):
            continue
        if phone := normalize_phone(match.group()):
            add("phone", phone, match.start(), match.end(), "text")
    words = [(normalized_name(m.group()), m.start(), m.end()) for m in _WORD.finditer(text)]
    for name in sorted({normalized_name(n) for n in known_names} - {""}):
        if len(found) > MAX_OCCURRENCES:
            break
        tokens = name.split()
        for index in range(len(words) - len(tokens) + 1):
            if len(found) > MAX_OCCURRENCES:
                break
            chunk = words[index : index + len(tokens)]
            if [word[0] for word in chunk] == tokens:
                add("alias", name, chunk[0][1], chunk[-1][2], "known_name")
    # Deterministic bounded output with an explicit incompleteness flag.
    ordered = sorted(
        set(found), key=lambda item: (item.start, item.end, item.kind, item.normalized)
    )
    return Identifiers(tuple(ordered[:MAX_OCCURRENCES]), len(ordered) > MAX_OCCURRENCES)


def propose_links(
    documents: Sequence[TraceDocument], *, known_names: Sequence[str] = ()
) -> TraceResult:
    """Compare caller-authorized documents only; never mix DEMO and non-DEMO records."""
    if len(documents) > MAX_DOCUMENTS:
        raise ValueError("Trace document count exceeds the supported input limit")
    extract_identifiers("", known_names=known_names)  # Validate even an empty batch.
    by_id = {}
    indexes = {}
    inverted = defaultdict(set)
    limited = False
    for doc in documents:
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", doc.id)
            or doc.id in by_id
            or type(doc.version) is not int
            or doc.version < 1
            or type(doc.demo) is not bool
        ):
            raise ValueError("Trace documents require unique IDs and valid versions/scopes")
        by_id[doc.id] = doc
        extracted = extract_identifiers(doc.text, known_names=known_names)
        limited |= extracted.limited
        index = defaultdict(list)
        for occurrence in extracted.occurrences:
            key = (occurrence.kind, occurrence.normalized)
            index[key].append(occurrence)
            inverted[(doc.demo, *key)].add(doc.id)
        indexes[doc.id] = index
    pairs = set()
    for ids in inverted.values():
        pairs.update(combinations(sorted(ids), 2))
    proposals = []
    for left, right in sorted(pairs)[:MAX_PROPOSALS]:
        matches = [
            SharedIdentifier(
                kind,
                value,
                tuple(indexes[left][(kind, value)]),
                tuple(indexes[right][(kind, value)]),
            )
            for kind, value in sorted(indexes[left].keys() & indexes[right].keys())
        ]
        a, b = by_id[left], by_id[right]
        proposals.append(
            TraceProposal(
                left,
                right,
                a.version,
                b.version,
                hashlib.sha256(a.text.encode()).hexdigest(),
                hashlib.sha256(b.text.encode()).hexdigest(),
                a.demo,
                tuple(matches),
                all(match.kind == "alias" for match in matches),
            )
        )
    return TraceResult(tuple(proposals), limited, len(pairs) > MAX_PROPOSALS)
