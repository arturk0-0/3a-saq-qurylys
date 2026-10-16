from typing import Literal

from pydantic import AwareDatetime, Field

from app.models.common import DomainModel, Identifier


class TraceOccurrence(DomainModel):
    kind: Literal["phone", "domain", "alias"]
    normalized: str = Field(min_length=1, max_length=10000)
    quote: str = Field(min_length=1, max_length=20000)
    start: int = Field(ge=0, le=20000)
    end: int = Field(ge=1, le=20000)
    origin: Literal["text", "whatsapp_url", "website_url", "known_name"]


class TraceMatch(DomainModel):
    kind: Literal["phone", "domain", "alias"]
    normalized: str = Field(min_length=1, max_length=10000)
    left: list[TraceOccurrence] = Field(min_length=1, max_length=100)
    right: list[TraceOccurrence] = Field(min_length=1, max_length=100)


class TraceSnapshot(DomainModel):
    left_id: Identifier
    right_id: Identifier
    left_version: int = Field(ge=1)
    right_version: int = Field(ge=1)
    left_text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    right_text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    demo: bool
    matches: list[TraceMatch] = Field(min_length=1, max_length=100)
    name_only: bool
    normalizer_version: str = Field(min_length=1, max_length=64)


class AdLink(TraceSnapshot):
    id: Identifier
    status: Literal["proposed", "confirmed", "rejected"] = "proposed"
    created_by: str = Field(min_length=1, max_length=128)
    created_at: AwareDatetime
    reviewer: str | None = Field(default=None, min_length=1, max_length=128)
    reviewed_at: AwareDatetime | None = None
    notes: str = Field(default="", max_length=2000)
    version: int = Field(default=1, ge=1)


class TraceSave(DomainModel):
    expected_snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    other_advertisement_id: Identifier
    expected_version: int = Field(ge=1)
    expected_other_version: int = Field(ge=1)


class TraceDecision(DomainModel):
    decision: Literal["confirmed", "rejected"]
    notes: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    expected_version: int = Field(ge=1)
