from typing import Literal

from pydantic import AwareDatetime, Field

from app.models.common import DomainModel, Identifier, ShortText
from app.models.entities import Complex, Developer
from app.models.risk import RiskResult


class EvidenceSnapshot(DomainModel):
    id: Identifier
    type: str
    source_url: str | None
    source_reference: str
    excerpt: str
    excerpt_truncated: bool
    captured_at: AwareDatetime
    reviewer: str
    reviewed_at: AwareDatetime
    sha256: str | None
    version: int


class SignalSnapshot(DomainModel):
    complex: Complex
    developer: Developer
    authorized_company: Developer | None = None
    risk: RiskResult
    evidence: list[EvidenceSnapshot]
    captured_at: AwareDatetime


class Signal(DomainModel):
    id: Identifier
    complex_id: Identifier
    title: ShortText
    reason: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    status: Literal["draft", "pending_review", "confirmed", "returned"] = "draft"
    snapshot: SignalSnapshot
    created_by: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    reviewer: str | None = None
    reviewed_at: AwareDatetime | None = None
    review_notes: str = ""
    version: int = 1
    demo: bool = True


class SignalCreate(DomainModel):
    complex_id: Identifier
    expected_complex_version: int = Field(ge=1)
    title: ShortText
    reason: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class SignalDecision(DomainModel):
    action: Literal["submit", "confirm", "return"]
    expected_version: int = Field(ge=1)
    notes: str = Field(min_length=1, max_length=2000, pattern=r"\S")
