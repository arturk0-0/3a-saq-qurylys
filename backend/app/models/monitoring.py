"""Public-source observations are leads, never verified legal evidence."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.models.analysis import Extraction
from app.models.common import DomainModel, Identifier, ShortText


class SourceInput(DomainModel):
    name: ShortText
    kind: Literal["web_search", "telegram", "instagram_ads"]
    target: str = Field(min_length=1, max_length=250, pattern=r"\S")
    interval_minutes: int = Field(default=60, ge=15, le=1440)
    auto_analyze: bool = False


class MonitorSource(SourceInput):
    id: Identifier
    enabled: bool = True
    version: int = 1
    created_at: AwareDatetime
    created_by: str
    last_run_at: AwareDatetime | None = None
    next_run_at: AwareDatetime | None = None
    lease_until: AwareDatetime | None = None
    active_run_id: str | None = None
    last_error: str | None = None


class SourceUpdate(DomainModel):
    expected_version: int = Field(ge=1)
    enabled: bool
    auto_analyze: bool


class MediaReference(DomainModel):
    kind: Literal["image", "video", "thumbnail"]
    url: str = Field(max_length=2000)


class Observation(DomainModel):
    original_url: str = Field(max_length=2000)
    title: str = Field(default="", max_length=500)
    text: str = Field(min_length=1, max_length=20000)
    published_at: AwareDatetime | None = None
    content_kind: Literal["search_snippet", "telegram_post", "instagram_ad"]
    account: str = Field(default="", max_length=500)
    ad_archive_id: str | None = Field(default=None, pattern=r"^[0-9]{1,40}$")
    ad_started_at: AwareDatetime | None = None
    ad_active: bool | None = None
    platforms: list[str] = Field(default_factory=list, max_length=10)
    media: list[MediaReference] = Field(default_factory=list, max_length=12)


class RegistryDocument(DomainModel):
    provider: Literal["homeportal"]
    record_id: str = Field(pattern=r"^[0-9]{1,15}$")
    kind: Literal["regional_permit", "guarantee"]
    name: ShortText
    address: ShortText
    developer: ShortText
    developer_bin: str = Field(pattern=r"^[0-9]{12}$")
    holder: ShortText
    holder_bin: str = Field(pattern=r"^[0-9]{12}$")
    reference: ShortText
    issued_on: date
    source_url: str
    response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    checked_at: AwareDatetime


class BasisReview(DomainModel):
    document: RegistryDocument
    advertisement_date: date
    reviewer: str
    reviewed_at: AwareDatetime
    notes: str


class ItemBasisReview(DomainModel):
    expected_document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_version: int = Field(ge=1)
    record_id: str = Field(pattern=r"^[0-9]{1,15}$")
    advertisement_date: date
    object_matches: Literal[True]
    phase_matches: Literal[True]
    holder_matches: Literal[True]
    document_validity_checked: Literal[True]
    advertisement_date_checked: Literal[True]
    other_risks_reviewed: Literal[True]
    notes: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class MonitorItem(Observation):
    id: Identifier
    source_id: Identifier
    source_ids: list[Identifier] = Field(max_length=20)
    discovery_url: str
    text_sha256: str
    response_sha256: str
    revision_key: str
    created_at: AwareDatetime
    last_seen_at: AwareDatetime
    region_matches: list[str]
    housing_matches: list[str]
    payment_matches: list[str]
    status: Literal["new", "investigating", "dismissed"] = "new"
    reviewer: str | None = None
    reviewed_at: AwareDatetime | None = None
    notes: str = ""
    version: int = 1
    demo: Literal[False] = False
    ai_status: Literal["not_requested", "running", "succeeded", "failed"] = "not_requested"
    ai_request_id: str | None = None
    ai_model: str | None = None
    ai_prompt_version: str | None = None
    ai_error: str | None = None
    ai_completed_at: AwareDatetime | None = None
    extraction: Extraction | None = None
    advertisement_id: Identifier | None = None
    basis_review: BasisReview | None = None


class ItemReview(DomainModel):
    expected_version: int = Field(ge=1)
    decision: Literal["investigating", "dismissed", "new"]
    notes: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class ItemAnalyze(DomainModel):
    expected_version: int = Field(ge=1)
    request_id: UUID


class ItemAttach(DomainModel):
    expected_version: int = Field(ge=1)
    complex_id: Identifier
    notes: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class MonitorRun(DomainModel):
    id: Identifier
    source_id: Identifier
    created_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    actor_uid: str
    status: Literal["running", "succeeded", "failed"] = "running"
    fetched: int = 0
    relevant: int = 0
    created: int = 0
    duplicates: int = 0
    limited: bool = False
    error_code: str | None = None
    auto_ai_status: str | None = None
    unreadable: int = 0
    provider_credits_before: int | None = None
