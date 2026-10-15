from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, HttpUrl, field_validator

from app.models.common import DomainModel, Identifier, ShortText
from app.models.entities import Coordinates, Progress
from app.models.risk import FactorCode


class AdvertisementCreate(DomainModel):
    complex_id: Identifier
    platform: ShortText
    account: ShortText
    source_url: HttpUrl
    text: str = Field(min_length=1, max_length=20000)
    published_at: AwareDatetime

    @field_validator("text", "platform", "account")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text must not be empty")
        return value  # Preserve the original source exactly, including whitespace.


class ComplexCreate(DomainModel):
    name: ShortText
    city: Literal["Усть-Каменогорск", "Риддер", "Алтай", "Серебрянск", "Шемонаиха", "Зайсан"]
    address: ShortText
    developer_id: Identifier
    stage: Literal["planning", "under_construction", "commissioned"] = "under_construction"
    coordinates: Coordinates | None = None
    progress: Progress = Field(default_factory=Progress)
    demo: Literal[True] = True


class EvidenceCreate(DomainModel):
    complex_id: Identifier
    advertisement_id: Identifier | None = None
    type: Literal[
        "advertisement",
        "legal_basis_review",
        "complaint",
        "progress_report",
        "work_status",
        "document",
    ]
    source_url: HttpUrl | None = None
    source_reference: str = Field(default="", max_length=2000)
    excerpt: str = Field(min_length=1, max_length=20000)
    captured_at: AwareDatetime

    @field_validator("excerpt")
    @classmethod
    def nonempty_excerpt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Excerpt must not be empty")
        return value


class EvidenceReview(DomainModel):
    expected_version: int = Field(ge=1)
    decision: Literal["confirmed", "rejected"]
    notes: str = Field(min_length=1, max_length=5000)
    legal_absence_verified: bool = False
    applicable_bases_checked: bool = False
    active_advertising_verified: bool = False
    construction_verified: bool = False
    payment_offer_verified: bool = False
    collective_complaint_verified: bool = False
    work_stoppage_verified: bool = False
    claimed_percent: int | None = Field(default=None, ge=0, le=100)
    verified_percent: int | None = Field(default=None, ge=0, le=100)
    claimed_at: AwareDatetime | None = None
    verified_at: AwareDatetime | None = None
    claimed_source: str = Field(default="", max_length=2000)
    verified_source: str = Field(default="", max_length=2000)

    @field_validator("notes")
    @classmethod
    def nonempty_notes(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Review notes are required")
        return value


class FactorDecision(DomainModel):
    code: FactorCode
    decision: Literal["confirmed", "rejected", "unknown"]
    evidence_ids: list[Identifier] = Field(default_factory=list, max_length=30)
    notes: str = Field(min_length=1, max_length=5000)
    expected_version: int = Field(ge=1)

    @field_validator("notes")
    @classmethod
    def nonempty_notes(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Review notes are required")
        return value


class LegalBasisInput(DomainModel):
    type: Literal["guarantee", "regional_permit", "other_applicable", "unknown"] = "unknown"
    status: Literal["confirmed", "disproved", "unknown"] = "unknown"
    reference: str = Field(default="", max_length=500)
    source: str = Field(default="", max_length=2000)
    valid_until: AwareDatetime | None = None


class LegalBasisUpdate(DomainModel):
    basis: LegalBasisInput
    expected_version: int = Field(ge=1)


PageSize = Annotated[int, Field(ge=1, le=100)]
