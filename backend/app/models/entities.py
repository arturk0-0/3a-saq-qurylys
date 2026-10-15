from typing import Literal, Self

from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from app.models.common import DomainModel, Identifier, ShortText
from app.models.risk import RiskFactor, VerificationStatus


class Developer(DomainModel):
    id: Identifier
    name: ShortText
    bin: str = Field(pattern=r"^[0-9]{12}$")
    demo: bool = True


class Coordinates(DomainModel):
    latitude: float = Field(ge=47, le=51.5)
    longitude: float = Field(ge=81, le=87.5)


class LegalBasis(DomainModel):
    type: Literal["guarantee", "regional_permit", "other_applicable", "unknown"] = "unknown"
    status: Literal["confirmed", "disproved", "unknown"] = "unknown"
    reference: str = Field(default="", max_length=500)
    source: str = Field(default="", max_length=2000)
    checked_at: AwareDatetime | None = None
    reviewer: str | None = Field(default=None, min_length=1, max_length=128)
    valid_until: AwareDatetime | None = None

    @model_validator(mode="after")
    def require_source(self) -> Self:
        if self.status != "unknown" and (
            not self.source.strip() or not self.reviewer or self.checked_at is None
        ):
            raise ValueError("Reviewed legal basis requires a source, reviewer and date")
        if self.status == "confirmed" and (self.type == "unknown" or not self.reference.strip()):
            raise ValueError("Confirmed legal basis requires an applicable type and reference")
        return self


class Progress(DomainModel):
    claimed_percent: int | None = Field(default=None, ge=0, le=100)
    verified_percent: int | None = Field(default=None, ge=0, le=100)
    claimed_at: AwareDatetime | None = None
    verified_at: AwareDatetime | None = None
    claimed_source: str = Field(default="", max_length=2000)
    verified_source: str = Field(default="", max_length=2000)


class Complex(DomainModel):
    id: Identifier
    name: ShortText
    city: Literal["Усть-Каменогорск", "Риддер", "Алтай", "Серебрянск", "Шемонаиха", "Зайсан"]
    region: Literal["ВКО"] = "ВКО"
    address: ShortText
    developer_id: Identifier
    stage: Literal["planning", "under_construction", "commissioned"] = "under_construction"
    coordinates: Coordinates | None = None
    progress: Progress = Field(default_factory=Progress)
    legal_basis: LegalBasis = Field(default_factory=LegalBasis)
    factors: list[RiskFactor] = Field(default_factory=list, max_length=6)
    demo: bool = True
    scenario: Literal["A", "B", "C"] | None = None
    version: int = Field(default=1, ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def distinct_factors(self) -> Self:
        if len({factor.code for factor in self.factors}) != len(self.factors):
            raise ValueError("Risk factors must be unique per complex")
        if self.legal_basis.status == "confirmed" and any(
            factor.code == "R1" and factor.status == "confirmed" for factor in self.factors
        ):
            raise ValueError("An applicable confirmed legal basis contradicts confirmed R1")
        return self


class Advertisement(DomainModel):
    id: Identifier
    complex_id: Identifier
    platform: ShortText
    account: ShortText
    source_url: HttpUrl
    text: str = Field(min_length=1, max_length=20000)
    published_at: AwareDatetime
    captured_at: AwareDatetime
    created_by: str = Field(min_length=1, max_length=128)
    attachment_ids: list[Identifier] = Field(default_factory=list, max_length=10)
    demo: bool = True
    linkage_status: Literal["proposed", "confirmed", "rejected"] = "confirmed"
    version: int = Field(default=1, ge=1)


class Evidence(DomainModel):
    id: Identifier
    complex_id: Identifier
    advertisement_id: Identifier | None = None
    type: Literal[
        "advertisement",
        "legal_basis_review",
        "complaint",
        "progress_report",
        "work_status",
        "document",
        "screenshot",
    ]
    source_url: HttpUrl | None = None
    source_reference: str = Field(default="", max_length=2000)
    excerpt: str = Field(min_length=1, max_length=20000)
    captured_at: AwareDatetime
    status: VerificationStatus = VerificationStatus.UNKNOWN
    reviewer: str | None = Field(default=None, min_length=1, max_length=128)
    reviewed_at: AwareDatetime | None = None
    storage_path: str | None = Field(default=None, max_length=500)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    media_type: Literal["image/jpeg", "image/png", "image/webp"] | None = None
    size_bytes: int | None = Field(default=None, ge=1, le=10485760)
    # Explicit human findings, never set by Gemini or derived from an empty lookup.
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
    demo: bool = True
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def verified_provenance(self) -> Self:
        if self.status == VerificationStatus.CONFIRMED and (
            not self.reviewer
            or self.reviewed_at is None
            or not (self.source_url or self.source_reference.strip())
        ):
            raise ValueError("Verified evidence requires source, reviewer and review time")
        if self.legal_absence_verified and not self.applicable_bases_checked:
            raise ValueError("Legal absence requires reviewing all applicable legal bases")
        return self
